from app.meta.errors import MetaError
from tests.api.campaign_bodies import MANUAL
from tests.api_helpers import connect_fake_meta, login


async def ready_campaign(client) -> dict:
    await login(client)
    await connect_fake_meta(client)
    res = await client.post("/campaigns", json=MANUAL)
    assert res.status_code == 200, res.text
    campaign = res.json()
    img_res = await client.post(f"/campaigns/{campaign['id']}/image/generate", json={})
    assert img_res.status_code == 200, img_res.text
    return img_res.json()


async def test_publish_starts_and_runs_to_active_on_meta(client):
    campaign = await ready_campaign(client)
    assert campaign["can_publish"] is True

    pub_res = await client.post(f"/campaigns/{campaign['id']}/publish", json={"confirm": True})
    assert pub_res.status_code == 200, pub_res.text
    assert pub_res.json() == {"status": "PUBLISHING"}

    # In tests spawn runs inline, so publish has finished
    poll_res = await client.get(f"/campaigns/{campaign['id']}/publish")
    assert poll_res.status_code == 200, poll_res.text
    pub_block = poll_res.json()
    assert pub_block["status"] == "DONE"
    assert all(s["status"] == "DONE" for s in pub_block["steps"])

    get_res = await client.get(f"/campaigns/{campaign['id']}")
    assert get_res.json()["status"] == "ACTIVE"


async def test_publish_requires_confirm_literal_true(client):
    campaign = await ready_campaign(client)

    assert (await client.post(f"/campaigns/{campaign['id']}/publish", json={})).status_code == 422
    assert (
        await client.post(f"/campaigns/{campaign['id']}/publish", json={"confirm": False})
    ).status_code == 422


async def test_publish_other_users_campaign_returns_404(client, make_client):
    campaign = await ready_campaign(client)

    async with make_client() as other_client:
        await login(other_client, email="other@example.com")
        res = await other_client.post(f"/campaigns/{campaign['id']}/publish", json={"confirm": True})
        assert res.status_code == 404


async def test_publish_resume_and_discard(client, fake_gateway):
    campaign = await ready_campaign(client)
    fake_gateway.fail_at["ADSET"] = MetaError(
        http_status=400, meta_code=100, message="Invalid parameter", user_msg="Meta error 100"
    )

    pub_res = await client.post(f"/campaigns/{campaign['id']}/publish", json={"confirm": True})
    assert pub_res.status_code == 200

    poll_res = await client.get(f"/campaigns/{campaign['id']}/publish")
    assert poll_res.json()["status"] == "FAILED"

    # Discard moves back to DRAFT
    discard_res = await client.post(f"/campaigns/{campaign['id']}/publish/discard")
    assert discard_res.status_code == 200
    assert discard_res.json() == {"status": "DRAFT"}

    c_draft = (await client.get(f"/campaigns/{campaign['id']}")).json()
    assert c_draft["status"] == "DRAFT"

    # Now publish again with failure, then resume
    fake_gateway.fail_at["ADSET"] = MetaError(
        http_status=400, meta_code=100, message="Invalid parameter", user_msg="Meta error 100"
    )
    await client.post(f"/campaigns/{campaign['id']}/publish", json={"confirm": True})

    resume_res = await client.post(f"/campaigns/{campaign['id']}/publish/resume")
    assert resume_res.status_code == 200
    assert resume_res.json() == {"status": "PUBLISHING"}

    poll_done = (await client.get(f"/campaigns/{campaign['id']}/publish")).json()
    assert poll_done["status"] == "DONE"


async def test_publish_is_blocked_under_default_settings(make_client, fake_gateway):
    async with make_client(allow_real_ad_spend=False, safe_mode_no_spend=True) as c:
        campaign = await ready_campaign(c)
        assert campaign["live_delivery_enabled"] is False

        res = await c.post(f"/campaigns/{campaign['id']}/publish", json={"confirm": True})
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "SPEND_BLOCKED"
        assert (await c.get(f"/campaigns/{campaign['id']}")).json()["status"] == "DRAFT"
    assert fake_gateway.objects == {}  # nothing was written to Meta


async def test_publish_pause_resume_with_spend_allowed(client):
    campaign = await ready_campaign(client)
    assert campaign["live_delivery_enabled"] is True
    await client.post(f"/campaigns/{campaign['id']}/publish", json={"confirm": True})
    assert (await client.get(f"/campaigns/{campaign['id']}")).json()["status"] == "ACTIVE"

    # Publishing already started delivery, so there is nothing left to activate
    # (and no confirmation means the request is malformed).
    assert (await client.post(f"/campaigns/{campaign['id']}/activate", json={})).status_code == 422
    again = await client.post(f"/campaigns/{campaign['id']}/activate", json={"confirm": True})
    assert (again.status_code, again.json()["error"]["code"]) == (409, "ILLEGAL_TRANSITION")

    pause_res = await client.post(f"/campaigns/{campaign['id']}/pause")
    assert pause_res.status_code == 200, pause_res.text
    assert pause_res.json()["status"] == "PAUSED"

    resume_res = await client.post(f"/campaigns/{campaign['id']}/resume")
    assert resume_res.status_code == 200, resume_res.text
    assert resume_res.json()["status"] == "ACTIVE"


async def test_delete_campaign_deletes_meta_objects_and_images(client, fake_gateway, db):
    campaign = await ready_campaign(client)
    await client.post(f"/campaigns/{campaign['id']}/publish", json={"confirm": True})
    assert len(fake_gateway.objects) > 0

    del_res = await client.delete(f"/campaigns/{campaign['id']}")
    assert del_res.status_code == 200, del_res.text
    assert del_res.json() == {"status": "DELETED", "id": campaign["id"]}

    assert (await client.get(f"/campaigns/{campaign['id']}")).status_code == 404
    assert len(fake_gateway.objects) == 0

    # GridFS check
    images = await db["images.files"].find({"metadata.campaign_id": campaign["id"]}).to_list(10)
    assert len(images) == 0


async def test_lifecycle_other_users_campaign_returns_404(client, make_client):
    campaign = await ready_campaign(client)
    await client.post(f"/campaigns/{campaign['id']}/publish", json={"confirm": True})

    async with make_client() as other_client:
        await login(other_client, email="other@example.com")
        assert (
            await other_client.post(f"/campaigns/{campaign['id']}/activate", json={"confirm": True})
        ).status_code == 404
        assert (await other_client.post(f"/campaigns/{campaign['id']}/pause")).status_code == 404
        assert (await other_client.post(f"/campaigns/{campaign['id']}/resume")).status_code == 404
        assert (await other_client.delete(f"/campaigns/{campaign['id']}")).status_code == 404
