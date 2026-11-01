from datetime import UTC, datetime, timedelta

import pytest
from tenacity import wait_none

from app.clock import FixedClock
from app.container import build_container
from app.domain.ad_states import AdState
from app.services import ad_lifecycle
from app.services.insights import RateLimited, check_refresh_rate_limit, collect, refresh_all_active
from tests.conftest import run_inline
from tests.integration.test_ad_lifecycle import publish_to_paused_on_meta


def make_spend_container(container, settings, fake_gateway, clock=None):
    return build_container(
        settings.model_copy(update={"allow_real_ad_spend": True, "safe_mode_no_spend": False}),
        clock=clock or container.clock,
        fake_gateway=fake_gateway,
        image_generator=container.image_generator,
        spawn=run_inline,
        retry_wait=wait_none(),
    )


async def test_collect_calculates_and_stores_insights(db, container, settings, fake_gateway):
    campaign = await publish_to_paused_on_meta(db, container, fake_gateway)
    spend_container = make_spend_container(container, settings, fake_gateway)
    activated = await ad_lifecycle.activate(db, campaign, container=spend_container)

    insights = await collect(db, activated, container=spend_container)
    assert insights["impressions"] > 0
    assert insights["reach"] > 0
    assert insights["clicks"] > 0
    assert insights["spend_minor"] > 0
    assert insights["ctr"] > 0
    assert insights["updated_at"] is not None

    reloaded = await db.campaigns.find_one({"_id": campaign["_id"]})
    assert reloaded["insights"]["spend_minor"] == insights["spend_minor"]
    assert reloaded["meta"]["effective_status"] in ("ACTIVE", "PAUSED")


async def test_collect_marks_past_end_date_as_completed(db, container, settings, fake_gateway):
    campaign = await publish_to_paused_on_meta(db, container, fake_gateway)
    spend_container = make_spend_container(container, settings, fake_gateway)
    await ad_lifecycle.activate(db, campaign, container=spend_container)

    # Set end_date to yesterday relative to future clock
    await db.campaigns.update_one({"_id": campaign["_id"]}, {"$set": {"end_date": "2026-10-10"}})
    future_clock = FixedClock(datetime(2026, 10, 15, 12, 0, tzinfo=UTC))
    future_container = make_spend_container(container, settings, fake_gateway, clock=future_clock)

    fresh = await db.campaigns.find_one({"_id": campaign["_id"]})
    await collect(db, fresh, container=future_container)

    reloaded = await db.campaigns.find_one({"_id": campaign["_id"]})
    assert reloaded["status"] == AdState.COMPLETED.value


async def test_rate_limit_check_enforces_5_minute_window(container):
    clock = container.clock
    now = clock.now()
    recent = {"insights": {"updated_at": now.isoformat()}}

    with pytest.raises(RateLimited) as exc_info:
        check_refresh_rate_limit(recent, clock)
    assert exc_info.value.status == 429
    assert exc_info.value.code == "RATE_LIMITED"

    # 6 minutes later -> passes without error
    old = {"insights": {"updated_at": (now - timedelta(minutes=6)).isoformat()}}
    check_refresh_rate_limit(old, clock)


async def test_refresh_all_active_continues_past_individual_failures(db, container, settings, fake_gateway):
    c1 = await publish_to_paused_on_meta(db, container, fake_gateway)
    c2 = await publish_to_paused_on_meta(db, container, fake_gateway)
    spend_container = make_spend_container(container, settings, fake_gateway)
    await ad_lifecycle.activate(db, c1, container=spend_container)
    await ad_lifecycle.activate(db, c2, container=spend_container)

    # Make c1 fail by corrupting user_id
    await db.campaigns.update_one({"_id": c1["_id"]}, {"$set": {"user_id": "bad_id"}})

    count = await refresh_all_active(db, spend_container)
    assert count == 1  # c2 refreshed successfully despite c1 failure


async def test_collect_counts_the_whole_life_of_the_ad_not_just_the_stored_dates(
    db, container, settings, fake_gateway, monkeypatch
):
    """The start time can be moved in Ads Manager, so delivery may precede the dates stored here."""
    campaign = await publish_to_paused_on_meta(db, container, fake_gateway)
    spend_container = make_spend_container(container, settings, fake_gateway)
    activated = await ad_lifecycle.activate(db, campaign, container=spend_container)
    created = activated["created_at"].date()
    await db.campaigns.update_one(
        {"_id": campaign["_id"]},
        {"$set": {"start_date": (created + timedelta(days=1)).isoformat(),
                  "end_date": (created + timedelta(days=2)).isoformat()}},
    )
    asked = {}
    original = fake_gateway.insights

    async def spy(campaign_id, since, until):
        asked["since"], asked["until"] = since, until
        return await original(campaign_id, since, until)

    monkeypatch.setattr(fake_gateway, "insights", spy)
    await collect(db, await db.campaigns.find_one({"_id": campaign["_id"]}), container=spend_container)

    assert asked["since"] <= created
    assert asked["until"] >= spend_container.clock.now().date()
