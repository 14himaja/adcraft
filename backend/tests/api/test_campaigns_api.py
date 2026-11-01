from bson import ObjectId

from tests.api.campaign_bodies import MANUAL, VARIANT
from tests.api_helpers import connect_fake_meta, login


async def create(client, body=MANUAL):
    response = await client.post("/campaigns", json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def test_campaign_routes_require_login(client):
    assert (await client.get("/campaigns")).status_code == 401
    assert (await client.post("/campaigns", json=MANUAL)).status_code == 401


async def test_create_saves_a_draft_and_never_calls_meta(client, fake_gateway, db):
    await login(client)
    await connect_fake_meta(client)
    campaign = await create(client)
    assert campaign["status"] == "DRAFT" and campaign["rev"] == 0
    assert (campaign["daily_budget"], campaign["daily_budget_minor"]) == (500.0, 50000)
    assert campaign["audience"]["interests"][0]["id"] == "6003682002118"
    assert campaign["missing_fields"] == ["image_id"]
    assert (campaign["image_url"], campaign["can_publish"], campaign["can_activate"]) == (None, False, False)
    assert "user_id" not in campaign
    assert fake_gateway.objects == {}
    stored = await db.campaigns.find_one({"_id": ObjectId(campaign["id"])})
    assert (stored["schema_version"], stored["missing_fields"]) == (2, ["image_id"])


async def test_create_with_only_a_title_lists_missing_fields(client):
    await login(client)
    campaign = await create(client, {"title": "Just an idea"})
    assert campaign["missing_fields"][0] == "objective"
    assert "variants" in campaign["missing_fields"]


async def test_unsupported_objective_is_rejected(client):
    await login(client)
    response = await client.post("/campaigns", json={**MANUAL, "objective": "LEADS"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "OBJECTIVE_UNSUPPORTED"


async def test_budget_over_the_cap_is_rejected_with_the_reason(client):
    await login(client)
    response = await client.post("/campaigns", json={**MANUAL, "daily_budget": 5000})
    error = response.json()["error"]
    assert (response.status_code, error["code"]) == (422, "VALIDATION_FAILED")
    assert error["details"]["problems"] == ["daily_budget: must be at most ₹1000"]


async def test_get_and_list_return_only_my_campaigns(client):
    await login(client)
    mine = await create(client)
    assert (await client.get(f"/campaigns/{mine['id']}")).json()["title"] == "Python Course Launch"
    assert [c["id"] for c in (await client.get("/campaigns")).json()] == [mine["id"]]
    await login(client, "other@example.com")
    assert (await client.get("/campaigns")).json() == []
    response = await client.get(f"/campaigns/{mine['id']}")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert (await client.get("/campaigns/not-an-id")).status_code == 404


async def test_put_edits_a_draft(client):
    await login(client)
    campaign = await create(client)
    response = await client.put(
        f"/campaigns/{campaign['id']}",
        json={"title": "New title", "daily_budget": 250.5, "variants": [VARIANT, VARIANT]},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert (updated["title"], updated["daily_budget_minor"], updated["rev"]) == ("New title", 25050, 1)
    assert len(updated["variants"]) == 2


async def test_invalid_edit_lists_each_problem(client):
    await login(client)
    campaign = await create(client)
    bad = {**VARIANT, "headline": "H" * 41, "call_to_action": "BUY_NOW"}
    response = await client.put(f"/campaigns/{campaign['id']}", json={"variants": [bad]})
    error = response.json()["error"]
    assert (response.status_code, error["code"]) == (422, "VALIDATION_FAILED")
    assert [p.split(":")[0] for p in error["details"]["problems"]] == [
        "variants.0.headline",
        "variants.0.call_to_action",
    ]
    assert "at most 40 characters" in error["message"]


async def test_published_campaign_cannot_be_edited(client, db):
    await login(client)
    campaign = await create(client)
    await db.campaigns.update_one({"_id": ObjectId(campaign["id"])}, {"$set": {"status": "PAUSED_ON_META"}})
    response = await client.put(f"/campaigns/{campaign['id']}", json={"title": "x"})
    assert (response.status_code, response.json()["error"]["code"]) == (409, "ILLEGAL_TRANSITION")


async def test_duplicate_published_campaign_preserves_image_but_not_meta_state(client, db):
    await login(client)
    source = await create(client)
    await db.campaigns.update_one(
        {"_id": ObjectId(source["id"])},
        {"$set": {"status": "ACTIVE", "image_id": "shared-image", "meta": {"campaign_id": "meta-1"},
                  "publish": {"status": "DONE"}, "insights": {"clicks": 5}}},
    )
    result = await client.post(f"/campaigns/{source['id']}/duplicate")
    assert result.status_code == 200, result.text
    copy = result.json()
    stored = await db.campaigns.find_one({"_id": ObjectId(copy["id"])})
    assert copy["status"] == "DRAFT" and copy["title"].endswith("(copy)")
    assert copy["image_id"] == "shared-image"
    assert stored["meta"] == {} and stored["publish"] is None and stored["insights"] is None


async def test_special_category_idea_gets_a_warning_and_cannot_publish(client):
    await login(client)
    campaign = await create(client, {**MANUAL, "title": "Cheap home loan offer"})
    assert any("special ad category" in w for w in campaign["warnings"])
    assert campaign["can_publish"] is False


async def test_advertiser_can_confirm_an_ad_is_not_a_special_category(client):
    await login(client)
    # Software that helps companies hire is not a job ad, but the keyword check can't tell.
    campaign = await create(client, {**MANUAL, "title": "Narad: hiring automation for recruiters"})
    assert campaign["special_category_reason"]
    response = await client.put(f"/campaigns/{campaign['id']}", json={"not_special_category": True})
    confirmed = response.json()
    assert confirmed["special_category_reason"] is None and confirmed["not_special_category"] is True
    assert not any("special ad category" in w.lower() for w in confirmed["warnings"])


async def test_delete_removes_my_campaign_only(client):
    await login(client)
    campaign = await create(client)
    await login(client, "other@example.com")
    assert (await client.delete(f"/campaigns/{campaign['id']}")).status_code == 404
    await login(client)
    response = await client.delete(f"/campaigns/{campaign['id']}")
    assert response.json() == {"status": "DELETED", "id": campaign["id"]}
    assert (await client.get(f"/campaigns/{campaign['id']}")).status_code == 404


async def test_legacy_campaign_lists_as_draft_and_deletes(client, db, clock):
    await login(client)
    user = await db.users.find_one({"email": "dev@example.com"})
    legacy = {
        "user_id": user["_id"],
        "title": "Old studio ad",
        "objective": "OUTCOME_TRAFFIC",
        "daily_budget": 500.0,
        "currency": "INR",
        "status": "READY_PAUSED",
        "landing_url": "https://synxa.ai",
        "audience": {"country": "IN", "cities": [], "age_min": 18, "age_max": 45, "interests": ["Python"]},
        "creative": {"headline": "Old", "primary_text": "Old text", "call_to_action": "LEARN_MORE"},
        "created_at": clock.now(),
    }
    legacy_id = (await db.campaigns.insert_one(legacy)).inserted_id
    [listed] = (await client.get("/campaigns")).json()
    assert (listed["status"], listed["daily_budget"]) == ("DRAFT", 500.0)
    assert listed["audience"]["countries"] == ["IN"]
    assert listed["audience"]["interests"] == [{"id": "", "name": "Python"}]
    assert listed["variants"][0]["headline"] == "Old"
    assert (await client.delete(f"/campaigns/{legacy_id}")).status_code == 200


async def test_publishing_destinations_can_be_saved_and_serialized(client):
    await login(client)
    destinations = {
        "facebook_feed": True,
        "facebook_story": False,
        "instagram_feed": True,
        "instagram_story": True,
    }
    campaign = await create(client, {**MANUAL, "publishing_destinations": destinations})
    assert campaign["publishing_destinations"] == destinations
    updated = (
        await client.put(
            f"/campaigns/{campaign['id']}",
            json={"publishing_destinations": {**destinations, "facebook_story": True}},
        )
    ).json()
    assert updated["publishing_destinations"]["facebook_story"] is True
