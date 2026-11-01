from datetime import UTC, datetime

from bson import ObjectId

from app.meta.payloads import (
    ad_payload,
    adset_payload,
    campaign_payload,
    creative_payload,
    object_name,
    targeting,
)
from tests.factories import SAMPLE_VARIANTS
from tests.meta_payloads import m0

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)
POSITIONS = ["stream", "explore"]
AUDIENCE = {
    "countries": ["IN"],
    "cities": [],
    "age_min": 18,
    "age_max": 24,
    "genders": "ALL",
    "interests": [{"id": "6003682002118", "name": "Python (programming language)"}],
}
CAMPAIGN = {
    "objective": "TRAFFIC",
    "audience": AUDIENCE,
    "daily_budget_minor": 50_000,
    "start_date": "2026-10-10",
    "end_date": "2026-10-13",
}


def test_object_name_is_deterministic():
    cid = ObjectId("6702a1f0c3b9e4a1d2f30001")
    assert object_name(cid, "ADSET") == "acm-f30001-ADSET"
    assert object_name(cid, "ADSET") == object_name(str(cid), "ADSET")


def test_campaign_payload_matches_m0():
    expected = {k: v for k, v in m0("r7_campaign_success.request")["params"].items() if k != "name"}
    payload = campaign_payload("TRAFFIC", "acm-x-CAMPAIGN")
    assert {k: v for k, v in payload.items() if k != "name"} == expected


def test_targeting_countries_instagram_only_and_advantage_audience_off():
    spec = targeting(AUDIENCE, POSITIONS)
    assert spec == {
        "geo_locations": {"countries": ["IN"]},
        "age_min": 18,
        "age_max": 24,
        "flexible_spec": [{"interests": [{"id": "6003682002118"}]}],
        "publisher_platforms": ["instagram"],
        "instagram_positions": ["stream", "explore"],
        "targeting_automation": {"advantage_audience": 0},
    }


def test_targeting_cities_replace_countries_and_genders_map():
    audience = {**AUDIENCE, "cities": [{"key": "1017930", "name": "Bangalore"}], "genders": "WOMEN"}
    spec = targeting({**audience, "interests": []}, POSITIONS)
    assert spec["geo_locations"] == {"cities": [{"key": "1017930"}]}  # same shape as M0 r8
    assert spec["genders"] == [2] and "flexible_spec" not in spec
    assert targeting({**AUDIENCE, "genders": "MEN"}, POSITIONS)["genders"] == [1]


def test_adset_payload_has_the_m0_fields_daily_budget_and_dates():
    m0_params = m0("r8_adset_app_plan.request")["params"]
    payload = adset_payload(CAMPAIGN, "cmp_1", "acm-x-ADSET", now=NOW, positions=POSITIONS)
    assert set(payload) >= set(m0_params) - {"lifetime_budget"}
    assert payload["daily_budget"] == 50_000 and "lifetime_budget" not in payload
    assert (payload["status"], payload["campaign_id"]) == ("PAUSED", "cmp_1")
    assert (payload["optimization_goal"], payload["billing_event"]) == ("LINK_CLICKS", "IMPRESSIONS")
    assert payload["bid_strategy"] == "LOWEST_COST_WITHOUT_CAP"
    assert payload["start_time"] == "2026-10-10T00:00:00+0000"
    assert payload["end_time"] == "2026-10-13T00:00:00+0000"


def test_awareness_adset_optimizes_reach_without_destination():
    payload = adset_payload({**CAMPAIGN, "objective": "AWARENESS"}, "c", "n", now=NOW, positions=POSITIONS)
    assert payload["optimization_goal"] == "REACH" and "destination_type" not in payload


def test_adset_start_is_at_least_ten_minutes_from_now():
    late = datetime(2026, 10, 10, 15, 0, tzinfo=UTC)
    payload = adset_payload(CAMPAIGN, "c", "n", now=late, positions=POSITIONS)
    assert payload["start_time"] == "2026-10-10T15:10:00+0000"


def test_creative_payload_has_page_instagram_account_and_link_data():
    payload = creative_payload(
        SAMPLE_VARIANTS[0],
        page_id="page_1",
        instagram_user_id="ig_1",
        link="https://reviewbot.example.com",
        image_hash="abc",
        name="acm-x-CREATIVE",
    )
    spec = payload["object_story_spec"]
    assert (spec["page_id"], spec["instagram_user_id"]) == ("page_1", "ig_1")
    link_data = spec["link_data"]
    assert link_data["name"] == SAMPLE_VARIANTS[0]["headline"]
    assert link_data["message"] == SAMPLE_VARIANTS[0]["primary_text"]
    assert link_data["description"] == SAMPLE_VARIANTS[0]["description"]
    assert link_data["image_hash"] == "abc"
    assert link_data["call_to_action"] == {
        "type": "LEARN_MORE",
        "value": {"link": "https://reviewbot.example.com"},
    }


def test_ad_payload_is_paused_and_points_at_the_creative():
    assert ad_payload("adset_1", "cr_1", "acm-x-AD") == {
        "name": "acm-x-AD",
        "adset_id": "adset_1",
        "creative": {"creative_id": "cr_1"},
        "status": "PAUSED",
    }
