"""State moves and Meta writes after publishing: activate, pause, resume, delete (spec 07 §2, §9)."""

from pymongo import ReturnDocument

from app import audit
from app.clock import Clock
from app.config import Settings
from app.domain.ad_campaign import field_errors
from app.domain.ad_states import AdState, can_transition
from app.errors import AppError
from app.meta.connections import mark_expired, require_selected
from app.meta.errors import ErrorClass, MetaError, classify, with_retries
from app.meta.ports import AdsWriter
from app.services.ad_campaigns import InvalidCampaign
from app.services.transitions import ConcurrentModification, IllegalTransition

DELETE_ORDER = ("ad_id", "creative_id", "adset_id", "campaign_id")  # children first
ACTIVATE_ORDER = ("ad_id", "adset_id", "campaign_id")  # campaign last, so nothing delivers half-switched


class SpendBlocked(AppError):
    status, code = 409, "SPEND_BLOCKED"


async def transition(
    db, campaign: dict, to: AdState, *, actor: str, reason: str, clock: Clock, set_fields: dict | None = None
) -> dict:
    """Conditional move on {_id, status, rev}; 409 ILLEGAL_TRANSITION / CONCURRENT_MODIFICATION."""
    try:
        src = AdState(campaign.get("status"))
    except ValueError:
        src = None
    if src is None or not can_transition(src, to):
        raise IllegalTransition(
            f"A {campaign.get('status')} campaign cannot move to {to}",
            {"from": campaign.get("status"), "to": to},
        )
    updated = await db.campaigns.find_one_and_update(
        {"_id": campaign["_id"], "status": src.value, "rev": campaign.get("rev", 0)},
        {"$set": {**(set_fields or {}), "status": to.value, "updated_at": clock.now()}, "$inc": {"rev": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise ConcurrentModification("The campaign was changed by another request; reload and try again")
    await audit.record(
        db,
        actor=actor,
        event_type="STATE_TRANSITION",
        payload={"from": src.value, "to": to.value, "reason": reason, "rev": updated["rev"]},
        user_id=campaign["user_id"],
        campaign_id=campaign["_id"],
    )
    return updated


def check_caps(campaign: dict, settings: Settings, clock: Clock) -> None:
    """MAX_DAILY_BUDGET_INR / MAX_CAMPAIGN_DAYS again at publish/activate time (settings may have changed)."""
    problems = field_errors(
        campaign,
        {"daily_budget_minor", "end_date"},
        today=clock.now().date(),
        max_daily_budget_inr=settings.max_daily_budget_inr,
        max_days=settings.max_campaign_days,
    )
    if problems:
        raise InvalidCampaign("; ".join(problems), {"problems": problems})


def require_spend_allowed(settings: Settings) -> None:
    if not settings.spend_allowed:
        raise SpendBlocked(
            "Live ad delivery is disabled on this server. Enable ALLOW_REAL_AD_SPEND and disable "
            "SAFE_MODE_NO_SPEND before publishing live ads."
        )


async def meta_write(db, campaign: dict, container, fn, *args):
    """One audited-by-caller Meta write with safe retries; code 190 marks the connection expired."""
    try:
        return await with_retries(fn, *args, wait=container.retry_wait)
    except MetaError as exc:
        if classify(exc) == ErrorClass.AUTH:
            await mark_expired(db, campaign["user_id"], clock=container.clock)
        raise


async def _writer(db, campaign: dict, container) -> AdsWriter:
    connection = await require_selected(db, campaign["user_id"], clock=container.clock)
    return container.gateway_for(connection)[1]


async def delete_meta_objects(db, campaign: dict, container, *, actor: str) -> None:
    meta = campaign.get("meta") or {}
    if not any(meta.get(key) for key in DELETE_ORDER):
        return
    writer = await _writer(db, campaign, container)
    for key in DELETE_ORDER:
        if not (object_id := meta.get(key)):
            continue
        try:
            await meta_write(db, campaign, container, writer.delete, object_id)
        except MetaError as exc:
            if classify(exc) != ErrorClass.INVALID:  # code 100 "does not exist" = already deleted
                raise
        await db.campaigns.update_one({"_id": campaign["_id"]}, {"$unset": {f"meta.{key}": ""}})
        await audit.record(
            db,
            actor=actor,
            event_type="META_OBJECT_DELETED",
            payload={"object": key, "meta_object_id": object_id},
            user_id=campaign["user_id"],
            campaign_id=campaign["_id"],
        )


async def _set_meta_status(db, campaign: dict, container, keys: tuple[str, ...], status: str) -> None:
    writer = await _writer(db, campaign, container)
    for key in keys:
        object_id = campaign["meta"][key]
        await meta_write(db, campaign, container, writer.update, object_id, {"status": status})
        await audit.record(
            db,
            actor="user",
            event_type="META_OBJECT_UPDATED",
            payload={"object": key, "meta_object_id": object_id, "after": {"status": status}},
            user_id=campaign["user_id"],
            campaign_id=campaign["_id"],
        )


def _require(campaign: dict, *states: AdState) -> None:
    if campaign.get("status") not in states:
        raise IllegalTransition(
            f"This needs a {' or '.join(states)} campaign; this one is {campaign.get('status')}",
            {"from": campaign.get("status")},
        )


async def _go_live(db, campaign: dict, container, keys: tuple[str, ...], reason: str) -> dict:
    settings, clock = container.settings, container.clock
    require_spend_allowed(settings)
    check_caps(campaign, settings, clock)
    await _set_meta_status(db, campaign, container, keys, "ACTIVE")
    await db.social_posts.update_many(
        {"campaign_id": campaign["_id"]},
        {"$set": {"ad_campaign_status": "active"}},
    )
    fresh = await db.campaigns.find_one({"_id": campaign["_id"]})
    return await transition(db, fresh, AdState.ACTIVE, actor="user", reason=reason, clock=clock)


async def activate(db, campaign: dict, *, container) -> dict:
    _require(campaign, AdState.PAUSED_ON_META)
    return await _go_live(db, campaign, container, ACTIVATE_ORDER, "user activated (spend confirmed)")


async def resume(db, campaign: dict, *, container) -> dict:
    _require(campaign, AdState.PAUSED)
    return await _go_live(db, campaign, container, ("campaign_id",), "user resumed")


async def pause(db, campaign: dict, *, container) -> dict:
    _require(campaign, AdState.ACTIVE)  # always allowed: pausing stops spend
    await _set_meta_status(db, campaign, container, ("campaign_id",), "PAUSED")
    await db.social_posts.update_many(
        {"campaign_id": campaign["_id"]},
        {"$set": {"ad_campaign_status": "stopped"}},
    )
    fresh = await db.campaigns.find_one({"_id": campaign["_id"]})
    return await transition(
        db, fresh, AdState.PAUSED, actor="user", reason="user paused", clock=container.clock
    )
