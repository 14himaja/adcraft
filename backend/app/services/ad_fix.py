"""Fix what Meta reports as wrong with a published ad, when the fix lives inside the ad itself.

Known Meta messages map to a fixed repair (no AI guessing, so it cannot make things worse):
- button not allowed on Instagram -> new creative with Learn More, swapped onto the ad
- city targeting refused          -> targeting without cities (whole country)
Anything else (profile photo, payment, review) is returned as a plain instruction for the user.
"""

from app import audit
from app.agents.ad_drafter import DEFAULT_COUNTRY
from app.domain.ad_states import AdState
from app.errors import AppError
from app.meta.connections import require_selected
from app.meta.payloads import creative_payload, object_name, targeting
from app.services.ad_lifecycle import meta_write

SAFE_CTA = "LEARN_MORE"
FIXABLE = (AdState.ACTIVE, AdState.PAUSED, AdState.PAUSED_ON_META, AdState.PUBLISH_FAILED)
PHOTO_HELP = (
    "The Instagram account needs a profile photo. Add one in the Instagram app "
    "(Profile, Edit profile, Edit picture), wait a few minutes, then press Refresh insights."
)


class NothingToFix(AppError):
    status, code = 409, "NOTHING_TO_FIX"


def reported_problems(campaign: dict) -> list[str]:
    error = (campaign.get("publish") or {}).get("error") or {}
    return [
        *((campaign.get("meta") or {}).get("issues") or []),
        *([error["message"]] if error.get("message") else []),
    ]


def plan(problems: list[str]) -> tuple[set[str], list[str]]:
    """(automatic fixes, instructions for the user)"""
    auto, manual = set(), []
    for problem in problems:
        low = problem.lower()
        if "call to action" in low or "cta" in low:
            auto.add("cta")
        elif "city targeting" in low:
            auto.add("cities")
        elif "profile photo" in low or "profile picture" in low or "not supported for ig" in low:
            manual.append(PHOTO_HELP)
        else:
            manual.append(
                f"{problem} Open the ad in Ads Manager and read its Delivery error for the exact fix."
            )
    return auto, list(dict.fromkeys(manual))


async def fix_issues(db, campaign: dict, *, container) -> dict:
    if campaign.get("status") not in FIXABLE:
        raise NothingToFix(f"Nothing to fix on a {campaign.get('status')} ad")
    auto, manual = plan(reported_problems(campaign))
    if not auto and not manual:
        raise NothingToFix("Meta has not reported a problem with this ad. Press Refresh insights first.")
    fixed, set_fields, meta = [], {}, campaign.get("meta") or {}
    connection = await require_selected(db, campaign["user_id"], clock=container.clock)
    writer = container.gateway_for(connection)[1]
    selected = campaign.get("selected_variant", 0)

    if "cta" in auto and meta.get("ad_id"):
        variant = {**campaign["variants"][selected], "call_to_action": SAFE_CTA}
        params = creative_payload(
            variant,
            page_id=connection["page_id"],
            instagram_user_id=connection["instagram_user_id"],
            link=campaign["landing_url"],
            image_hash=meta["image_hash"],
            name=f"{object_name(campaign['_id'], 'CREATIVE')}-fix",
        )
        creative_id = await meta_write(
            db, campaign, container, writer.create, connection["ad_account_id"], "adcreatives", params
        )
        await meta_write(
            db, campaign, container, writer.update, meta["ad_id"], {"creative": {"creative_id": creative_id}}
        )
        set_fields[f"variants.{selected}.call_to_action"] = SAFE_CTA
        set_fields["meta.creative_id"] = creative_id
        fixed.append("Changed the button to Learn More on the ad.")

    if "cities" in auto:
        audience = campaign.get("audience") or {}
        audience = {**audience, "cities": [], "countries": audience.get("countries") or [DEFAULT_COUNTRY]}
        if meta.get("adset_id"):
            positions = container.settings.instagram_position_list
            await meta_write(
                db,
                campaign,
                container,
                writer.update,
                meta["adset_id"],
                {"targeting": targeting(audience, positions)},
            )
        set_fields["audience.cities"] = []
        set_fields["audience.countries"] = audience["countries"]
        fixed.append(
            "Removed the cities and targeted the whole country."
            + (
                " Press Resume publishing to continue."
                if campaign["status"] == AdState.PUBLISH_FAILED
                else ""
            )
        )

    if set_fields:
        set_fields["meta.issues"] = []
        await db.campaigns.update_one({"_id": campaign["_id"]}, {"$set": set_fields})
        await audit.record(
            db,
            actor="agent",
            event_type="AD_ISSUES_FIXED",
            payload={"fixed": fixed},
            user_id=campaign["user_id"],
            campaign_id=campaign["_id"],
        )
    return {"fixed": fixed, "manual": manual}
