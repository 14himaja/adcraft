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
    "x_client_id": "x_id",
    "x_client_secret": "x_secret",
    "pinterest_client_id": "pin_id",
    "pinterest_client_secret": "pin_secret",
    "reddit_client_id": "rd_id",
    "reddit_client_secret": "rd_secret",
}


def _state_of(response) -> str:
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


async def test_list_integrations_returns_all_six_platforms(client):
    await login(client)
    res = await client.get("/integrations")
    assert res.status_code == 200
    body = res.json()
    assert body["total_platforms"] == 6
    assert [p["platform"] for p in body["platforms"]] == [
        "instagram",
        "facebook",
        "linkedin",
        "x",
        "pinterest",
        "reddit",
    ]
    assert all(p["status"] == "NOT_CONNECTED" for p in body["platforms"])


async def test_unconfigured_platform_redirects_cleanly(make_client):
    async with make_client(social_oauth_mode="real", linkedin_client_id="", linkedin_client_secret="") as c:
        await login(c)
        res = await c.get("/integrations/linkedin/connect")
    assert res.status_code == 302
    assert "error=not_configured" in res.headers["location"]
    assert "platform=linkedin" in res.headers["location"]


async def test_real_oauth_redirects_include_state_and_pkce_for_x(make_client):
    async with make_client(**REAL_INTEGRATION_ENV) as c:
        await login(c)
        li = await c.get("/integrations/linkedin/connect")
        x = await c.get("/integrations/x/connect")
        pin = await c.get("/integrations/pinterest/connect")
        rd = await c.get("/integrations/reddit/connect")
    assert li.headers["location"].startswith("https://www.linkedin.com/oauth/v2/authorization?")
    assert x.headers["location"].startswith("https://x.com/i/oauth2/authorize?")
    assert "code_challenge=" in x.headers["location"]
    assert pin.headers["location"].startswith("https://www.pinterest.com/oauth/?")
    assert rd.headers["location"].startswith("https://www.reddit.com/api/v1/authorize?")


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
async def test_x_pinterest_reddit_oauth_and_discovery(make_client):
    # X
    respx.post("https://api.x.com/2/oauth2/token").respond(
        json={"access_token": "X-TOK", "refresh_token": "X-REF", "expires_in": 7200, "scope": "tweet.read tweet.write users.read offline.access"}
    )
    respx.get("https://api.x.com/2/users/me").respond(
        json={"data": {"id": "x_1", "name": "AdCraft X", "username": "adcraft_x"}}
    )
    # Pinterest
    respx.post("https://api.pinterest.com/v5/oauth/token").respond(
        json={"access_token": "PIN-TOK", "refresh_token": "PIN-REF", "expires_in": 3600, "scope": "user_accounts:read,boards:read,pins:write"}
    )
    respx.get("https://api.pinterest.com/v5/user_account").respond(
        json={"id": "pin_u1", "username": "adcraft_pin", "account_type": "BUSINESS"}
    )
    respx.get("https://api.pinterest.com/v5/boards").respond(
        json={"items": [{"id": "b_1", "name": "Summer Ideas", "privacy": "PUBLIC"}]}
    )
    # Reddit
    respx.post("https://www.reddit.com/api/v1/access_token").respond(
        json={"access_token": "RD-TOK", "refresh_token": "RD-REF", "expires_in": 3600, "scope": "identity mysubreddits submit read"}
    )
    respx.get("https://oauth.reddit.com/api/v1/me").respond(json={"id": "rd_u1", "name": "adcraft_rd"})
    respx.get("https://oauth.reddit.com/subreddits/mine/subscriber").respond(
        json={"data": {"children": [{"data": {"display_name": "saasmarketing", "submission_type": "any"}}]}}
    )

    async with make_client(**REAL_INTEGRATION_ENV) as c:
        await login(c)
        for plat, code in [("x", "c_x"), ("pinterest", "c_pin"), ("reddit", "c_rd")]:
            st = _state_of(await c.get(f"/integrations/{plat}/connect"))
            cb = await c.get(f"/integrations/{plat}/callback", params={"code": code, "state": st})
            assert cb.status_code == 302 and "connected=1" in cb.headers["location"]

        pin_accts = (await c.get("/integrations/pinterest/accounts")).json()["accounts"]
        assert pin_accts[0]["target_id"] == "b_1"

        rd_accts = (await c.get("/integrations/reddit/accounts")).json()["accounts"]
        assert any(a["target_id"] == "saasmarketing" for a in rd_accts)


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
        await login(alice, "alice@example.com")
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
async def test_token_expiration_and_auto_refresh(make_client, db, clock):
    respx.post("https://www.linkedin.com/oauth/v2/accessToken").respond(
        json={"access_token": "LI-NEW-TOKEN", "refresh_token": "LI-NEW-REF", "expires_in": 3600}
    )
    respx.get("https://api.linkedin.com/rest/organizationAcls").respond(json={"elements": []})
    respx.get("https://api.linkedin.com/v2/userinfo").respond(json={"sub": "m1", "name": "Refreshed User"})

    async with make_client(**{**REAL_INTEGRATION_ENV, "social_oauth_mode": "fake"}) as c:
        await login(c)
        await c.get("/integrations/linkedin/connect")
        # Force record to real mode & expired timestamp with a refresh token
        await db.social_connections.update_one(
            {"platform": "linkedin"},
            {"$set": {"mode": "real", "token_expires_at": clock.now() - timedelta(hours=1)}},
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
        await c.get("/integrations/x/connect")
        # Pinterest is NOT connected

        preview = await c.post(
            "/integrations/publish/preview",
            json={"platforms": ["linkedin", "x", "pinterest"], "text": "Hello multi-platform!"},
        )
        assert preview.status_code == 200
        assert preview.json()["previews"]["linkedin"]["valid"] is True
        assert preview.json()["previews"]["x"]["valid"] is True
        assert preview.json()["previews"]["pinterest"]["valid"] is False

        pub = await c.post(
            "/integrations/publish",
            json={"platforms": ["linkedin", "x", "pinterest"], "text": "Hello multi-platform!"},
        )
        assert pub.status_code == 200
        results = pub.json()["results"]
        assert results["linkedin"]["status"] == "PUBLISHED"
        assert results["x"]["status"] == "PUBLISHED"
        assert results["pinterest"]["status"] == "FAILED"

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


@respx.mock
async def test_unauthenticated_callback_restores_user_from_signed_state(make_client, db):
    respx.post("https://www.linkedin.com/oauth/v2/accessToken").respond(
        json={"access_token": "LI-RESTORED-TOKEN", "refresh_token": "LI-RESTORED-REF", "expires_in": 3600, "scope": "openid profile"}
    )
    respx.get("https://api.linkedin.com/rest/organizationAcls").respond(json={"elements": []})
    respx.get("https://api.linkedin.com/v2/userinfo").respond(
        json={"sub": "restored_member", "name": "Restored User", "email": "restored@example.com"}
    )

    async with make_client(**REAL_INTEGRATION_ENV) as c:
        await login(c)
        # Obtain signed state token tied to the user
        conn_res = await c.get("/integrations/linkedin/connect?return_to=/settings/connections")
        state = _state_of(conn_res)

        # Clear session cookies to simulate cross-site cookie drop on OAuth redirect
        c.cookies.clear()

        cb = await c.get("/integrations/linkedin/callback", params={"code": "auth_code_123", "state": state})
        assert cb.status_code == 302
        assert "connected=1" in cb.headers["location"]
        assert "platform=linkedin" in cb.headers["location"]
        assert "/settings/connections" in cb.headers["location"]

        # Verify session cookie was restored
        assert "session" in cb.cookies
        doc = await db.social_connections.find_one({"platform": "linkedin"})
        assert doc is not None
