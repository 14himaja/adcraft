import pytest

from app.meta.errors import MetaError
from app.meta.fake import FakeAdsGateway
from app.meta.publish_checks import DraftIncomplete
from app.meta.publisher import (
    STEPS,
    discard_publish,
    recover_interrupted,
    resume_publish,
    run_publish,
    start_publish,
)
from app.services.image_store import load_image
from tests.integration.publish_helpers import ready_draft

EDGES = ("campaigns", "adsets", "adcreatives", "ads")


async def publish(db, container, campaign) -> dict:
    await start_publish(db, campaign, container=container)
    await run_publish(db, campaign["_id"], container=container)
    return await db.campaigns.find_one({"_id": campaign["_id"]})


def counts(fake) -> list[int]:
    return [len(fake.by_edge(edge)) for edge in EDGES]


async def test_start_moves_to_publishing_with_every_step_pending(db, container):
    campaign = await ready_draft(db, container)
    started = await start_publish(db, campaign, container=container)
    assert started["status"] == "PUBLISHING"
    assert [s["name"] for s in started["publish"]["steps"]] == list(STEPS)
    assert {s["status"] for s in started["publish"]["steps"]} == {"PENDING"}
    assert started["publish"]["status"] == "RUNNING" and started["publish"]["error"] is None


async def test_happy_path_creates_live_instagram_objects(db, container, fake_gateway):
    campaign = await ready_draft(db, container)
    done = await publish(db, container, campaign)
    assert done["status"] == "ACTIVE" and done["publish"]["status"] == "DONE"
    assert all(s["status"] == "DONE" and s["meta_object_id"] for s in done["publish"]["steps"])
    assert set(done["meta"]) == {"campaign_id", "adset_id", "image_hash", "creative_id", "ad_id"}
    assert counts(fake_gateway) == [1, 1, 1, 1]
    # created paused, then campaign, ad set and ad are switched on; creatives have no delivery status
    statuses = {edge: {o["status"] for o in fake_gateway.by_edge(edge)} for edge in EDGES}
    assert statuses == {
        "campaigns": {"ACTIVE"},
        "adsets": {"ACTIVE"},
        "adcreatives": {"PAUSED"},
        "ads": {"ACTIVE"},
    }
    last6 = str(campaign["_id"])[-6:]
    assert sorted(o["name"] for o in fake_gateway.objects.values()) == sorted(
        f"acm-{last6}-{step}" for step in ("CAMPAIGN", "ADSET", "CREATIVE", "AD")
    )
    adset = fake_gateway.by_edge("adsets")[0]["params"]
    assert adset["daily_budget"] == 50_000 and adset["campaign_id"] == done["meta"]["campaign_id"]
    assert adset["targeting"]["publisher_platforms"] == ["instagram"]
    assert adset["targeting"]["geo_locations"] == {"cities": [{"key": "1017930"}]}
    story = fake_gateway.by_edge("adcreatives")[0]["params"]["object_story_spec"]
    assert (story["page_id"], story["instagram_user_id"]) == ("page_fake_1", "ig_fake_1")
    data, _ = await load_image(db, campaign["image_id"], campaign["user_id"])
    assert fake_gateway.images[done["meta"]["image_hash"]] == data


async def test_an_interest_meta_no_longer_confirms_stops_publishing_before_any_meta_write(
    db, container, fake_gateway
):
    interests = [
        {"id": "6003682002118", "name": "Python (programming language)"},
        {"id": "6003139266461", "name": "Software Engineering & Tech"},  # curated, not from Meta
    ]
    audience = {"countries": ["IN"], "cities": [], "age_min": 18, "age_max": 24, "interests": interests}
    campaign = await ready_draft(db, container, audience=audience)
    with pytest.raises(DraftIncomplete, match="Software Engineering & Tech"):
        await start_publish(db, campaign, container=container)
    assert fake_gateway.objects == {}
    assert (await db.campaigns.find_one({"_id": campaign["_id"]}))["status"] == "DRAFT"


@pytest.mark.parametrize(
    ("overrides", "change", "code"),
    [
        ({}, {"image_id": None}, "DRAFT_INCOMPLETE"),
        ({"title": "Cheap home loan offer"}, {}, "SPECIAL_AD_CATEGORY_UNSUPPORTED"),
        ({}, {"objective": "LEADS"}, "OBJECTIVE_UNSUPPORTED"),
        ({"daily_budget_minor": 6_000}, {}, "BUDGET_BELOW_META_MINIMUM"),
        ({}, {"status": "ACTIVE"}, "ILLEGAL_TRANSITION"),
    ],
)
async def test_publish_is_refused_before_any_meta_call(db, container, fake_gateway, overrides, change, code):
    campaign = await ready_draft(db, container, **overrides)
    if change:
        await db.campaigns.update_one({"_id": campaign["_id"]}, {"$set": change})
        campaign = {**campaign, **change}
    with pytest.raises(Exception) as exc:
        await start_publish(db, campaign, container=container)
    assert exc.value.code == code
    assert fake_gateway.objects == {} and fake_gateway.images == {}
    assert (await db.campaigns.find_one({"_id": campaign["_id"]}))["status"] == change.get("status", "DRAFT")


async def test_publish_without_meta_connection_is_refused(db, container):
    campaign = await ready_draft(db, container, connected=False)
    with pytest.raises(Exception) as exc:
        await start_publish(db, campaign, container=container)
    assert exc.value.code == "META_NOT_CONNECTED"


async def test_caps_are_enforced_again_at_publish(db, container):
    campaign = await ready_draft(db, container)
    container.settings = container.settings.model_copy(update={"max_daily_budget_inr": 100})
    with pytest.raises(Exception) as exc:
        await start_publish(db, campaign, container=container)
    assert exc.value.code == "VALIDATION_FAILED" and "at most ₹100" in exc.value.message


async def test_code_100_fails_with_metas_message_and_resume_finishes(db, container, fake_gateway):
    fake_gateway.fail_at["ADSET"] = MetaError(
        http_status=400, meta_code=100, message="Invalid parameter", user_msg="Budget too low for Meta"
    )
    campaign = await ready_draft(db, container)
    failed = await publish(db, container, campaign)
    assert failed["status"] == "PUBLISH_FAILED" and failed["publish"]["status"] == "FAILED"
    assert failed["publish"]["error"] == {
        "step": "ADSET",
        "message": "Budget too low for Meta",
        "meta_code": 100,
    }
    steps = {s["name"]: s for s in failed["publish"]["steps"]}
    assert steps["CAMPAIGN"]["status"] == "DONE" and steps["ADSET"]["status"] == "FAILED"
    assert steps["ADSET"]["attempts"] == 1  # code 100 is never retried

    await resume_publish(db, failed, container=container)
    await run_publish(db, campaign["_id"], container=container)
    done = await db.campaigns.find_one({"_id": campaign["_id"]})
    assert done["status"] == "ACTIVE" and counts(fake_gateway) == [1, 1, 1, 1]


async def test_timeout_after_create_is_adopted_not_duplicated(db, container, fake_gateway):
    fake_gateway.fail_at["ADSET"] = "timeout_after_create"
    done = await publish(db, container, await ready_draft(db, container))
    assert done["status"] == "ACTIVE" and counts(fake_gateway) == [1, 1, 1, 1]
    adset_step = next(s for s in done["publish"]["steps"] if s["name"] == "ADSET")
    assert adset_step["attempts"] == 2


async def test_throttling_is_retried(db, container, fake_gateway):
    fake_gateway.fail_at["CAMPAIGN"] = MetaError(http_status=400, meta_code=17, message="limit")
    done = await publish(db, container, await ready_draft(db, container))
    assert done["status"] == "ACTIVE"


async def test_code_190_fails_and_expires_the_connection(db, container, fake_gateway):
    fake_gateway.fail_at["CREATIVE"] = MetaError(http_status=400, meta_code=190, message="token expired")
    campaign = await ready_draft(db, container)
    failed = await publish(db, container, campaign)
    assert failed["status"] == "PUBLISH_FAILED"
    assert (await db.meta_connections.find_one({"user_id": campaign["user_id"]}))["status"] == "EXPIRED"


async def test_lookup_refused_by_meta_falls_back_to_create(db, container, fake_gateway):
    async def refuse(account_id, edge, name):
        raise MetaError(http_status=400, meta_code=100, message="filtering not supported")

    fake_gateway.find_by_name = refuse
    done = await publish(db, container, await ready_draft(db, container))
    assert done["status"] == "ACTIVE" and counts(fake_gateway) == [1, 1, 1, 1]


async def test_discard_deletes_children_first_and_returns_to_draft(db, container, fake_gateway):
    deleted = []
    original = FakeAdsGateway.delete

    async def recording_delete(object_id):
        deleted.append(fake_gateway.objects[object_id]["edge"])
        await original(fake_gateway, object_id)

    fake_gateway.delete = recording_delete
    fake_gateway.fail_at["AD"] = MetaError(http_status=400, meta_code=100, message="bad ad")
    failed = await publish(db, container, await ready_draft(db, container))
    draft = await discard_publish(db, failed, container=container)
    assert deleted == ["adcreatives", "adsets", "campaigns"]
    assert fake_gateway.objects == {}
    assert (draft["status"], draft["meta"], draft["publish"]) == ("DRAFT", {}, None)


async def test_discard_treats_already_deleted_objects_as_gone(db, container, fake_gateway):
    fake_gateway.fail_at["AD"] = MetaError(http_status=400, meta_code=100, message="bad ad")
    failed = await publish(db, container, await ready_draft(db, container))
    del fake_gateway.objects[failed["meta"]["adset_id"]]  # someone removed it in Ads Manager
    draft = await discard_publish(db, failed, container=container)
    assert draft["status"] == "DRAFT" and fake_gateway.objects == {}


async def test_restart_marks_stuck_publishing_failed_and_it_can_resume(db, container, fake_gateway):
    campaign = await ready_draft(db, container)
    await start_publish(db, campaign, container=container)
    assert await recover_interrupted(db, clock=container.clock) == 1
    stuck = await db.campaigns.find_one({"_id": campaign["_id"]})
    assert stuck["status"] == "PUBLISH_FAILED"
    assert "interrupted by a server restart" in stuck["publish"]["error"]["message"]
    await resume_publish(db, stuck, container=container)
    await run_publish(db, campaign["_id"], container=container)
    assert (await db.campaigns.find_one({"_id": campaign["_id"]}))["status"] == "ACTIVE"
