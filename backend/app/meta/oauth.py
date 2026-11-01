from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.errors import AppError
from app.meta.errors import meta_error_from_body
from app.security.jwt import InvalidToken, decode_token, issue_token

SCOPES = (
    "ads_management",
    "ads_read",
    "business_management",
    "pages_show_list",
    "instagram_basic",
    "instagram_content_publish",  # organic feed posts
    "instagram_manage_messages",  # read and answer DMs
    "pages_messaging",
    "pages_manage_metadata",  # subscribe the Page to webhooks
)
DIALOG_URL = "https://www.facebook.com/{version}/dialog/oauth"
TOKEN_URL = "https://graph.facebook.com/{version}/oauth/access_token"
LONG_LIVED_DEFAULT = timedelta(days=60)
STATE_TTL_MINUTES = 10


class InvalidOAuthState(AppError):
    status, code = 400, "INVALID_OAUTH_STATE"


@dataclass(frozen=True)
class MetaToken:
    access_token: str
    expires_at: datetime


def auth_url(settings: Settings, state: str) -> str:
    params = {
        "client_id": settings.meta_app_id,
        "redirect_uri": settings.meta_redirect_uri,
        "state": state,
        "response_type": "code",
    }
    if settings.meta_login_config_id:  # Facebook Login for Business
        params |= {"config_id": settings.meta_login_config_id, "override_default_response_type": "true"}
    else:
        params["scope"] = ",".join(SCOPES)
    return f"{DIALOG_URL.format(version=settings.meta_api_version)}?{urlencode(params)}"


async def _token_request(settings: Settings, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=10) as http:
        response = await http.get(
            TOKEN_URL.format(version=settings.meta_api_version),
            params={"client_id": settings.meta_app_id, "client_secret": settings.meta_app_secret, **params},
        )
    body = response.json() if response.content else {}
    if response.status_code != 200 or "access_token" not in body:
        raise meta_error_from_body(body, response.status_code)
    return body


async def exchange_code(settings: Settings, code: str, *, now: datetime) -> MetaToken:
    short = await _token_request(settings, {"redirect_uri": settings.meta_redirect_uri, "code": code})
    long = await _token_request(
        settings, {"grant_type": "fb_exchange_token", "fb_exchange_token": short["access_token"]}
    )
    lifetime = timedelta(seconds=long["expires_in"]) if long.get("expires_in") else LONG_LIVED_DEFAULT
    return MetaToken(access_token=long["access_token"], expires_at=now + lifetime)


def _state_secret(settings: Settings) -> str:
    return f"{settings.jwt_secret}:meta_oauth"  # different from the session secret on purpose


def make_state(settings: Settings, user_id) -> str:
    return issue_token(str(user_id), _state_secret(settings), ttl_minutes=STATE_TTL_MINUTES)


def check_state(settings: Settings, state: str, user_id) -> None:
    try:
        claims = decode_token(state, _state_secret(settings))
    except InvalidToken as exc:
        raise InvalidOAuthState(
            "The Meta login link expired or was tampered with. Try connecting again."
        ) from exc
    if claims["sub"] != str(user_id):
        raise InvalidOAuthState("This Meta login was started by a different user.")
