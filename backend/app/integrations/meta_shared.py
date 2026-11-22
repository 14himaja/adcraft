from datetime import datetime
from urllib.parse import urlencode

from app.config import Settings
from app.container import build_meta_gateway
from app.integrations.base.errors import (
    IntegrationApiError,
    IntegrationAuthExpired,
    IntegrationPermissionDenied,
    IntegrationRateLimited,
)
from app.integrations.base.models import OAuthTokenResult
from app.meta.errors import ErrorClass, MetaError, classify
from app.meta.oauth import DIALOG_URL, SCOPES, exchange_code

META_PLATFORM_SCOPES = (
    "ads_management",
    "ads_read",
    "business_management",
    "pages_show_list",
    "pages_manage_posts",
    "pages_read_engagement",
    "instagram_basic",
    "instagram_content_publish",
    "instagram_manage_messages",
    "pages_messaging",
    "pages_manage_metadata",
)


def meta_redirect_uri(settings: Settings, platform: str) -> str:
    if platform == "instagram" and settings.instagram_redirect_uri:
        return settings.instagram_redirect_uri
    if platform == "facebook" and settings.facebook_redirect_uri:
        return settings.facebook_redirect_uri
    return settings.meta_redirect_uri


def meta_auth_url(settings: Settings, state: str, *, platform: str) -> str:
    params = {
        "client_id": settings.meta_app_id,
        "redirect_uri": meta_redirect_uri(settings, platform),
        "state": state,
        "response_type": "code",
    }
    if settings.meta_login_config_id:
        params |= {"config_id": settings.meta_login_config_id, "override_default_response_type": "true"}
    else:
        params["scope"] = ",".join(META_PLATFORM_SCOPES)
    return f"{DIALOG_URL.format(version=settings.meta_api_version)}?{urlencode(params)}"


async def meta_exchange_code(settings: Settings, code: str, *, now: datetime) -> OAuthTokenResult:
    try:
        token = await exchange_code(settings, code, now=now)
    except MetaError as exc:
        raise translate_meta_error(exc, platform="meta") from exc
    return OAuthTokenResult(
        access_token=token.access_token,
        expires_at=token.expires_at,
        scopes=tuple(SCOPES),
        mode="real",
    )


def meta_gateway(access_token: str, settings: Settings, *, mode: str, container=None):
    if mode == "fake" and container is not None:
        return container.gateway_for({"mode": "fake"})
    return build_meta_gateway(settings, access_token=access_token, mode=mode)


def translate_meta_error(exc: MetaError, *, platform: str) -> Exception:
    kind = classify(exc)
    if kind == ErrorClass.AUTH:
        return IntegrationAuthExpired(str(exc), {"platform": platform, "meta_code": exc.meta_code})
    if kind == ErrorClass.PERMISSION:
        return IntegrationPermissionDenied(str(exc), {"platform": platform, "meta_code": exc.meta_code})
    if kind == ErrorClass.RETRYABLE:
        if exc.meta_code in (4, 17, 32, 613):
            return IntegrationRateLimited(str(exc), {"platform": platform, "retry_after": exc.retry_after_s})
        return IntegrationApiError(
            str(exc), platform=platform, http_status=exc.http_status, retryable=True
        )
    return IntegrationApiError(
        str(exc), platform=platform, http_status=exc.http_status, retryable=False
    )

