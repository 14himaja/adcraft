"""Every AdsReader/AdsWriter implementation must pass these tests (Liskov)."""

from datetime import date
from decimal import Decimal

import pytest

from app.meta.errors import ErrorClass, MetaError, classify
from app.meta.ports import AdsReader, AdsWriter, InterestOption
from tests.meta_payloads import m0

CAMPAIGN = {
    "name": "acm-000001-v1-CAMPAIGN",
    "objective": "OUTCOME_TRAFFIC",
    "status": "PAUSED",
    "special_ad_categories": [],
    "is_adset_budget_sharing_enabled": False,
}
# Synthetic: no M0 capture yet; shape from Meta's delivery_estimate docs.
DELIVERY_ESTIMATE = {
    "data": [
        {
            "estimate_mau_lower_bound": 1200000,
            "estimate_mau_upper_bound": 1400000,
            "estimate_ready": True,
        }
    ]
}


def protocol_methods(protocol) -> set[str]:
    return {name for name in vars(protocol) if not name.startswith("_")}


def test_gateway_has_every_port_method(gateway):
    for name in protocol_methods(AdsReader) | protocol_methods(AdsWriter):
        assert callable(getattr(gateway, name, None)), name


async def test_create_returns_an_id(gateway, world, account):
    world.created("campaigns", "120251612314120363")
    assert await gateway.create(account, "campaigns", CAMPAIGN)


async def test_find_by_name_finds_what_was_created(gateway, world, account):
    world.created("campaigns", "120251612314120363")
    object_id = await gateway.create(account, "campaigns", CAMPAIGN)
    world.found("campaigns", object_id)
    assert await gateway.find_by_name(account, "campaigns", CAMPAIGN["name"]) == object_id


async def test_find_by_name_is_none_when_absent(gateway, world, account):
    world.found("campaigns", None)
    assert await gateway.find_by_name(account, "campaigns", "acm-nothing-v1-CAMPAIGN") is None


async def test_update_returns_none(gateway, world, account):
    world.created("campaigns", "120251612314120363")
    object_id = await gateway.create(account, "campaigns", CAMPAIGN)
    world.updated(object_id)
    assert await gateway.update(object_id, {"status": "ACTIVE"}) is None


async def test_delete_removes_the_object(gateway, world, account):
    world.created("campaigns", "120251612314120363")
    object_id = await gateway.create(account, "campaigns", CAMPAIGN)
    world.deleted(object_id)
    await gateway.delete(object_id)
    world.found("campaigns", None)
    assert await gateway.find_by_name(account, "campaigns", CAMPAIGN["name"]) is None


async def test_upload_image_returns_a_hash(gateway, world, account):
    world.replay("POST", f"{account}/adimages", m0("r5_adimages.response"))
    image_hash = await gateway.upload_image(account, b"\xff\xd8 not really a jpeg", "x.jpg")
    assert len(image_hash) == 32


async def test_code_100_raises_an_invalid_meta_error(gateway, world, account):
    world.create_fails("campaigns", m0("r6_campaign_missing_budget_sharing.response"))
    with pytest.raises(MetaError) as exc:
        await gateway.create(account, "campaigns", CAMPAIGN)
    assert classify(exc.value) == ErrorClass.INVALID
    assert exc.value.meta_subcode == 4834011


async def test_search_interests_returns_resolved_options(gateway, world):
    world.replay("GET", "search", m0("r3_search_interest_python.response"))
    options = await gateway.search_interests("python", limit=5)
    assert 1 <= len(options) <= 5
    assert all(isinstance(o, InterestOption) for o in options)
    assert options[0].id == "6003682002118"


async def test_search_locations_returns_keys(gateway, world):
    world.replay("GET", "search", m0("r4_search_location_bengaluru.response"))
    first = (await gateway.search_locations("Bengaluru", "IN"))[0]
    assert first == {"key": "1017930", "name": "Bangalore", "type": "city", "country_code": "IN"}


async def test_list_ad_accounts(gateway, world):
    world.replay("GET", "me/adaccounts", m0("r1_adaccounts.response"))
    account = (await gateway.list_ad_accounts())[0]
    assert account["id"].startswith("act_")
    assert account["currency"] == "INR"
    assert isinstance(account["min_daily_budget_minor"], int)


async def test_list_pages(gateway, world):
    world.replay("GET", "me/accounts", m0("r2_pages.response"))
    assert {"id", "name"} <= set((await gateway.list_pages())[0])


async def test_instagram_account_for_page(gateway, world):
    page = world.PAGE_WITH_INSTAGRAM
    world.replay("GET", page, m0("r2b_instagram_account.response"))
    instagram = await gateway.instagram_account_for_page(page)
    assert instagram["id"] and instagram["username"]


async def test_delivery_estimate(gateway, world, account):
    world.replay("GET", f"{account}/delivery_estimate", DELIVERY_ESTIMATE)
    estimate = await gateway.delivery_estimate(account, {"geo_locations": {"countries": ["IN"]}})
    assert 0 < estimate["lower"] <= estimate["upper"]


INSIGHTS = {  # Synthetic: the M0 capture (r13) had no delivery; field shapes from Meta's insights docs.
    "data": [
        {
            "impressions": "1200",
            "reach": "800",
            "clicks": "30",
            "spend": "152.35",
            "ctr": "2.5",
            "cpc": "5.078333",
            "date_start": "2026-10-07",
            "date_stop": "2026-10-09",
        }
    ]
}
SINCE, UNTIL = date(2026, 10, 7), date(2026, 10, 9)


async def test_insights_of_a_delivered_campaign_are_numeric_strings(gateway, world, account):
    world.created("campaigns", "120251612314120363")
    object_id = await gateway.create(account, "campaigns", CAMPAIGN)
    world.updated(object_id)
    await gateway.update(object_id, {"status": "ACTIVE"})
    world.replay("GET", f"{object_id}/insights", INSIGHTS)
    [row] = await gateway.insights(object_id, SINCE, UNTIL)
    assert all(int(row[key]) > 0 for key in ("impressions", "reach", "clicks"))
    assert Decimal(row["spend"]) > 0 and float(row["ctr"]) > 0


async def test_insights_without_delivery_are_empty(gateway, world, account):
    world.created("campaigns", "120251612314120363")
    object_id = await gateway.create(account, "campaigns", CAMPAIGN)
    world.replay("GET", f"{object_id}/insights", m0("r13_insights.response"))
    assert await gateway.insights(object_id, SINCE, UNTIL) == []


async def test_ad_status_reports_the_effective_status(gateway, world, account):
    world.created("ads", "120254994914340712")
    ad_id = await gateway.create(account, "ads", {"name": "acm-000001-AD", "status": "PAUSED"})
    world.replay("GET", ad_id, m0("r12_ad_status.response"))
    status = await gateway.ad_status(ad_id)
    assert status["effective_status"] in ("PAUSED", "IN_PROCESS")
    assert "review_feedback" in status


async def test_search_locations_needs_a_known_place(gateway, world):
    world.replay("GET", "search", {"data": []})
    assert await gateway.search_locations("Atlantis", "IN") == []


async def test_send_dm_delivers_to_page_messages_edge(gateway, world):
    page_id = "page_fake_1" if hasattr(world, "fake") else world.PAGE_WITH_INSTAGRAM
    world.replay("GET", page_id, {"id": page_id, "access_token": "PAGE-TOKEN"})  # Page's own token
    world.replay("POST", f"{page_id}/messages", {"message_id": "mid_dm_12345"})
    mid = await gateway.send_dm(page_id, "customer_ig_scoped_id", "Hello from Priya Bakery!")
    assert mid.startswith("mid_") or mid.startswith("fake_mid_")


async def test_subscribe_messages_and_status(gateway, world):
    page_id = "page_fake_1" if hasattr(world, "fake") else world.PAGE_WITH_INSTAGRAM
    world.replay("GET", page_id, {"id": page_id, "access_token": "PAGE-TOKEN"})
    world.replay("GET", page_id, {"id": page_id, "access_token": "PAGE-TOKEN"})  # one per Page-level call
    world.replay("POST", f"{page_id}/subscribed_apps", {"success": True})
    world.replay("GET", f"{page_id}/subscribed_apps", {"data": [{"subscribed_fields": ["messages"]}]})
    await gateway.subscribe_messages(page_id)
    assert await gateway.messages_subscribed(page_id) is True
