from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
import respx
from bson import ObjectId

from app.meta.errors import MetaError
from app.meta.oauth import SCOPES, InvalidOAuthState, auth_url, check_state, exchange_code, make_state
from app.security.jwt import InvalidToken, decode_token

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)
TOKEN_URL = "https://graph.facebook.com/v26.0/oauth/access_token"


@pytest.fixture
def real(settings):
    return settings.model_copy(
        update={"meta_mode": "real", "meta_app_id": "123", "meta_app_secret": "s3cret"}
    )


def query(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_auth_url_has_client_redirect_scopes_state_and_version(real):
    url = auth_url(real, "STATE")
    assert url.startswith("https://www.facebook.com/v26.0/dialog/oauth?")
    q = query(url)
    assert q["client_id"] == "123" and q["state"] == "STATE" and q["response_type"] == "code"
    assert q["redirect_uri"] == real.meta_redirect_uri
    assert q["scope"].split(",") == list(SCOPES)


def test_auth_url_uses_config_id_for_login_for_business(real):
    q = query(auth_url(real.model_copy(update={"meta_login_config_id": "987"}), "S"))
    assert q["config_id"] == "987" and "scope" not in q


@respx.mock
async def test_code_is_exchanged_then_made_long_lived(real):
    respx.get(TOKEN_URL, params__contains={"code": "abc"}).respond(
        json={"access_token": "SHORT", "token_type": "bearer", "expires_in": 3600}
    )
    long_lived = respx.get(TOKEN_URL, params__contains={"grant_type": "fb_exchange_token"}).respond(
        json={"access_token": "LONG", "token_type": "bearer", "expires_in": 5_184_000}
    )
    token = await exchange_code(real, "abc", now=NOW)
    assert token.access_token == "LONG"
    assert token.expires_at == NOW + timedelta(seconds=5_184_000)
    assert long_lived.calls[0].request.url.params["fb_exchange_token"] == "SHORT"


@respx.mock
async def test_missing_expiry_defaults_to_60_days(real):
    respx.get(TOKEN_URL, params__contains={"code": "abc"}).respond(json={"access_token": "SHORT"})
    respx.get(TOKEN_URL, params__contains={"grant_type": "fb_exchange_token"}).respond(
        json={"access_token": "LONG"}
    )
    assert (await exchange_code(real, "abc", now=NOW)).expires_at == NOW + timedelta(days=60)


@respx.mock
async def test_bad_code_raises_meta_error(real):
    respx.get(TOKEN_URL).respond(400, json={"error": {"code": 100, "message": "Invalid verification code"}})
    with pytest.raises(MetaError):
        await exchange_code(real, "bad", now=NOW)


def test_state_round_trip_for_the_same_user(real):
    user = ObjectId()
    check_state(real, make_state(real, user), user)


def test_state_of_another_user_is_rejected(real):
    with pytest.raises(InvalidOAuthState):
        check_state(real, make_state(real, ObjectId()), ObjectId())


def test_garbage_state_is_rejected(real):
    with pytest.raises(InvalidOAuthState):
        check_state(real, "not-a-state", ObjectId())


def test_state_is_not_a_valid_session_token(real):
    with pytest.raises(InvalidToken):
        decode_token(make_state(real, ObjectId()), real.jwt_secret)
