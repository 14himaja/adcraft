from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import respx

from app.security.crypto import decrypt_token
from tests.api_helpers import login

REAL_INTEGRATION_ENV = {
    "social_oauth_mode": "real",
    "meta_mode": "real",
    "meta_app_id": "meta_id",
    "meta_app_secret": "meta_secret",
    "linkedin_client_id": "li_id",
    "linkedin_client_secret": "li_secret",
}


def _state_of(response) -> str:
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


async def test_list_integrations_returns_all_three_platforms(client):
    await login(client)
    res = await client.get("/integrations")
    assert res.status_code == 200
    body = res.json()
    assert body["total_platforms"] == 3
    assert [p["platform"] for p in body["platforms"]] == [
        "facebook",
        "instagram",
        "linkedin",
    ]
    assert all(p["status"] == "NOT_CONNECTED" for p in body["platforms"])


async def test_unconfigured_platform_redirects_cleanly(make_client):
    async with make_client(social_oauth_mode="real", linkedin_client_id="", linkedin_client_secret="") as c:
        await login(c)
        res = await c.get("/integrations/linkedin/connect")
    assert res.status_code == 302
    assert "error=not_configured" in res.headers["location"]
    assert "platform=linkedin" in res.headers["location"]


async def test_real_oauth_redirects_include_state(make_client):
    async with make_client(**REAL_INTEGRATION_ENV) as c:
        await login(c)
        li = await c.get("/integrations/linkedin/connect")
    assert li.headers["location"].startswith("https://www.linkedin.com/oauth/v2/authorization?")
    assert "state=" in li.headers["location"]


@respx.mock
async def test_linkedin_oauth_callback_org_discovery_selection_and_publish(make_client, db, settings):
    respx.post("https://www.linkedin.com/oauth/v2/accessToken").respond(
        json={"access_token": "LI-ACCESS-SECRET", "refresh_token": "LI-REFRESH", "expires_in": 3600, "scope": "openid profile w_member_social r_organization_social w_organization_social"}
    )
    respx.get("https://api.linkedin.com/rest/organizationAcls").respond(
        json={"elements": [{"organization": "urn:li:organization:555", "role": "ADMINISTRATOR"}]}
    )
    respx.get("https://api.linkedin.com/rest/organizations/555").respond(
        json={"localizedName": "Acme Corp", "vanityName": "acme-corp"}
    )
    respx.get("https://api.linkedin.com/v2/userinfo").respond(
        json={"sub": "member1", "name": "Alice Smith", "email": "alice@acme.com"}
    )
    respx.post("https://api.linkedin.com/rest/posts").respond(
        status_code=201, headers={"x-restli-id": "urn:li:share:9988"}
    )
    respx.post("https://api.linkedin.com/oauth/v2/revoke").respond(status_code=200)

    async with make_client(**REAL_INTEGRATION_ENV) as c:
        await login(c)
        state = _state_of(await c.get("/integrations/linkedin/connect"))
        cb = await c.get("/integrations/linkedin/callback", params={"code": "code_li", "state": state})
        assert cb.status_code == 302
        assert "connected=1" in cb.headers["location"]
        assert "platform=linkedin" in cb.headers["location"]

        # Verify encrypted storage & no token exposure
        doc = await db.social_connections.find_one({"platform": "linkedin"})
        assert b"LI-ACCESS-SECRET" not in doc["access_token_ciphertext"]
        assert decrypt_token(settings.token_encryption_key, doc["access_token_ciphertext"]) == "LI-ACCESS-SECRET"

        status = (await c.get("/integrations/linkedin")).json()
        assert status["status"] == "ACTIVE"
        assert "LI-ACCESS-SECRET" not in str(status)

        # Discover both Organization Page and Personal Profile separately
        accts = (await c.get("/integrations/linkedin/accounts")).json()["accounts"]
        assert any(a["account_type"] == "organization" and a["target_id"] == "urn:li:organization:555" for a in accts)
        assert any(a["account_type"] == "personal" and a["target_id"] == "urn:li:person:member1" for a in accts)

        # Select Organization Page
        sel = await c.put("/integrations/linkedin/account", json={"target_id": "urn:li:organization:555"})
        assert sel.status_code == 200
        assert sel.json()["selected_target_name"] == "Acme Corp"

        # Publish organic post
        pub = await c.post(
            "/integrations/publish",
            json={"platforms": ["linkedin"], "text": "Launching our new feature!", "hashtags": ["#SaaS"]},
        )
        assert pub.status_code == 200
        assert pub.json()["results"]["linkedin"]["status"] == "PUBLISHED"
        assert pub.json()["results"]["linkedin"]["platform_post_id"] == "urn:li:share:9988"

        history = (await c.get("/integrations/publish/history")).json()
        assert len(history) == 1 and history[0]["platform"] == "linkedin"

        # Disconnect revokes token and removes record
        disc = await c.post("/integrations/linkedin/disconnect")
        assert disc.status_code == 200 and disc.json()["status"] == "NOT_CONNECTED"
        assert await db.social_connections.find_one({"platform": "linkedin"}) is None


@respx.mock
async def test_linkedin_publish_image_article_and_errors(make_client):
    respx.post("https://www.linkedin.com/oauth/v2/accessToken").respond(
        json={"access_token": "LI-TOK", "refresh_token": "LI-REF", "expires_in": 3600, "scope": "openid profile w_member_social"}
    )
    respx.get("https://api.linkedin.com/rest/organizationAcls").respond(json={"elements": []})
    respx.get("https://api.linkedin.com/v2/userinfo").respond(
        json={"sub": "member99", "name": "Test Poster", "email": "poster@example.com"}
    )
    respx.post("https://api.linkedin.com/rest/images?action=initializeUpload").respond(
        json={"value": {"uploadUrl": "https://upload.linkedin.com/media/123", "image": "urn:li:image:123"}}
    )
    respx.put("https://upload.linkedin.com/media/123").respond(status_code=201)

    post_route = respx.post("https://api.linkedin.com/rest/posts").respond(
        status_code=201, headers={"x-restli-id": "urn:li:share:img99"}
    )

    async with make_client(**REAL_INTEGRATION_ENV) as c:
        await login(c)
        state = _state_of(await c.get("/integrations/linkedin/connect"))
        await c.get("/integrations/linkedin/callback", params={"code": "c_li", "state": state})

        # 1. Publish Article Link
        pub_link = await c.post(
            "/integrations/publish",
            json={"platforms": ["linkedin"], "text": "Check out our site", "link_url": "https://example.com/post"},
        )
        assert pub_link.status_code == 200
        assert pub_link.json()["results"]["linkedin"]["status"] == "PUBLISHED"

        # 2. Publish Image
        import pytest
        from app.config import Settings
        from app.integrations.base.errors import IntegrationAuthExpired
        from app.integrations.base.models import PublishContent
        from app.integrations.registry import get_adapter

        adapter = get_adapter("linkedin")
        conn = (await c.get("/integrations/linkedin")).json()
        img_res = await adapter.publish(
            "LI-TOK",
            PublishContent(text="Image caption", image_bytes=b"fake-image-bytes", target_id="urn:li:person:member99"),
            conn,
            Settings(
                _env_file=None,
                mongodb_uri="mongodb://localhost:27017",
                jwt_secret="x" * 32,
                token_encryption_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            ),
        )
        assert img_res.status == "PUBLISHED"
        assert img_res.platform_post_id == "urn:li:share:img99"

        # 3. Provider 401 error raises IntegrationAuthExpired
        post_route.respond(status_code=401, json={"message": "Expired access token"})
        with pytest.raises(IntegrationAuthExpired):
            await adapter.publish(
                "LI-TOK",
                PublishContent(text="Should fail with 401", target_id="urn:li:person:member99"),
                conn,
                Settings(
                    _env_file=None,
                    mongodb_uri="mongodb://localhost:27017",
                    jwt_secret="x" * 32,
                    token_encryption_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
                ),
            )


async def test_oauth_cancellation_and_cross_user_state_rejection(make_client):
    async with make_client(**REAL_INTEGRATION_ENV) as alice, make_client(**REAL_INTEGRATION_ENV) as mallory:
        await login(mallory, "mallory@example.com")
        mallory_state = _state_of(await mallory.get("/integrations/linkedin/connect"))

        await login(alice, "alice@example.com")
        denied = await alice.get(
            "/integrations/linkedin/callback",
            params={"error": "access_denied", "state": "ignored"},
        )
        assert denied.status_code == 302 and "error=denied" in denied.headers["location"]

        hijack = await alice.get(
            "/integrations/linkedin/callback",
            params={"code": "abc", "state": mallory_state},
        )
        assert hijack.status_code == 400 and hijack.json()["error"]["code"] == "INVALID_OAUTH_STATE"


async def test_multi_tenant_and_workspace_isolation(make_client):
    async with make_client(social_oauth_mode="fake", meta_mode="fake") as alice, make_client(
        social_oauth_mode="fake", meta_mode="fake"
    ) as bob:
        await login(alice, "alice@synxait.in")
        await login(bob, "bob@example.com")

        # Alice connects LinkedIn in default synxait workspace
        await alice.get("/integrations/linkedin/connect")
        alice_synxait = (await alice.get("/integrations")).json()
        assert next(p for p in alice_synxait["platforms"] if p["platform"] == "linkedin")["status"] == "ACTIVE"

        # Bob does NOT see Alice's connection
        bob_conns = (await bob.get("/integrations")).json()
        assert next(p for p in bob_conns["platforms"] if p["platform"] == "linkedin")["status"] == "NOT_CONNECTED"

        # Alice switches to personal workspace -> isolated from synxait workspace
        await alice.post("/auth/workspace/switch", json={"workspace_id": "personal"})
        alice_personal = (await alice.get("/integrations")).json()
        assert next(p for p in alice_personal["platforms"] if p["platform"] == "linkedin")["status"] == "NOT_CONNECTED"


async def test_instagram_and_facebook_independent_disconnect(make_client):
    async with make_client(social_oauth_mode="fake", meta_mode="fake") as c:
        await login(c)
        await c.get("/integrations/instagram/connect")
        await c.get("/integrations/facebook/connect")

        both = (await c.get("/integrations")).json()["platforms"]
        assert next(p for p in both if p["platform"] == "instagram")["status"] == "ACTIVE"
        assert next(p for p in both if p["platform"] == "facebook")["status"] == "ACTIVE"

        # Disconnecting Instagram must NOT disconnect Facebook
        await c.post("/integrations/instagram/disconnect")
        after = (await c.get("/integrations")).json()["platforms"]
        assert next(p for p in after if p["platform"] == "instagram")["status"] == "NOT_CONNECTED"
        assert next(p for p in after if p["platform"] == "facebook")["status"] == "ACTIVE"


@respx.mock
async def test_token_expiration_and_auto_refresh(make_client, db, clock, settings):
    respx.post("https://www.linkedin.com/oauth/v2/accessToken").respond(
        json={"access_token": "LI-NEW-TOKEN", "refresh_token": "LI-NEW-REF", "expires_in": 3600}
    )
    respx.get("https://api.linkedin.com/rest/organizationAcls").respond(json={"elements": []})
    respx.get("https://api.linkedin.com/v2/userinfo").respond(json={"sub": "m1", "name": "Refreshed User"})

    async with make_client(**{**REAL_INTEGRATION_ENV, "social_oauth_mode": "fake"}) as c:
        await login(c)
        await c.get("/integrations/linkedin/connect")
        # Force record to real mode & expired timestamp with a refresh token
        from app.security.crypto import encrypt_token
        await db.social_connections.update_one(
            {"platform": "linkedin"},
            {
                "$set": {
                    "mode": "real",
                    "token_expires_at": clock.now() - timedelta(hours=1),
                    "refresh_token_ciphertext": encrypt_token(settings.token_encryption_key, "LI-OLD-REF"),
                }
            },
        )
        accts = await c.get("/integrations/linkedin/accounts")
        assert accts.status_code == 200
        assert accts.json()["accounts"][0]["target_name"] == "Refreshed User"

        # Without a refresh token, expiry returns 409 PLATFORM_AUTH_EXPIRED
        await db.social_connections.update_one(
            {"platform": "linkedin"},
            {
                "$set": {"token_expires_at": clock.now() - timedelta(hours=1)},
                "$unset": {"refresh_token_ciphertext": ""},
            },
        )
        expired = await c.get("/integrations/linkedin/accounts")
        assert expired.status_code == 409 and expired.json()["error"]["code"] == "PLATFORM_AUTH_EXPIRED"


async def test_multi_platform_publish_partial_failure_and_advertising_separation(make_client):
    async with make_client(social_oauth_mode="fake", meta_mode="fake") as c:
        await login(c)
        await c.get("/integrations/linkedin/connect")
        await c.get("/integrations/facebook/connect")
        # Instagram is NOT connected

        preview = await c.post(
            "/integrations/publish/preview",
            json={"platforms": ["linkedin", "facebook", "instagram"], "text": "Hello multi-platform!"},
        )
        assert preview.status_code == 200
        assert preview.json()["previews"]["linkedin"]["valid"] is True
        assert preview.json()["previews"]["facebook"]["valid"] is True
        assert preview.json()["previews"]["instagram"]["valid"] is False

        pub = await c.post(
            "/integrations/publish",
            json={"platforms": ["linkedin", "facebook", "instagram"], "text": "Hello multi-platform!"},
        )
        assert pub.status_code == 200
        results = pub.json()["results"]
        assert results["linkedin"]["status"] == "PUBLISHED"
        assert results["facebook"]["status"] == "PUBLISHED"
        assert results["instagram"]["status"] == "FAILED"

        # Verify paid advertising remains separate and gated even when organic is connected
        ads = (await c.get("/integrations/advertising/platforms")).json()
        li_ads = next(p for p in ads["platforms"] if p["id"] == "linkedin_ads")
        assert li_ads["organic_connected"] is True
        assert li_ads["status"] == "REQUIRES_API_APPROVAL"
        assert "campaign_creation" in li_ads["gated_features"]


async def test_unauthenticated_connect_redirects_to_login_with_target_param(client):
    res = await client.get("/integrations/linkedin/connect?return_to=/settings/connections")
    assert res.status_code == 302
    assert res.headers["location"].startswith("/login?redirect=")
    assert "%2Fintegrations%2Flinkedin%2Fconnect" in res.headers["location"]
    assert "%2Fsettings%2Fconnections" in res.headers["location"]


async def test_unauthenticated_callback_rejected_and_no_cookie_issued(make_client, db):
    async with make_client(**REAL_INTEGRATION_ENV) as c:
        await login(c)
        conn_res = await c.get("/integrations/linkedin/connect?return_to=/settings/connections")
        state = _state_of(conn_res)

        # Clear session cookies to simulate unauthenticated request
        c.cookies.clear()

        # Unauthenticated callback with code and state must NOT log the user in
        cb = await c.get("/integrations/linkedin/callback", params={"code": "auth_code_123", "state": state})
        assert cb.status_code == 302
        assert "/login" in cb.headers["location"]
        assert "error=session_expired" in cb.headers["location"]
        assert "session" not in cb.cookies

        # Attack scenario from B-1: callback with error=... and state must NOT issue a session cookie
        cb_err = await c.get("/integrations/linkedin/callback", params={"error": "access_denied", "state": state})
        assert cb_err.status_code == 302
        assert "/login" in cb_err.headers["location"]
        assert "error=session_expired" in cb_err.headers["location"]
        assert "session" not in cb_err.cookies


@respx.mock
async def test_publish_linkedin_401_marks_connection_expired(make_client, db):
    respx.post("https://api.linkedin.com/rest/posts").respond(
        status_code=401, json={"message": "Revoked or expired access token"}
    )
    async with make_client(social_oauth_mode="fake") as c:
        await login(c)
        await c.get("/integrations/linkedin/connect")

        # Set connection mode to real so it attempts real API call
        await db.social_connections.update_one(
            {"platform": "linkedin"},
            {"$set": {"mode": "real", "selected_target_id": "urn:li:person:me"}},
        )

        pub = await c.post(
            "/integrations/publish",
            json={"platforms": ["linkedin"], "text": "Post that triggers 401"},
        )
        assert pub.status_code == 200
        res = pub.json()["results"]["linkedin"]
        assert res["status"] == "FAILED"
        assert res["error_code"] == "PLATFORM_AUTH_EXPIRED"

        # Verify connection status is now EXPIRED in database
        doc = await db.social_connections.find_one({"platform": "linkedin"})
        assert doc is not None
        assert doc["status"] == "EXPIRED"

        # Verify GET /integrations shows expired
        li_status = (await c.get("/integrations")).json()["platforms"]
        li_conn = next(p for p in li_status if p["platform"] == "linkedin")
        assert li_conn["status"] == "EXPIRED"


async def test_publish_unknown_client_target_rejected(make_client, monkeypatch):
    from app.integrations.linkedin.adapter import LinkedInAdapter

    called = []

    async def fake_publish(*args, **kwargs):
        called.append(True)
        return None

    monkeypatch.setattr(LinkedInAdapter, "publish", fake_publish)

    async with make_client(social_oauth_mode="fake") as c:
        await login(c)
        await c.get("/integrations/linkedin/connect")
        pub = await c.post(
            "/integrations/publish",
            json={
                "platforms": ["linkedin"],
                "text": "Hello world",
                "targets": {"linkedin": "urn:li:organization:unauthorized_999"},
            },
        )
        assert pub.status_code == 200
        res = pub.json()["results"]["linkedin"]
        assert res["status"] == "FAILED"
        assert res["error_code"] == "TARGET_NOT_ALLOWED"
        assert len(called) == 0  # adapter is not called


async def test_publish_no_selected_target_rejected(make_client, db):
    async with make_client(social_oauth_mode="fake") as c:
        await login(c)
        await c.get("/integrations/linkedin/connect")

        # Clear selected target and platform account id
        await db.social_connections.update_one(
            {"platform": "linkedin"},
            {"$set": {"selected_target_id": None, "platform_account_id": None}},
        )

        pub = await c.post(
            "/integrations/publish",
            json={"platforms": ["linkedin"], "text": "Hello without target"},
        )
        assert pub.status_code == 200
        res = pub.json()["results"]["linkedin"]
        assert res["status"] == "FAILED"
        assert res["error_code"] == "NO_TARGET_SELECTED"


async def test_publish_client_sends_selected_target(make_client):
    async with make_client(social_oauth_mode="fake") as c:
        await login(c)
        await c.get("/integrations/linkedin/connect")

        conns = (await c.get("/integrations")).json()["platforms"]
        li = next(p for p in conns if p["platform"] == "linkedin")
        target_id = li["selected_target_id"] or li["account_id"]

        pub = await c.post(
            "/integrations/publish",
            json={
                "platforms": ["linkedin"],
                "text": "Hello with valid target",
                "targets": {"linkedin": target_id},
            },
        )
        assert pub.status_code == 200
        res = pub.json()["results"]["linkedin"]
        assert res["status"] == "PUBLISHED"
