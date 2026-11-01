import pytest


@pytest.mark.asyncio
async def test_m3_end_to_end_flow(client):
    # 1. Register a user and establish an authenticated session
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "m3_smoke_user@example.com",
            "password": "ValidPassword123!",
        },
    )
    assert register_resp.status_code == 201, register_resp.text

    # Log in to get the session cookie
    login_resp = await client.post(
        "/auth/login",
        json={
            "email": "m3_smoke_user@example.com",
            "password": "ValidPassword123!",
        },
    )
    assert login_resp.status_code == 200, login_resp.text

    # 2. Before connect, connection status should be NOT_CONNECTED
    status_resp = await client.get("/meta/connection")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "NOT_CONNECTED"

    # 3. Assets before connect should raise 409
    assets_unauth = await client.get("/meta/assets")
    assert assets_unauth.status_code == 409
    assert assets_unauth.json()["error"]["code"] == "META_NOT_CONNECTED"

    # 4. Initiate connect in fake mode (redirects to /settings/meta?connected=1)
    connect_resp = await client.get("/meta/connect", follow_redirects=False)
    assert connect_resp.status_code == 302
    assert connect_resp.headers["location"] == "/settings/meta?connected=1"

    # 5. Check connection status after connect
    status_resp_after = await client.get("/meta/connection")
    assert status_resp_after.status_code == 200
    body = status_resp_after.json()
    assert body["status"] == "ACTIVE"
    assert body["mode"] == "fake"
    assert body["ad_account_id"] is None

    # 6. List assets
    assets_resp = await client.get("/meta/assets")
    assert assets_resp.status_code == 200
    assets = assets_resp.json()
    assert len(assets["ad_accounts"]) >= 1
    assert len(assets["pages"]) >= 2
    assert assets["ad_accounts"][0]["id"] == "act_fake_1"

    # 7. Attempt asset selection with a page that has no linked Instagram (page_fake_2)
    invalid_sel = await client.put(
        "/meta/connection",
        json={"ad_account_id": "act_fake_1", "page_id": "page_fake_2"},
    )
    assert invalid_sel.status_code == 422
    assert invalid_sel.json()["error"]["details"]["reason"] == "no_instagram"

    # 8. Valid asset selection with page_fake_1 (linked to ig_fake_1)
    valid_sel = await client.put(
        "/meta/connection",
        json={"ad_account_id": "act_fake_1", "page_id": "page_fake_1"},
    )
    assert valid_sel.status_code == 200
    selected = valid_sel.json()
    assert selected["ad_account_id"] == "act_fake_1"
    assert selected["page_id"] == "page_fake_1"
    assert selected["instagram_user_id"] == "ig_fake_1"

    # 9. Read connection status again to confirm persistence
    status_final = await client.get("/meta/connection")
    assert status_final.status_code == 200
    final_body = status_final.json()
    assert final_body["status"] == "ACTIVE"
    assert final_body["ad_account_id"] == "act_fake_1"
    assert final_body["page_id"] == "page_fake_1"
    assert final_body["instagram_user_id"] == "ig_fake_1"
