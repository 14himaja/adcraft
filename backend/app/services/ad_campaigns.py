"""AI Ad Studio campaigns: create, read, edit and serialize DRAFTs (spec 07 §1, §2, §4, §5)."""

from bson import ObjectId
from bson.errors import InvalidId
from gridfs import AsyncGridFSBucket
from pymongo import ReturnDocument

from app import audit
from app.clock import Clock
from app.config import Settings
from app.domain.ad_campaign import (
    field_errors,
    from_minor,
    missing_fields,
    special_category_reason,
    to_minor,
)
from app.domain.ad_states import EDITABLE, AdState
from app.domain.rules import OBJECTIVES
from app.errors import AppError, NotFound
from app.services.transitions import ConcurrentModification, IllegalTransition

SCHEMA_VERSION = 2
DEFAULT_AUDIENCE = {
    "countries": [],
    "cities": [],
    "age_min": 18,
    "age_max": 65,
    "genders": "ALL",
    "interests": [],
}
PUBLIC_KEYS = (
    "schema_version",
    "status",
    "idea",
    "title",
    "objective",
    "landing_url",
    "audience",
    "daily_budget_minor",
    "currency",
    "start_date",
    "end_date",
    "variants",
    "selected_variant",
    "chat",
    "not_special_category",
    "image_prompt",
    "image_id",
    "meta",
    "publish",
    "insights",
    "posted",
    "publishing_destinations",
    "selected_hashtags",
    "custom_hashtags",
    "ai_recommended_hashtags",
    "rev",
    "created_at",
    "updated_at",
)


class InvalidCampaign(AppError):
    status, code = 422, "VALIDATION_FAILED"


class ObjectiveUnsupported(AppError):
    status, code = 422, "OBJECTIVE_UNSUPPORTED"


def _check(doc: dict, changed: set[str], settings: Settings, clock: Clock) -> None:
    if "objective" in changed and doc.get("objective") not in OBJECTIVES:
        raise ObjectiveUnsupported(
            f"Objective {doc.get('objective')!r} is not supported yet; use TRAFFIC or AWARENESS",
            {"supported": sorted(OBJECTIVES)},
        )
    problems = field_errors(
        doc,
        changed,
        today=clock.now().date(),
        max_daily_budget_inr=settings.max_daily_budget_inr,
        max_days=settings.max_campaign_days,
    )
    if problems:
        raise InvalidCampaign("; ".join(problems), {"problems": problems})


async def create_draft(
    db,
    *,
    user_id,
    fields: dict,
    settings: Settings,
    clock: Clock,
    actor: str = "user",
    extra: dict | None = None,
) -> dict:
    """`fields` are user-editable values; `extra` (idea, image_prompt, warnings) is stored as is."""
    now = clock.now()
    doc = {
        "user_id": user_id,
        "schema_version": SCHEMA_VERSION,
        "status": AdState.DRAFT.value,
        "idea": "",
        "title": "",
        "objective": None,
        "landing_url": "",
        "audience": dict(DEFAULT_AUDIENCE),
        "daily_budget_minor": None,
        "currency": "INR",
        "start_date": None,
        "end_date": None,
        "variants": [],
        "selected_variant": 0,
        "image_prompt": "",
        "image_id": None,
        "warnings": [],
        "meta": {},
        "publish": None,
        "insights": None,
        "posted": {},
        "publishing_destinations": None,
        "selected_hashtags": [],
        "custom_hashtags": [],
        "rev": 0,
        "created_at": now,
        "updated_at": now,
        **(extra or {}),
        **fields,
    }
    _check(doc, set(fields), settings, clock)
    doc["missing_fields"] = missing_fields(doc)
    doc["_id"] = (await db.campaigns.insert_one(doc)).inserted_id
    await audit.record(
        db,
        actor=actor,
        event_type="CAMPAIGN_CREATED",
        payload={"fields": sorted(fields)},
        user_id=user_id,
        campaign_id=doc["_id"],
    )
    return doc


async def get_owned(db, campaign_id: str, user_id) -> dict:
    try:
        oid = ObjectId(campaign_id)
    except (InvalidId, TypeError):
        raise NotFound("Campaign not found") from None
    doc = await db.campaigns.find_one({"_id": oid, "user_id": user_id})
    if doc is None:
        raise NotFound("Campaign not found")
    return doc


def require_editable(campaign: dict) -> None:
    status = campaign.get("status")
    if status not in EDITABLE:
        raise IllegalTransition(f"Only a DRAFT can be edited; this campaign is {status}", {"from": status})


async def update_draft(
    db, campaign: dict, changes: dict, *, settings: Settings, clock: Clock, actor: str = "user"
) -> dict:
    require_editable(campaign)
    changes = dict(changes)
    doc = {**campaign, **changes}
    if "selected_variant" not in changes and doc.get("selected_variant", 0) >= len(
        doc.get("variants") or [1]
    ):
        changes["selected_variant"] = doc["selected_variant"] = 0  # variants shrank
    _check(doc, set(changes), settings, clock)
    updated = await db.campaigns.find_one_and_update(
        {"_id": campaign["_id"], "status": AdState.DRAFT.value, "rev": campaign.get("rev", 0)},
        {
            "$set": {**changes, "missing_fields": missing_fields(doc), "updated_at": clock.now()},
            "$inc": {"rev": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise ConcurrentModification("The campaign was changed by another request; reload and try again")
    await audit.record(
        db,
        actor=actor,
        event_type="CAMPAIGN_UPDATED",
        payload={"fields": sorted(changes), "rev": updated["rev"]},
        user_id=campaign["user_id"],
        campaign_id=campaign["_id"],
    )
    return updated


async def list_owned(db, user_id) -> list[dict]:
    return await db.campaigns.find({"user_id": user_id}).sort("created_at", -1).to_list(100)


async def duplicate_campaign(
    db, campaign: dict, *, settings: Settings, clock: Clock, actor: str = "user"
) -> dict:
    """Copy campaign content into a DRAFT, including its shared image, without Meta state."""
    now = clock.now()
    title = f"{campaign.get('title') or 'Untitled'} (copy)" if campaign.get("title") else "(copy)"
    variants = [dict(v) for v in (campaign.get("variants") or [])]
    audience = dict(campaign.get("audience") or DEFAULT_AUDIENCE)
    doc = {
        "user_id": campaign["user_id"],
        "schema_version": SCHEMA_VERSION,
        "status": AdState.DRAFT.value,
        "idea": campaign.get("idea", ""),
        "title": title,
        "objective": campaign.get("objective"),
        "landing_url": campaign.get("landing_url", ""),
        "audience": audience,
        "daily_budget_minor": campaign.get("daily_budget_minor"),
        "currency": campaign.get("currency", "INR"),
        "start_date": campaign.get("start_date"),
        "end_date": campaign.get("end_date"),
        "variants": variants,
        "selected_variant": campaign.get("selected_variant", 0),
        "image_prompt": campaign.get("image_prompt", ""),
        "image_id": campaign.get("image_id"),
        "not_special_category": campaign.get("not_special_category", False),
        "selected_hashtags": list(campaign.get("selected_hashtags") or []),
        "custom_hashtags": list(campaign.get("custom_hashtags") or []),
        "ai_recommended_hashtags": list(campaign.get("ai_recommended_hashtags") or []),
        "publishing_destinations": campaign.get("publishing_destinations"),
        "warnings": [],
        "meta": {},
        "publish": None,
        "insights": None,
        "rev": 0,
        "created_at": now,
        "updated_at": now,
    }
    doc["missing_fields"] = missing_fields(doc)
    doc["_id"] = (await db.campaigns.insert_one(doc)).inserted_id
    await audit.record(
        db,
        actor=actor,
        event_type="CAMPAIGN_DUPLICATED",
        payload={"source_id": str(campaign["_id"])},
        user_id=campaign["user_id"],
        campaign_id=doc["_id"],
    )
    return doc


async def delete_owned(db, campaign: dict, *, container=None) -> None:
    if container is not None:
        from app.services.ad_lifecycle import delete_meta_objects

        await delete_meta_objects(db, campaign, container, actor="user")
        bucket = AsyncGridFSBucket(db, bucket_name="images")
        files = db["images.files"].find(
            {
                "metadata.campaign_id": {"$in": [campaign["_id"], str(campaign["_id"])]},
                "metadata.user_id": campaign["user_id"],
                "metadata.source": "generated",
            }
        )
        async for f in files:
            other = await db.campaigns.find_one(
                {"_id": {"$ne": campaign["_id"]}, "image_id": str(f["_id"])}
            )
            if not other:
                await bucket.delete(f["_id"])
    await db.campaigns.delete_one({"_id": campaign["_id"], "user_id": campaign["user_id"]})
    await audit.record(
        db,
        actor="user",
        event_type="CAMPAIGN_DELETED",
        payload={"status": campaign.get("status")},
        user_id=campaign["user_id"],
        campaign_id=campaign["_id"],
    )


def _legacy_view(doc: dict) -> dict:
    """Old studio documents (READY_PAUSED, flat budget, `creative`, interest names) -> best-effort v2."""
    audience = doc.get("audience") or {}
    creative = doc.get("creative") or {}
    budget = doc.get("daily_budget")
    objective = doc.get("objective")
    return {
        **doc,
        "status": AdState.DRAFT.value,
        "objective": next((k for k, v in OBJECTIVES.items() if v["objective"] == objective), objective),
        "audience": {
            "countries": [audience["country"]] if audience.get("country") else audience.get("countries", []),
            "cities": [
                {"key": "", "name": c} if isinstance(c, str) else c for c in audience.get("cities", [])
            ],
            "age_min": audience.get("age_min", 18),
            "age_max": audience.get("age_max", 65),
            "genders": audience.get("gender", "ALL"),
            "interests": [
                {"id": "", "name": i} if isinstance(i, str) else i for i in audience.get("interests", [])
            ],
        },
        "daily_budget_minor": to_minor(budget) if budget is not None else None,
        "variants": [
            {
                "headline": creative.get("headline", ""),
                "primary_text": creative.get("primary_text", ""),
                "description": creative.get("description", ""),
                "call_to_action": creative.get("call_to_action", "LEARN_MORE"),
            }
        ]
        if creative
        else [],
        "rev": doc.get("rev", 0),
    }


def special_reason(doc: dict) -> str | None:
    """Why the ad looks like a Meta special category, unless the advertiser has confirmed it is not one."""
    return None if doc.get("not_special_category") else special_category_reason(campaign_text(doc))


def campaign_text(doc: dict) -> str:
    parts = [doc.get("idea") or "", doc.get("title") or ""]
    for variant in doc.get("variants") or []:
        parts += [
            variant.get("headline", ""),
            variant.get("primary_text", ""),
            variant.get("description", ""),
        ]
    return " ".join(parts)


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def serialize(doc: dict, settings: Settings) -> dict:
    view = doc if doc.get("schema_version") == SCHEMA_VERSION else _legacy_view(doc)
    status = view.get("status")
    reason = special_reason(view)
    warnings = list(view.get("warnings") or []) + ([f"Special ad category: {reason}"] if reason else [])
    missing = missing_fields(view)
    minor = view.get("daily_budget_minor")
    image_id = view.get("image_id")
    return {
        "id": str(doc["_id"]),
        **{key: view.get(key) for key in PUBLIC_KEYS},
        "created_at": _iso(view.get("created_at")),
        "updated_at": _iso(view.get("updated_at")),
        "daily_budget": from_minor(minor) if minor is not None else None,
        "image_url": f"/api/v1/images/{image_id}" if image_id else None,
        "missing_fields": missing,
        "warnings": warnings,
        "can_publish": status == AdState.DRAFT and not missing and reason is None,
        "live_delivery_enabled": settings.spend_allowed,
        "special_category_reason": reason,
        "can_activate": status in (AdState.PAUSED_ON_META, AdState.PAUSED) and settings.spend_allowed,
    }
