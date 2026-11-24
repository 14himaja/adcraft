from datetime import timedelta
from urllib.parse import urlencode

import structlog

from app.config import Settings
from app.integrations.base.adapter import ensure_utc
from app.integrations.base.errors import (
    IntegrationAuthExpired,
    IntegrationNotConfigured,
    IntegrationNotConnected,
    IntegrationValidationError,
    sanitize_error_message,
)
from app.integrations.base.models import DiscoveredAccount, OAuthTokenResult, PlatformId
from app.integrations.oauth import (
    check_oauth_state,
    decrypt_connection_tokens,
    delete_connection,
    get_connection,
    list_connections,
    make_oauth_state,
    mark_connection_expired,
    save_connection_tokens,
    select_connection_account,
    tenant_scope,
)
from app.integrations.oauth.token_store import clear_disconnect_tombstone
from app.integrations.registry import get_adapter, list_adapters
from app.meta import connections as meta_connections

log = structlog.get_logger()
FAKE_TOKEN_LIFETIME = timedelta(days=60)


def _append_query(path: str, params: dict[str, str]) -> str:
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}{urlencode(params)}"


async def get_all_connections_status(db, user: dict, *, settings: Settings, clock) -> dict:
    user_id, org_id, _ = tenant_scope(user)
    now = clock.now()
    existing = await list_connections(db, user_id=user_id, organization_id=org_id)
    platforms = [
        adapter.get_connection_status(existing.get(adapter.platform_id), now=now, settings=settings)
        for adapter in list_adapters()
    ]
    connected_count = sum(1 for p in platforms if p["status"] == "ACTIVE")
    return {
        "organization_id": org_id,
        "connected_count": connected_count,
        "total_platforms": len(platforms),
        "platforms": platforms,
    }


async def get_platform_status(db, user: dict, platform: str, *, settings: Settings, clock) -> dict:
    adapter = get_adapter(platform)
    user_id, org_id, _ = tenant_scope(user)
    conn = await get_connection(db, user_id=user_id, organization_id=org_id, platform=adapter.platform_id)
    return adapter.get_connection_status(conn, now=clock.now(), settings=settings)


async def initiate_connect(
    db,
    user: dict,
    platform: str,
    *,
    settings: Settings,
    clock,
    return_to: str | None = None,
    container=None,
) -> tuple[str, bool]:
    """Return (redirect_url, is_immediate_fake_connect)."""
    adapter = get_adapter(platform)
    user_id, org_id, _ = tenant_scope(user)
    await clear_disconnect_tombstone(db, user_id=user_id, organization_id=org_id, platform=adapter.platform_id)

    if adapter.use_fake_mode(settings):
        fake_token = OAuthTokenResult(
            access_token=f"fake-{platform}-token",
            refresh_token=f"fake-{platform}-refresh" if adapter.definition(settings).capabilities.supports_refresh else None,
            expires_at=clock.now() + FAKE_TOKEN_LIFETIME,
            scopes=adapter.definition(settings).required_scopes,
            mode="fake",
        )
        accounts = await adapter.get_accounts(
            fake_token.access_token,
            settings,
            connection={"mode": "fake"},
            container=container,
        )
        default_acc = next((a for a in accounts if a.can_publish), accounts[0] if accounts else None)
        await save_connection_tokens(
            db,
            user_id=user_id,
            organization_id=org_id,
            platform=adapter.platform_id,
            token=fake_token,
            settings=settings,
            clock=clock,
            account_hint=default_acc,
        )
        await _sync_social_to_meta(
            db, user_id=user_id, platform=adapter.platform_id, token=fake_token, account=default_acc, settings=settings, clock=clock
        )
        dest = _append_query(return_to or "/?section=connections", {"connected": "1", "platform": platform})
        return dest, True

    if not adapter.is_configured(settings):
        raise IntegrationNotConfigured(
            f"{adapter.definition(settings).name} OAuth credentials are not configured on this server.",
            {
                "platform": platform,
                "required_env_vars": list(adapter.definition(settings).required_env_vars),
            },
        )

    code_verifier = None
    code_challenge = None

    state = make_oauth_state(
        settings,
        user_id=user_id,
        organization_id=org_id,
        platform=adapter.platform_id,
        return_to=return_to,
        code_verifier=code_verifier,
    )
    return adapter.connect(settings, state, code_challenge=code_challenge), False


async def handle_oauth_callback(
    db,
    user: dict,
    platform: str,
    *,
    state: str,
    code: str | None,
    error: str | None,
    settings: Settings,
    clock,
    container=None,
) -> str:
    adapter = get_adapter(platform)
    user_id, current_org_id, _ = tenant_scope(user)

    if error:
        target = "/?section=connections"
        if state:
            try:
                parsed = check_oauth_state(settings, state, user_id=user_id, platform=adapter.platform_id)
                target = parsed["return_to"]
            except Exception:
                pass
        return _append_query(target, {"error": "denied", "platform": platform})

    claims = check_oauth_state(settings, state, user_id=user_id, platform=adapter.platform_id)
    org_id = claims["organization_id"] or current_org_id
    return_to = claims["return_to"]

    if not code:
        raise IntegrationValidationError(f"{adapter.definition(settings).name} did not return an authorization code.")

    token = await adapter.handle_callback(
        settings,
        code,
        now=clock.now(),
        code_verifier=claims.get("code_verifier"),
    )
    await clear_disconnect_tombstone(db, user_id=user_id, organization_id=org_id, platform=adapter.platform_id)

    account_hint: DiscoveredAccount | None = None
    try:
        discovered = await adapter.get_accounts(
            token.access_token,
            settings,
            connection={"mode": token.mode, "scopes": list(token.scopes)},
            container=container,
        )
        account_hint = next((a for a in discovered if a.can_publish), discovered[0] if discovered else None)
    except Exception as exc:
        log.warning("social_initial_account_discovery_failed", platform=platform, error=sanitize_error_message(str(exc)))

    await save_connection_tokens(
        db,
        user_id=user_id,
        organization_id=org_id,
        platform=adapter.platform_id,
        token=token,
        settings=settings,
        clock=clock,
        account_hint=account_hint,
    )
    await _sync_social_to_meta(
        db, user_id=user_id, platform=adapter.platform_id, token=token, account=account_hint, settings=settings, clock=clock
    )
    return _append_query(return_to, {"connected": "1", "platform": platform})


async def _ensure_active_token(
    db, user_id, org_id: str, platform: PlatformId, *, settings: Settings, clock
) -> tuple[dict, str]:
    adapter = get_adapter(platform)
    conn = await get_connection(db, user_id=user_id, organization_id=org_id, platform=platform)
    if conn is None:
        raise IntegrationNotConnected(f"Connect {adapter.definition(settings).name} first.")

    access_token, refresh_token = decrypt_connection_tokens(conn, settings)
    now_utc = ensure_utc(clock.now())
    expires_at = conn.get("token_expires_at")
    is_expired = conn.get("status") == "EXPIRED" or (
        expires_at is not None and ensure_utc(expires_at) <= now_utc
    )

    if is_expired:
        if refresh_token and conn.get("mode", "real") == "real":
            try:
                refreshed = await adapter.refresh_token(settings, refresh_token, now=clock.now())
                if refreshed:
                    conn = await save_connection_tokens(
                        db,
                        user_id=user_id,
                        organization_id=org_id,
                        platform=platform,
                        token=refreshed,
                        settings=settings,
                        clock=clock,
                    )
                    return conn, refreshed.access_token
            except Exception as exc:
                await mark_connection_expired(
                    db, user_id=user_id, organization_id=org_id, platform=platform, clock=clock, error=str(exc)[:200]
                )
                raise IntegrationAuthExpired(
                    f"Your {adapter.definition(settings).name} connection expired. Please reconnect."
                ) from exc
        await mark_connection_expired(
            db, user_id=user_id, organization_id=org_id, platform=platform, clock=clock
        )
        raise IntegrationAuthExpired(
            f"Your {adapter.definition(settings).name} connection expired. Please reconnect."
        )

    return conn, access_token


async def refresh_platform_connection(
    db, user: dict, platform: str, *, settings: Settings, clock
) -> dict:
    adapter = get_adapter(platform)
    user_id, org_id, _ = tenant_scope(user)
    conn = await get_connection(db, user_id=user_id, organization_id=org_id, platform=adapter.platform_id)
    if conn is None:
        raise IntegrationNotConnected(f"Connect {adapter.definition(settings).name} first.")
    _, refresh_tok = decrypt_connection_tokens(conn, settings)
    if conn.get("mode") == "fake":
        refreshed = OAuthTokenResult(
            access_token=f"fake-{platform}-token-refreshed",
            refresh_token=refresh_tok,
            expires_at=clock.now() + FAKE_TOKEN_LIFETIME,
            scopes=tuple(conn.get("scopes") or []),
            mode="fake",
        )
    elif refresh_tok:
        refreshed = await adapter.refresh_token(settings, refresh_tok, now=clock.now())
        if refreshed is None:
            raise IntegrationValidationError(f"{adapter.definition(settings).name} does not support token refresh.")
    else:
        raise IntegrationValidationError(
            f"{adapter.definition(settings).name} does not have a refresh token; reconnect via OAuth."
        )
    saved = await save_connection_tokens(
        db,
        user_id=user_id,
        organization_id=org_id,
        platform=adapter.platform_id,
        token=refreshed,
        settings=settings,
        clock=clock,
    )
    return adapter.get_connection_status(saved, now=clock.now(), settings=settings)


async def discover_platform_accounts(
    db, user: dict, platform: str, *, settings: Settings, clock, container=None
) -> dict:
    adapter = get_adapter(platform)
    user_id, org_id, _ = tenant_scope(user)
    conn, access_token = await _ensure_active_token(
        db, user_id, org_id, adapter.platform_id, settings=settings, clock=clock
    )
    try:
        accounts = await adapter.get_accounts(
            access_token, settings, connection=conn, container=container
        )
    except IntegrationAuthExpired as exc:
        await mark_connection_expired(
            db, user_id=user_id, organization_id=org_id, platform=adapter.platform_id, clock=clock, error=str(exc)
        )
        raise
    return {
        "platform": adapter.platform_id,
        "selected_target_id": conn.get("selected_target_id"),
        "accounts": [a.to_dict() for a in accounts],
    }


async def select_platform_account(
    db,
    user: dict,
    platform: str,
    *,
    target_id: str,
    settings: Settings,
    clock,
    container=None,
) -> dict:
    adapter = get_adapter(platform)
    user_id, org_id, _ = tenant_scope(user)
    conn, access_token = await _ensure_active_token(
        db, user_id, org_id, adapter.platform_id, settings=settings, clock=clock
    )
    accounts = await adapter.get_accounts(access_token, settings, connection=conn, container=container)
    match = next((a for a in accounts if (a.target_id or a.account_id) == target_id or a.account_id == target_id), None)
    if match is None:
        raise IntegrationValidationError(
            f"Account or target {target_id!r} was not found in your authorized {adapter.definition(settings).name} assets."
        )
    if not match.can_publish:
        raise IntegrationValidationError(
            match.permission_note or f"Selected {adapter.definition(settings).name} target lacks publishing permission."
        )
    saved = await select_connection_account(
        db,
        user_id=user_id,
        organization_id=org_id,
        platform=adapter.platform_id,
        account=match,
        clock=clock,
    )
    await _sync_selection_to_meta(db, user_id=user_id, platform=adapter.platform_id, account=match, clock=clock, container=container)
    return adapter.get_connection_status(saved, now=clock.now(), settings=settings)


async def disconnect_platform(db, user: dict, platform: str, *, settings: Settings, clock) -> dict:
    adapter = get_adapter(platform)
    user_id, org_id, _ = tenant_scope(user)
    conn = await get_connection(db, user_id=user_id, organization_id=org_id, platform=adapter.platform_id)
    if conn is not None and conn.get("mode", "real") == "real":
        try:
            access_token, _ = decrypt_connection_tokens(conn, settings)
            await adapter.revoke_token(settings, access_token)
        except Exception as exc:
            log.warning("social_revoke_failed", platform=platform, error=sanitize_error_message(str(exc)))
    await delete_connection(db, user_id=user_id, organization_id=org_id, platform=adapter.platform_id, clock=clock)
    if adapter.platform_id == "instagram":
        await meta_connections.disconnect_asset(db, user_id, asset_type="instagram", clock=clock)
    elif adapter.platform_id == "facebook":
        await meta_connections.disconnect_asset(db, user_id, asset_type="page", clock=clock)
    return adapter.get_connection_status(None, now=clock.now(), settings=settings)


async def _sync_social_to_meta(
    db,
    *,
    user_id,
    platform: PlatformId,
    token: OAuthTokenResult,
    account: DiscoveredAccount | None,
    settings: Settings,
    clock,
) -> None:
    if platform not in ("instagram", "facebook"):
        return
    await meta_connections.save_token(
        db,
        user_id=user_id,
        token=token.access_token,
        expires_at=token.expires_at or (clock.now() + FAKE_TOKEN_LIFETIME),
        mode=token.mode,
        settings=settings,
        clock=clock,
    )
    if account is not None:
        await _sync_selection_to_meta(db, user_id=user_id, platform=platform, account=account, clock=clock)


async def _sync_selection_to_meta(
    db,
    *,
    user_id,
    platform: PlatformId,
    account: DiscoveredAccount,
    clock,
    container=None,
) -> None:
    if platform == "instagram":
        page = None
        if account.extra.get("page_id"):
            page = {"id": account.extra["page_id"], "name": account.extra.get("page_name", "")}
        await meta_connections.select_assets(
            db,
            user_id,
            page=page,
            instagram={"id": account.account_id, "username": account.username or account.display_name.lstrip("@")},
            clock=clock,
            container=container,
        )
    elif platform == "facebook":
        await meta_connections.select_assets(
            db,
            user_id,
            page={"id": account.account_id, "name": account.display_name},
            clock=clock,
            container=container,
        )
