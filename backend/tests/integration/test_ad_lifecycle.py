import pytest
from tenacity import wait_none

from app.container import build_container
from app.domain.ad_states import AdState
from app.meta.errors import MetaError
from app.meta.publisher import run_publish, start_publish
from app.services.ad_lifecycle import (
    ACTIVATE_ORDER,
    DELETE_ORDER,
    SpendBlocked,
    activate,
    delete_meta_objects,
    pause,
    resume,
)
from app.services.transitions import IllegalTransition
from tests.conftest import run_inline
from tests.integration.publish_helpers import ready_draft


async def publish_to_paused_on_meta(db, container, fake_gateway) -> dict:
    """A campaign in the legacy PAUSED_ON_META state (publish now goes straight to ACTIVE)."""
    campaign = await ready_draft(db, container)
    await start_publish(db, campaign, container=container)
    await run_publish(db, campaign["_id"], container=container)
    for obj in fake_gateway.objects.values():
        obj["status"] = "PAUSED"
    legacy = {"$set": {"status": AdState.PAUSED_ON_META.value}}
    await db.campaigns.update_one({"_id": campaign["_id"]}, legacy)
    return await db.campaigns.find_one({"_id": campaign["_id"]})


def make_blocked_container(container, settings, fake_gateway):
    """The default server settings: live delivery switched off."""
    return build_container(
        settings.model_copy(update={"allow_real_ad_spend": False, "safe_mode_no_spend": True}),
        clock=container.clock,
        fake_gateway=fake_gateway,
        image_generator=container.image_generator,
        spawn=run_inline,
        retry_wait=wait_none(),
    )


async def test_activate_is_refused_with_spend_blocked_under_default_settings(
    db, container, settings, fake_gateway
):
    campaign = await publish_to_paused_on_meta(db, container, fake_gateway)
    assert campaign["status"] == AdState.PAUSED_ON_META.value
    blocked = make_blocked_container(container, settings, fake_gateway)

    with pytest.raises(SpendBlocked) as exc_info:
        await activate(db, campaign, container=blocked)

    assert exc_info.value.status == 409
    assert exc_info.value.code == "SPEND_BLOCKED"

    reloaded = await db.campaigns.find_one({"_id": campaign["_id"]})
    assert reloaded["status"] == AdState.PAUSED_ON_META.value
    # Objects on Meta remain PAUSED
    assert all(obj["status"] == "PAUSED" for obj in fake_gateway.objects.values())


async def test_activate_works_when_spend_allowed_updating_ad_then_adset_then_campaign_last(
    db, container, settings, fake_gateway
):
    campaign = await publish_to_paused_on_meta(db, container, fake_gateway)
    spend_container = container

    update_sequence = []
    orig_update = fake_gateway.update

    async def tracking_update(object_id: str, params: dict):
        update_sequence.append((object_id, params.get("status")))
        await orig_update(object_id, params)

    fake_gateway.update = tracking_update

    activated = await activate(db, campaign, container=spend_container)
    assert activated["status"] == AdState.ACTIVE.value

    # Verify order: ad -> adset -> campaign last
    meta = campaign["meta"]
    expected_order = [(meta[key], "ACTIVE") for key in ACTIVATE_ORDER]
    assert update_sequence == expected_order

    reloaded = await db.campaigns.find_one({"_id": campaign["_id"]})
    assert reloaded["status"] == AdState.ACTIVE.value

    # Audit events verified
    audits = await db.audit_log.find({"campaign_id": campaign["_id"]}).to_list(100)
    event_types = [a["event_type"] for a in audits]
    assert "STATE_TRANSITION" in event_types
    assert event_types.count("META_OBJECT_UPDATED") >= 3


async def test_pause_is_always_allowed_even_under_default_settings(db, container, settings, fake_gateway):
    campaign = await publish_to_paused_on_meta(db, container, fake_gateway)
    activated = await activate(db, campaign, container=container)
    blocked = make_blocked_container(container, settings, fake_gateway)

    # Pausing works with live delivery switched off because pausing stops spend
    paused = await pause(db, activated, container=blocked)
    assert paused["status"] == AdState.PAUSED.value

    reloaded = await db.campaigns.find_one({"_id": campaign["_id"]})
    assert reloaded["status"] == AdState.PAUSED.value

    meta_campaign = fake_gateway.objects[campaign["meta"]["campaign_id"]]
    assert meta_campaign["status"] == "PAUSED"


async def test_resume_does_same_spend_check(db, container, settings, fake_gateway):
    campaign = await publish_to_paused_on_meta(db, container, fake_gateway)
    activated = await activate(db, campaign, container=container)
    paused = await pause(db, activated, container=container)
    blocked = make_blocked_container(container, settings, fake_gateway)

    # Under default settings, resume is blocked
    with pytest.raises(SpendBlocked):
        await resume(db, paused, container=blocked)

    # With spend allowed, resume succeeds
    resumed = await resume(db, paused, container=container)
    assert resumed["status"] == AdState.ACTIVE.value

    meta_campaign = fake_gateway.objects[campaign["meta"]["campaign_id"]]
    assert meta_campaign["status"] == "ACTIVE"


async def test_delete_meta_objects_deletes_children_first(db, container, fake_gateway):
    campaign = await publish_to_paused_on_meta(db, container, fake_gateway)
    delete_sequence = []
    orig_delete = fake_gateway.delete

    async def tracking_delete(object_id: str):
        delete_sequence.append(object_id)
        await orig_delete(object_id)

    fake_gateway.delete = tracking_delete

    await delete_meta_objects(db, campaign, container=container, actor="user")

    meta = campaign["meta"]
    expected_delete_order = [meta[key] for key in DELETE_ORDER if key in meta]
    assert delete_sequence == expected_delete_order
    assert len(fake_gateway.objects) == 0

    reloaded = await db.campaigns.find_one({"_id": campaign["_id"]})
    assert not any(k in reloaded.get("meta", {}) for k in DELETE_ORDER)

    audits = await db.audit_log.find(
        {
            "campaign_id": campaign["_id"],
            "event_type": "META_OBJECT_DELETED",
        }
    ).to_list(100)
    assert len(audits) == len(expected_delete_order)


async def test_delete_meta_objects_treats_code_100_as_already_deleted(db, container, fake_gateway):
    campaign = await publish_to_paused_on_meta(db, container, fake_gateway)
    # Inject code 100 on the first deletion
    fake_gateway.fail_at["DELETE"] = MetaError(
        http_status=400, meta_code=100, message="Object fake_ads_1 does not exist"
    )

    # Should not raise
    await delete_meta_objects(db, campaign, container=container, actor="user")
    reloaded = await db.campaigns.find_one({"_id": campaign["_id"]})
    assert not any(k in reloaded.get("meta", {}) for k in DELETE_ORDER)


async def test_lifecycle_refuses_illegal_state_transitions(db, container):
    draft = await ready_draft(db, container)

    with pytest.raises(IllegalTransition):
        await activate(db, draft, container=container)

    with pytest.raises(IllegalTransition):
        await pause(db, draft, container=container)

    with pytest.raises(IllegalTransition):
        await resume(db, draft, container=container)
