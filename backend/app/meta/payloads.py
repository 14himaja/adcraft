"""What Meta receives, built only from the stored campaign + saved connection (spec 07 §8)."""

from datetime import UTC, date, datetime, timedelta

from app.domain.rules import OBJECTIVES, PUBLISHER_PLATFORMS

ADVANTAGE_AUDIENCE_OFF = {"advantage_audience": 0}  # v26 requires an explicit choice (M0 r8)
START_MARGIN = timedelta(minutes=10)
GENDERS = {"MEN": [1], "WOMEN": [2]}  # "ALL" -> omitted


def object_name(campaign_id, step: str) -> str:
    return f"acm-{str(campaign_id)[-6:]}-{step}"


def _day_start(value: str) -> datetime:
    return datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=UTC)


def _meta_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S%z")


def campaign_payload(objective: str, name: str) -> dict:
    return {
        "name": name,
        "objective": OBJECTIVES[objective]["objective"],
        "status": "PAUSED",
        "special_ad_categories": [],  # special categories are refused before publishing
        "is_adset_budget_sharing_enabled": False,
    }


def targeting(audience: dict, positions: list[str]) -> dict:
    # Cities replace countries: Meta rejects a city inside a country that is also targeted.
    cities = [{"key": city["key"]} for city in audience.get("cities") or []]
    spec = {
        "geo_locations": {"cities": cities} if cities else {"countries": list(audience["countries"])},
        "age_min": audience.get("age_min", 18),
        "age_max": audience.get("age_max", 65),
    }
    if genders := GENDERS.get(audience.get("genders", "ALL")):
        spec["genders"] = genders
    if interests := audience.get("interests"):
        spec["flexible_spec"] = [{"interests": [{"id": i["id"]} for i in interests]}]
    return {
        **spec,
        "publisher_platforms": list(PUBLISHER_PLATFORMS),
        "instagram_positions": list(positions),
        "targeting_automation": ADVANTAGE_AUDIENCE_OFF,
    }


def adset_payload(
    campaign: dict, campaign_id: str, name: str, *, now: datetime, positions: list[str]
) -> dict:
    goal = OBJECTIVES[campaign["objective"]]
    payload = {
        "name": name,
        "campaign_id": campaign_id,
        "daily_budget": campaign["daily_budget_minor"],
        "start_time": _meta_time(max(_day_start(campaign["start_date"]), now + START_MARGIN)),
        "end_time": _meta_time(_day_start(campaign["end_date"])),
        "billing_event": goal["billing_event"],
        "optimization_goal": goal["optimization_goal"],
        "bid_strategy": goal["bid_strategy"],
        "status": "PAUSED",
        "targeting": targeting(campaign["audience"], positions),
    }
    if goal["optimization_goal"] == "LINK_CLICKS":
        payload["destination_type"] = "WEBSITE"  # as in M0 r8
    return payload


def creative_payload(
    variant: dict,
    *,
    page_id: str,
    instagram_user_id: str,
    link: str,
    image_hash: str,
    name: str,
) -> dict:
    return {
        "name": name,
        "object_story_spec": {
            "page_id": page_id,
            "instagram_user_id": instagram_user_id,
            "link_data": {
                "link": link,
                "message": variant["primary_text"],
                "name": variant["headline"],
                "description": variant["description"],
                "image_hash": image_hash,
                "call_to_action": {"type": variant["call_to_action"], "value": {"link": link}},
            },
        },
    }


def ad_payload(adset_id: str, creative_id: str, name: str) -> dict:
    return {
        "name": name,
        "adset_id": adset_id,
        "creative": {"creative_id": creative_id},
        "status": "PAUSED",
    }
