from urllib.parse import parse_qs, urlparse

import respx

from app.security.crypto import decrypt_token
from tests.api_helpers import connect_fake_meta, login

REAL = {"meta_mode": "real", "meta_app_id": "123", "meta_app_secret": "s3cret"}
TOKEN_URL = "https://graph.facebook.com/v26.0/oauth/access_token"


def state_of(response) -> str:
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


async def test_connect_requires_login(client):
    assert (await client.get("/meta/connect")).status_code == 401


async def test_fake_mode_connect_creates_a_fake_connection(client):
    await login(client)
    response = await client.get("/meta/connect")
    assert response.status_code == 302 and response.headers["location"] == "/settings/meta?connected=1"
    view = (await client.get("/meta/connection")).json()
    assert (view["status"], view["mode"]) == ("ACTIVE", "fake")
    assert "token_ciphertext" not in view


async def test_real_mode_connect_redirects_to_meta_with_state(make_client):
    async with make_client(**REAL) as client:
        await login(client)
        response = await client.get("/meta/connect")
    assert response.headers["location"].startswith("https://www.facebook.com/v26.0/dialog/oauth?")
    assert state_of(response)


@respx.mock
async def test_callback_exchanges_code_and_stores_token_encrypted(make_client, db, settings):
    respx.get(TOKEN_URL, params__contains={"code": "abc"}).respond(json={"access_token": "SHORT"})
    respx.get(TOKEN_URL, params__contains={"grant_type": "fb_exchange_token"}).respond(
        json={"access_token": "EAAB-LONG", "expires_in": 5_184_000}
    )
    async with make_client(**REAL) as client:
        await login(client)
        state = state_of(await client.get("/meta/connect"))
        response = await client.get("/meta/callback", params={"code": "abc", "state": state})
    assert response.status_code == 302 and response.headers["location"] == "/settings/meta?connected=1"
    doc = await db.meta_connections.find_one({})
    assert decrypt_token(settings.token_encryption_key, doc["token_ciphertext"]) == "EAAB-LONG"
    assert doc["mode"] == "real"


async def test_callback_rejects_a_bad_state(make_client):
    async with make_client(**REAL) as client:
        await login(client)
        response = await client.get("/meta/callback", params={"code": "abc", "state": "forged"})
    assert response.status_code == 400 and response.json()["error"]["code"] == "INVALID_OAUTH_STATE"


async def test_callback_rejects_another_users_state(make_client):
    async with make_client(**REAL) as alice, make_client(**REAL) as mallory:
        await login(mallory, "mallory@example.com")
        state = state_of(await mallory.get("/meta/connect"))
        await login(alice, "alice@example.com")
        response = await alice.get("/meta/callback", params={"code": "abc", "state": state})
    assert response.status_code == 400


async def test_denied_consent_goes_back_to_settings(make_client):
    async with make_client(**REAL) as client:
        await login(client)
        response = await client.get("/meta/callback", params={"error": "access_denied", "state": "x"})
    assert response.headers["location"] == "/settings/meta?error=denied"


async def test_state_cannot_be_used_as_a_session_cookie(make_client):
    async with make_client(**REAL) as client:
        await login(client)
        state = state_of(await client.get("/meta/connect"))
        client.cookies.clear()
        client.cookies.set("session", state)
        assert (await client.get("/auth/me")).status_code == 401


async def test_assets_include_the_instagram_account_per_page(client):
    await login(client)
    await client.get("/meta/connect")
    assets = (await client.get("/meta/assets")).json()
    assert assets["ad_accounts"][0]["id"] == "act_fake_1"
    by_id = {page["id"]: page for page in assets["pages"]}
    assert by_id["page_fake_1"]["instagram"]["id"] == "ig_fake_1"
    assert by_id["page_fake_1"]["instagram"]["username"] == "fake_brand"
    assert by_id["page_fake_2"]["instagram"] is None


async def test_selection_is_saved(client):
    await login(client)
    await connect_fake_meta(client)
    view = (await client.get("/meta/connection")).json()
    assert (view["ad_account_id"], view["page_id"], view["instagram_username"]) == (
        "act_fake_1",
        "page_fake_1",
        "fake_brand",
    )


async def test_page_without_instagram_is_rejected(client):
    await login(client)
    await client.get("/meta/connect")
    response = await client.put(
        "/meta/connection", json={"ad_account_id": "act_fake_1", "page_id": "page_fake_2"}
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_SELECTION"


async def test_unknown_ad_account_is_rejected(client):
    await login(client)
    await client.get("/meta/connect")
    response = await client.put(
        "/meta/connection", json={"ad_account_id": "act_999", "page_id": "page_fake_1"}
    )
    assert response.status_code == 422


async def test_assets_without_connection_is_409(client):
    await login(client)
    response = await client.get("/meta/assets")
    assert response.status_code == 409 and response.json()["error"]["code"] == "META_NOT_CONNECTED"
