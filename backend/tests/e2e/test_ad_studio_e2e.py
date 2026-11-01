import pytest

from app.meta.errors import MetaError
from tests.api_helpers import connect_fake_meta, login

IDEA = "Promote my Python course for college students in Bangalore, https://synxa.ai/python"


@pytest.mark.asyncio
async def test_e2e_main_path(client, make_client, fake_gateway):
    # 1. Register and login
    await login(client, email="e2e_main@example.com")

    # 2. Connect Meta in fake mode
    await connect_fake_meta(client)

    # 3. Create AI draft from idea
    draft_res = await client.post("/campaigns/draft", json={"idea": IDEA})
    assert draft_res.status_code == 200, draft_res.text
    campaign = draft_res.json()
    cid = campaign["id"]
    assert campaign["status"] == "DRAFT"
    assert campaign["can_publish"] is True

    # 4. Edit draft via PUT
    edit_res = await client.put(
        f"/campaigns/{cid}",
        json={"daily_budget": 300, "selected_variant": 1},
    )
    assert edit_res.status_code == 200, edit_res.text
    assert edit_res.json()["daily_budget"] == 300.0
    assert edit_res.json()["selected_variant"] == 1

    # 5. Regenerate image
    regen_res = await client.post(
        f"/campaigns/{cid}/image/generate",
        json={"prompt": "modern bright classroom"},
    )
    assert regen_res.status_code == 200, regen_res.text
    assert regen_res.json()["image_id"] is not None

    # 6. Publish to Meta (starts live delivery)
    pub_res = await client.post(f"/campaigns/{cid}/publish", json={"confirm": True})
    assert pub_res.status_code == 200, pub_res.text
    assert pub_res.json() == {"status": "PUBLISHING"}

    # Poll publish status (runs inline in test container)
    poll_res = await client.get(f"/campaigns/{cid}/publish")
    assert poll_res.status_code == 200, poll_res.text
    pub_block = poll_res.json()
    assert pub_block["status"] == "DONE"
    assert len(pub_block["steps"]) == 5
    assert all(s["status"] == "DONE" for s in pub_block["steps"])

    # Campaign status is ACTIVE
    c_res = await client.get(f"/campaigns/{cid}")
    assert c_res.status_code == 200
    assert c_res.json()["status"] == "ACTIVE"

    # Meta fake objects verification
    assert len(fake_gateway.by_edge("campaigns")) == 1
    assert len(fake_gateway.by_edge("adsets")) == 1
    assert len(fake_gateway.by_edge("adcreatives")) == 1
    assert len(fake_gateway.by_edge("ads")) == 1
    # created paused, then campaign, ad set and ad are switched on
    assert [fake_gateway.by_edge(e)[0]["status"] for e in ("campaigns", "adsets", "ads")] == ["ACTIVE"] * 3

    adset_params = fake_gateway.by_edge("adsets")[0]["params"]
    assert adset_params["targeting"]["publisher_platforms"] == ["instagram"]
    assert adset_params["targeting"]["instagram_positions"] == ["stream"]

    # 7. Publishing already started delivery: insights -> pause -> resume -> delete

    # Refresh insights
    ins_res = await client.post(f"/campaigns/{cid}/insights/refresh")
    assert ins_res.status_code == 200, ins_res.text
    insights = ins_res.json()
    assert insights["impressions"] > 0
    assert insights["spend_minor"] > 0

    # Pause
    pause_res = await client.post(f"/campaigns/{cid}/pause")
    assert pause_res.status_code == 200, pause_res.text
    assert pause_res.json()["status"] == "PAUSED"
    assert fake_gateway.by_edge("campaigns")[0]["status"] == "PAUSED"

    # Resume
    resume_res = await client.post(f"/campaigns/{cid}/resume")
    assert resume_res.status_code == 200, resume_res.text
    assert resume_res.json()["status"] == "ACTIVE"
    assert fake_gateway.by_edge("campaigns")[0]["status"] == "ACTIVE"

    # Delete
    del_res = await client.delete(f"/campaigns/{cid}")
    assert del_res.status_code == 200, del_res.text
    assert del_res.json() == {"status": "DELETED", "id": cid}

    # No objects left in fake
    assert len(fake_gateway.objects) == 0

    # Campaign returns 404
    get_deleted = await client.get(f"/campaigns/{cid}")
    assert get_deleted.status_code == 404


@pytest.mark.asyncio
async def test_e2e_failure_adset_code_100_and_resume(client, fake_gateway):
    await login(client, email="e2e_fail_adset@example.com")
    await connect_fake_meta(client)

    draft_res = await client.post("/campaigns/draft", json={"idea": IDEA})
    cid = draft_res.json()["id"]

    # Inject failure at ADSET
    fake_gateway.fail_at["ADSET"] = MetaError(
        http_status=400, meta_code=100, message="Invalid parameter", user_msg="Budget too low for Meta"
    )

    pub_res = await client.post(f"/campaigns/{cid}/publish", json={"confirm": True})
    assert pub_res.status_code == 200

    poll_res = await client.get(f"/campaigns/{cid}/publish")
    assert poll_res.status_code == 200
    pub_block = poll_res.json()
    assert pub_block["status"] == "FAILED"
    assert pub_block["error"]["message"] == "Budget too low for Meta"

    c_res = await client.get(f"/campaigns/{cid}")
    assert c_res.json()["status"] == "PUBLISH_FAILED"

    # Resume publish finishes successfully
    resume_res = await client.post(f"/campaigns/{cid}/publish/resume")
    assert resume_res.status_code == 200
    assert resume_res.json() == {"status": "PUBLISHING"}

    poll_done = await client.get(f"/campaigns/{cid}/publish")
    assert poll_done.json()["status"] == "DONE"

    c_done = await client.get(f"/campaigns/{cid}")
    assert c_done.json()["status"] == "ACTIVE"
    assert len(fake_gateway.by_edge("campaigns")) == 1
    assert len(fake_gateway.by_edge("adsets")) == 1


@pytest.mark.asyncio
async def test_e2e_failure_adset_timeout_after_create(client, fake_gateway):
    await login(client, email="e2e_timeout@example.com")
    await connect_fake_meta(client)

    draft_res = await client.post("/campaigns/draft", json={"idea": IDEA})
    cid = draft_res.json()["id"]

    # Injected timeout after creating adset; retry adopts by name, so exactly 1 exists
    fake_gateway.fail_at["ADSET"] = "timeout_after_create"

    pub_res = await client.post(f"/campaigns/{cid}/publish", json={"confirm": True})
    assert pub_res.status_code == 200

    poll_done = await client.get(f"/campaigns/{cid}/publish")
    assert poll_done.json()["status"] == "DONE"

    c_done = await client.get(f"/campaigns/{cid}")
    assert c_done.json()["status"] == "ACTIVE"
    assert len(fake_gateway.by_edge("adsets")) == 1


@pytest.mark.asyncio
async def test_e2e_failure_discard(client, fake_gateway):
    await login(client, email="e2e_discard@example.com")
    await connect_fake_meta(client)

    draft_res = await client.post("/campaigns/draft", json={"idea": IDEA})
    cid = draft_res.json()["id"]

    fake_gateway.fail_at["ADSET"] = MetaError(
        http_status=400, meta_code=100, message="Invalid param", user_msg="Meta adset failed"
    )

    await client.post(f"/campaigns/{cid}/publish", json={"confirm": True})
    c_failed = await client.get(f"/campaigns/{cid}")
    assert c_failed.json()["status"] == "PUBLISH_FAILED"
    # Campaign object had been created on Meta
    assert len(fake_gateway.by_edge("campaigns")) == 1

    # Discard removes created objects and returns to DRAFT
    discard_res = await client.post(f"/campaigns/{cid}/publish/discard")
    assert discard_res.status_code == 200
    assert discard_res.json() == {"status": "DRAFT"}

    c_draft = await client.get(f"/campaigns/{cid}")
    assert c_draft.json()["status"] == "DRAFT"
    assert len(fake_gateway.objects) == 0
