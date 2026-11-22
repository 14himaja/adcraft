from typing import Any

from pymongo import ReturnDocument

from app import audit
from app.clock import Clock
from app.config import Settings
from app.domain.workspaces import resolve_workspace_id
from app.integrations.base.models import DiscoveredAccount, OAuthTokenResult, PlatformId
from app.security.crypto import decrypt_token, encrypt_token


def tenant_scope(user: dict) -> tuple[Any, str, str]:
    user_id = user["_id"]
    org_id = resolve_workspace_id(user=user)
    return user_id, org_id, f"{user_id}:{org_id}"


async def save_connection_tokens(
    db,
    *,
    user_id,
    organization_id: str,
    platform: PlatformId,
    token: OAuthTokenResult,
    settings: Settings,
    clock: Clock,
    account_hint: DiscoveredAccount | None = None,
) -> dict:
    now = clock.now()
    tenant_id = f"{user_id}:{organization_id}"
    updates: dict[str, Any] = {
        "user_id": user_id,
        "organization_id": organization_id,
        "tenant_id": tenant_id,
        "platform": platform,
        "access_token_ciphertext": encrypt_token(settings.token_encryption_key, token.access_token),
        "token_expires_at": token.expires_at,
        "scopes": list(token.scopes),
        "status": "ACTIVE",
        "mode": token.mode,
        "last_error": None,
        "updated_at": now,
    }
    if token.refresh_token:
        updates["refresh_token_ciphertext"] = encrypt_token(
            settings.token_encryption_key, token.refresh_token
        )
    if account_hint is not None:
        updates["platform_account_id"] = account_hint.account_id
        updates["account_display_name"] = account_hint.display_name
        updates["account_username"] = account_hint.username
        updates["account_type"] = account_hint.account_type
        if account_hint.target_id:
            updates["selected_target_id"] = account_hint.target_id
            updates["selected_target_name"] = account_hint.target_name or account_hint.display_name
            updates["selected_target_type"] = account_hint.target_type or account_hint.account_type
        updates["metadata"] = {
            "avatar_url": account_hint.avatar_url,
            "permission_note": account_hint.permission_note,
            **account_hint.extra,
        }

    doc = await db.social_connections.find_one_and_update(
        {"user_id": user_id, "organization_id": organization_id, "platform": platform},
        {
            "$set": updates,
            "$setOnInsert": {"created_at": now, "schema_version": 1},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    await audit.record(
        db,
        actor="user",
        event_type="SOCIAL_CONNECTED",
        payload={
            "platform": platform,
            "organization_id": organization_id,
            "mode": token.mode,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        },
        user_id=user_id,
    )
    return doc


async def sync_meta_to_social(db, *, user_id, organization_id: str, meta_conn: dict) -> None:
    """Keep social_connections synchronized with legacy meta_connections for Instagram & Facebook."""
    now = meta_conn.get("updated_at") or meta_conn.get("created_at")
    tenant_id = f"{user_id}:{organization_id}"
    base = {
        "user_id": user_id,
        "organization_id": organization_id,
        "tenant_id": tenant_id,
        "access_token_ciphertext": meta_conn["token_ciphertext"],
        "token_expires_at": meta_conn.get("token_expires_at"),
        "scopes": list(meta_conn.get("scopes") or []),
        "status": meta_conn.get("status", "ACTIVE"),
        "mode": meta_conn.get("mode", "real"),
        "last_error": None,
        "updated_at": now,
    }

    ig_id = meta_conn.get("instagram_user_id")
    ig_username = meta_conn.get("instagram_username")
    ig_updates = {
        **base,
        "platform": "instagram",
        "platform_account_id": ig_id,
        "account_display_name": f"@{ig_username}" if ig_username else None,
        "account_username": ig_username,
        "account_type": "business" if ig_id else None,
        "selected_target_id": ig_id,
        "selected_target_name": f"@{ig_username}" if ig_username else None,
        "selected_target_type": "instagram_account" if ig_id else None,
        "metadata": {
            "linked_page_id": meta_conn.get("page_id"),
            "linked_page_name": meta_conn.get("page_name"),
        },
    }
    await db.social_connections.update_one(
        {"user_id": user_id, "organization_id": organization_id, "platform": "instagram"},
        {"$set": ig_updates, "$setOnInsert": {"created_at": now, "schema_version": 1}},
        upsert=True,
    )

    page_id = meta_conn.get("page_id")
    page_name = meta_conn.get("page_name")
    fb_updates = {
        **base,
        "platform": "facebook",
        "platform_account_id": page_id,
        "account_display_name": page_name,
        "account_username": page_name,
        "account_type": "page" if page_id else None,
        "selected_target_id": page_id,
        "selected_target_name": page_name,
        "selected_target_type": "facebook_page" if page_id else None,
        "metadata": {
            "ad_account_id": meta_conn.get("ad_account_id"),
            "ad_account_name": meta_conn.get("ad_account_name"),
            "currency": meta_conn.get("currency"),
        },
    }
    await db.social_connections.update_one(
        {"user_id": user_id, "organization_id": organization_id, "platform": "facebook"},
        {"$set": fb_updates, "$setOnInsert": {"created_at": now, "schema_version": 1}},
        upsert=True,
    )


async def get_connection(db, *, user_id, organization_id: str, platform: PlatformId) -> dict | None:
    doc = await db.social_connections.find_one(
        {"user_id": user_id, "organization_id": organization_id, "platform": platform}
    )
    if doc is None and platform in ("instagram", "facebook"):
        meta_conn = await db.meta_connections.find_one({"user_id": user_id})
        if meta_conn and meta_conn.get("token_ciphertext"):
            # Only auto-sync if the user hasn't explicitly disconnected this specific platform
            tombstone = await db.social_connections.find_one(
                {"user_id": user_id, "organization_id": organization_id, "platform": f"_disconnected_{platform}"}
            )
            if tombstone is None:
                await sync_meta_to_social(db, user_id=user_id, organization_id=organization_id, meta_conn=meta_conn)
                doc = await db.social_connections.find_one(
                    {"user_id": user_id, "organization_id": organization_id, "platform": platform}
                )
    return doc


async def list_connections(db, *, user_id, organization_id: str) -> dict[str, dict]:
    docs = await db.social_connections.find(
        {"user_id": user_id, "organization_id": organization_id}
    ).to_list(50)
    by_platform = {doc["platform"]: doc for doc in docs if not str(doc["platform"]).startswith("_")}
    if "instagram" not in by_platform or "facebook" not in by_platform:
        meta_conn = await db.meta_connections.find_one({"user_id": user_id})
        if meta_conn and meta_conn.get("token_ciphertext"):
            for plat in ("instagram", "facebook"):
                if plat not in by_platform:
                    tombstone = f"_disconnected_{plat}"
                    if not any(d.get("platform") == tombstone for d in docs):
                        await get_connection(db, user_id=user_id, organization_id=organization_id, platform=plat)
            docs = await db.social_connections.find(
                {"user_id": user_id, "organization_id": organization_id}
            ).to_list(50)
            by_platform = {doc["platform"]: doc for doc in docs if not str(doc["platform"]).startswith("_")}
    return by_platform


def decrypt_connection_tokens(connection: dict, settings: Settings) -> tuple[str, str | None]:
    access_token = decrypt_token(settings.token_encryption_key, connection["access_token_ciphertext"])
    refresh_token = None
    if connection.get("refresh_token_ciphertext"):
        refresh_token = decrypt_token(settings.token_encryption_key, connection["refresh_token_ciphertext"])
    return access_token, refresh_token


async def select_connection_account(
    db,
    *,
    user_id,
    organization_id: str,
    platform: PlatformId,
    account: DiscoveredAccount,
    clock: Clock,
) -> dict | None:
    now = clock.now()
    updates = {
        "platform_account_id": account.account_id,
        "account_display_name": account.display_name,
        "account_username": account.username,
        "account_type": account.account_type,
        "selected_target_id": account.target_id or account.account_id,
        "selected_target_name": account.target_name or account.display_name,
        "selected_target_type": account.target_type or account.account_type,
        "metadata": {
            "avatar_url": account.avatar_url,
            "permission_note": account.permission_note,
            **account.extra,
        },
        "updated_at": now,
    }
    doc = await db.social_connections.find_one_and_update(
        {"user_id": user_id, "organization_id": organization_id, "platform": platform},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    await audit.record(
        db,
        actor="user",
        event_type="SOCIAL_ACCOUNT_SELECTED",
        payload={
            "platform": platform,
            "organization_id": organization_id,
            "target_id": updates["selected_target_id"],
            "account_type": account.account_type,
        },
        user_id=user_id,
    )
    return doc


async def mark_connection_expired(
    db, *, user_id, organization_id: str, platform: PlatformId, clock: Clock, error: str | None = None
) -> None:
    await db.social_connections.update_one(
        {"user_id": user_id, "organization_id": organization_id, "platform": platform},
        {"$set": {"status": "EXPIRED", "last_error": error, "updated_at": clock.now()}},
    )
    await audit.record(
        db,
        actor="system",
        event_type="SOCIAL_AUTH_EXPIRED",
        payload={"platform": platform, "organization_id": organization_id},
        user_id=user_id,
    )


async def delete_connection(db, *, user_id, organization_id: str, platform: PlatformId, clock: Clock) -> None:
    await db.social_connections.delete_one(
        {"user_id": user_id, "organization_id": organization_id, "platform": platform}
    )
    if platform in ("instagram", "facebook"):
        # Record per-platform disconnect so legacy meta_connections doesn't auto-recreate it
        await db.social_connections.update_one(
            {"user_id": user_id, "organization_id": organization_id, "platform": f"_disconnected_{platform}"},
            {"$set": {"updated_at": clock.now()}},
            upsert=True,
        )
    await audit.record(
        db,
        actor="user",
        event_type="SOCIAL_DISCONNECTED",
        payload={"platform": platform, "organization_id": organization_id},
        user_id=user_id,
    )


async def clear_disconnect_tombstone(db, *, user_id, organization_id: str, platform: PlatformId) -> None:
    await db.social_connections.delete_one(
        {"user_id": user_id, "organization_id": organization_id, "platform": f"_disconnected_{platform}"}
    )
