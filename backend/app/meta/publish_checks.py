"""Checks that run before the first Meta write of a publish (spec 07 §4, §8)."""

import re

from app.clock import Clock
from app.config import Settings
from app.domain.ad_campaign import from_minor, missing_fields
from app.domain.rules import OBJECTIVES
from app.errors import AppError
from app.meta.connections import MetaNotConnected
from app.meta.ports import AdsReader
from app.services.ad_campaigns import ObjectiveUnsupported, special_reason
from app.services.ad_lifecycle import check_caps

MAX_INTERESTS = 5
INTEREST_SEARCH_LIMIT = 25


class DraftIncomplete(AppError):
    status, code = 422, "DRAFT_INCOMPLETE"


class SpecialCategoryUnsupported(AppError):
    status, code = 422, "SPECIAL_AD_CATEGORY_UNSUPPORTED"


class BudgetBelowMetaMinimum(AppError):
    status, code = 422, "BUDGET_BELOW_META_MINIMUM"


def check_publishable(campaign: dict, connection: dict, settings: Settings, clock: Clock) -> None:
    if campaign.get("objective") not in OBJECTIVES:
        raise ObjectiveUnsupported(
            f"Objective {campaign.get('objective')!r} is not supported yet; use TRAFFIC or AWARENESS",
            {"supported": sorted(OBJECTIVES)},
        )
    if missing := missing_fields(campaign):
        raise DraftIncomplete(
            f"Add these before publishing: {', '.join(missing)}", {"missing_fields": missing}
        )
    interests = (campaign.get("audience") or {}).get("interests") or []
    if len(interests) > MAX_INTERESTS:
        raise DraftIncomplete(
            f"Choose no more than {MAX_INTERESTS} Meta interests before publishing.",
            {"max_interests": MAX_INTERESTS},
        )
    if reason := special_reason(campaign):
        raise SpecialCategoryUnsupported(f"This ad can't be published: it {reason}.", {"reason": reason})
    check_caps(campaign, settings, clock)
    minimum = connection.get("min_daily_budget_minor")
    if minimum and campaign["daily_budget_minor"] < minimum:
        raise BudgetBelowMetaMinimum(
            f"Meta needs a daily budget of at least ₹{from_minor(minimum):g} for this ad account",
            {"min_daily_budget": from_minor(minimum)},
        )
    if not connection.get("instagram_user_id") or connection["instagram_user_id"] == "none":
        raise MetaNotConnected("Link an Instagram professional account to your Page in Settings first")


class InstagramProfileIncomplete(AppError):
    status, code = 422, "INSTAGRAM_PROFILE_INCOMPLETE"


async def check_instagram_profile(reader: AdsReader, page_id: str) -> None:
    """Meta refuses to run an ad from an Instagram profile with no photo; say so before creating anything."""
    instagram = await reader.instagram_account_for_page(page_id)
    if instagram and not instagram.get("profile_picture_url"):
        raise InstagramProfileIncomplete(
            f"@{instagram.get('username') or 'your Instagram account'} has no profile photo. "
            "Add one in the Instagram app (Profile, Edit profile, Edit picture), wait a few minutes, "
            "then publish again."
        )


async def _interest_still_exists(reader: AdsReader, interest: dict) -> bool:
    """Meta's search skips the "(dining)" suffix of an interest label, so also try the base name."""
    name = interest.get("name") or ""
    base = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    for term in dict.fromkeys(t for t in (name, base) if t):
        options = await reader.search_interests(term, limit=INTEREST_SEARCH_LIMIT)
        if any(o.id == interest.get("id") for o in options):
            return True
    return False


async def verify_interests(reader: AdsReader, interests: list[dict]) -> tuple[list[dict], list[str]]:
    """Confirm every selected interest is still available before creating any Meta objects."""
    kept = []
    for interest in interests:
        if not await _interest_still_exists(reader, interest):
            raise DraftIncomplete(
                f"Meta no longer confirms the selected interest '{interest.get('name')}'. "
                "Remove it or select a current Meta match, then publish again.",
                {"invalid_interest": interest.get("id")},
            )
        kept.append({"id": interest["id"], "name": interest["name"]})
    return kept, []
