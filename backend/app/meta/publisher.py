"""Publish a DRAFT to Meta, then activate all objects once the ad is complete (spec 07 §8).

Idempotency without an idempotency key: every object gets a deterministic name and is looked up by that
name before each create, so a timeout after Meta created it (or a crash before the checkpoint) adopts
the existing object instead of creating a paid duplicate.
"""

import structlog

from app import audit
from app.domain.ad_states import AdState
from app.meta.connections import mark_expired, require_selected
from app.meta.errors import ErrorClass, MetaError, classify, with_retries
from app.meta.payloads import ad_payload, adset_payload, campaign_payload, creative_payload, object_name
from app.meta.publish_checks import check_instagram_profile, check_publishable, verify_interests
from app.services.ad_lifecycle import delete_meta_objects, require_spend_allowed, transition
from app.services.image_store import load_image

STEPS = ("CAMPAIGN", "ADSET", "IMAGE", "CREATIVE", "AD")
EDGES = {"CAMPAIGN": "campaigns", "ADSET": "adsets", "CREATIVE": "adcreatives", "AD": "ads"}
META_KEYS = {
    "CAMPAIGN": "campaign_id",
    "ADSET": "adset_id",
    "IMAGE": "image_hash",
    "CREATIVE": "creative_id",
    "AD": "ad_id",
}
INTERRUPTED = "Publishing was interrupted by a server restart. Click Resume to continue."
log = structlog.get_logger()


def _new_block() -> dict:
    steps = [
        {"name": s, "status": "PENDING", "meta_object_id": None, "attempts": 0, "last_error": None}
        for s in STEPS
    ]
    return {"status": "RUNNING", "steps": steps, "error": None}


async def start_publish(db, campaign: dict, *, container) -> dict:
    """Validate live delivery before the first Meta write; the caller spawns the run."""
    if campaign.get("status") != AdState.DRAFT:
        return await transition(  # raises ILLEGAL_TRANSITION with the current state
            db, campaign, AdState.PUBLISHING, actor="user", reason="publish", clock=container.clock
        )
    connection = await require_selected(db, campaign["user_id"], clock=container.clock)
    require_spend_allowed(container.settings)
    check_publishable(campaign, connection, container.settings, container.clock)
    reader = container.gateway_for(connection)[0]
    await check_instagram_profile(reader, connection["page_id"])
    kept, warnings = await verify_interests(reader, (campaign.get("audience") or {}).get("interests") or [])
    return await transition(
        db,
        campaign,
        AdState.PUBLISHING,
        actor="user",
        reason="publish (live delivery)",
        clock=container.clock,
        set_fields={
            "publish": _new_block(),
            "meta": {},
            "audience.interests": kept,
            "warnings": [*(campaign.get("warnings") or []), *warnings],
        },
    )


async def _adopt_or_create(
    reader, writer, account: str, edge: str, name: str, params: dict
) -> tuple[str, bool]:
    try:
        existing = await reader.find_by_name(account, edge, name)
    except MetaError as exc:
        if classify(exc) != ErrorClass.INVALID:
            raise
        existing = None  # ponytail: this edge refused name filtering; a timeout right here could duplicate
    if existing:
        return existing, True
    return await writer.create(account, edge, params), False


async def _run_step(db, campaign: dict, step: str, connection: dict, gateway, container, counter) -> tuple:
    reader, writer = gateway
    account, meta, name = connection["ad_account_id"], campaign["meta"], object_name(campaign["_id"], step)
    wait = container.retry_wait
    if step == "IMAGE":  # Meta returns the same hash for the same bytes, so a re-upload is harmless
        data, _ = await load_image(db, campaign["image_id"], campaign["user_id"])
        return await with_retries(
            writer.upload_image, account, data, f"{name}.jpg", wait=wait, counter=counter
        ), False
    if step == "CAMPAIGN":
        params = campaign_payload(campaign["objective"], name)
    elif step == "ADSET":
        positions = container.settings.instagram_position_list
        params = adset_payload(
            campaign, meta["campaign_id"], name, now=container.clock.now(), positions=positions
        )
    elif step == "CREATIVE":
        params = creative_payload(
            campaign["variants"][campaign.get("selected_variant", 0)],
            page_id=connection["page_id"],
            instagram_user_id=connection["instagram_user_id"],
            link=campaign["landing_url"],
            image_hash=meta["image_hash"],
            name=name,
        )
    else:
        params = ad_payload(meta["adset_id"], meta["creative_id"], name)
    return await with_retries(
        _adopt_or_create, reader, writer, account, EDGES[step], name, params, wait=wait, counter=counter
    )


async def _checkpoint(db, campaign: dict, index: int, object_id: str, adopted: bool, attempts: int, clock):
    step = STEPS[index]
    campaign["meta"][META_KEYS[step]] = object_id
    prefix = f"publish.steps.{index}"
    await db.campaigns.update_one(
        {"_id": campaign["_id"], "status": AdState.PUBLISHING.value},
        {
            "$set": {
                f"{prefix}.status": "DONE",
                f"{prefix}.meta_object_id": object_id,
                f"{prefix}.attempts": attempts,
                f"{prefix}.last_error": None,
                f"meta.{META_KEYS[step]}": object_id,
                "updated_at": clock.now(),
            }
        },
    )
    await audit.record(
        db,
        actor="system",
        event_type="META_OBJECT_ADOPTED" if adopted else "META_OBJECT_CREATED",
        payload={"step": step, "meta_object_id": object_id, "status": "PAUSED", "attempts": attempts},
        user_id=campaign["user_id"],
        campaign_id=campaign["_id"],
    )


def _user_message(exc: Exception) -> str:
    if isinstance(exc, MetaError):
        return exc.message  # Meta's error_user_msg when present
    if isinstance(exc, TimeoutError):
        return "Meta did not respond in time. Click Resume to try again."
    if isinstance(exc, ConnectionError):
        return "Could not reach Meta. Click Resume to try again."
    return getattr(exc, "message", None) or "Publishing stopped because of an internal error. Click Resume."


async def _fail(db, campaign_id, index: int, exc: Exception, attempts: int, container) -> None:
    if not isinstance(exc, (MetaError, TimeoutError, ConnectionError)):
        log.exception("publish_step_crashed", step=STEPS[index])
    message = _user_message(exc)
    error = {"step": STEPS[index], "message": message, "meta_code": getattr(exc, "meta_code", None)}
    prefix = f"publish.steps.{index}"
    campaign = await db.campaigns.find_one_and_update(
        {"_id": campaign_id},
        {
            "$set": {
                "publish.status": "FAILED",
                "publish.error": error,
                f"{prefix}.status": "FAILED",
                f"{prefix}.last_error": message,
                f"{prefix}.attempts": attempts,
            }
        },
    )
    await audit.record(
        db,
        actor="system",
        event_type="PUBLISH_FAILED",
        payload=error,
        user_id=campaign["user_id"],
        campaign_id=campaign_id,
    )
    if isinstance(exc, MetaError) and classify(exc) == ErrorClass.AUTH:
        await mark_expired(db, campaign["user_id"], clock=container.clock)
    fresh = await db.campaigns.find_one({"_id": campaign_id})
    await transition(db, fresh, AdState.PUBLISH_FAILED, actor="system", reason=message, clock=container.clock)


async def run_publish(db, campaign_id, *, container) -> None:
    """Background job: runs the unfinished steps. Never leaves the campaign stuck in PUBLISHING."""
    campaign = await db.campaigns.find_one({"_id": campaign_id})
    if campaign is None or campaign["status"] != AdState.PUBLISHING:
        return
    campaign["meta"] = dict(campaign.get("meta") or {})
    pending = [i for i, s in enumerate(campaign["publish"]["steps"]) if s["status"] != "DONE"]
    index, counter = (pending or [0])[0], [0]
    try:
        connection = await require_selected(db, campaign["user_id"], clock=container.clock)
        gateway = container.gateway_for(connection)
        for index in pending:
            counter = [0]
            object_id, adopted = await _run_step(
                db, campaign, STEPS[index], connection, gateway, container, counter
            )
            await _checkpoint(db, campaign, index, object_id, adopted, counter[0], container.clock)
        # Keep every object paused until the full ad is ready. Enable parents first and the ad last,
        # so a partial failure cannot start delivery before the final activation write.
        index = len(STEPS) - 1
        for key in ("campaign_id", "adset_id", "ad_id"):
            object_id = campaign["meta"].get(key)
            await with_retries(gateway[1].update, object_id, {"status": "ACTIVE"}, wait=container.retry_wait)
            await audit.record(
                db,
                actor="system",
                event_type="META_OBJECT_UPDATED",
                payload={"object": key, "meta_object_id": object_id, "after": {"status": "ACTIVE"}},
                user_id=campaign["user_id"],
                campaign_id=campaign_id,
            )
    except Exception as exc:  # any failure -> PUBLISH_FAILED with a message, ready for Resume
        await _fail(db, campaign_id, index, exc, counter[0], container)
        return
    fresh = await db.campaigns.find_one({"_id": campaign_id})
    await transition(
        db,
        fresh,
        AdState.ACTIVE,
        actor="system",
        reason="published and activated",
        clock=container.clock,
        set_fields={"publish.status": "DONE"},
    )
    # Trigger automatic post-knowledge ingestion for the activated Meta ad
    try:
        user = await db.users.find_one({"_id": fresh["user_id"]}) or {}
        ws_id = fresh.get("workspace_id") or user.get("active_workspace_id") or "synxait"
        ad_id = str(fresh.get("meta", {}).get("ad_id") or fresh["_id"])
        variant = (fresh.get("variants") or [{}])[fresh.get("selected_variant", 0)]
        caption = "\n\n".join(filter(None, [variant.get("headline"), variant.get("primary_text")]))
        from app.services import social_knowledge
        await container.spawn(
            social_knowledge.ingest_post(
                db,
                container,
                user_id=fresh["user_id"],
                workspace_id=ws_id,
                platform="instagram",
                platform_post_id=ad_id,
                post_url=fresh.get("landing_url") or f"https://instagram.com/p/{ad_id}",
                title=fresh.get("title", ""),
                caption=caption,
                media_reference=fresh.get("image_id"),
                media_type="IMAGE",
                campaign_id=fresh["_id"],
                ad_campaign_status="ACTIVE",
                source="adcraft_ad",
                auto_process=True,
            )
        )
        log.info("ad_knowledge_ingestion_scheduled", campaign_id=str(campaign_id), ad_id=ad_id, workspace_id=ws_id)
    except Exception as ing_exc:
        log.warning("ad_knowledge_ingestion_trigger_failed", campaign_id=str(campaign_id), error=str(ing_exc))


async def resume_publish(db, campaign: dict, *, container) -> dict:
    """PUBLISH_FAILED -> PUBLISHING; the caller spawns run_publish, which continues at the first
    unfinished step."""
    if campaign.get("status") == AdState.PUBLISH_FAILED:
        await require_selected(db, campaign["user_id"], clock=container.clock)
        require_spend_allowed(container.settings)
    retry = {
        f"publish.steps.{i}.status": "PENDING"
        for i, s in enumerate((campaign.get("publish") or {}).get("steps") or [])
        if s["status"] == "FAILED"
    }
    return await transition(
        db,
        campaign,
        AdState.PUBLISHING,
        actor="user",
        reason="resume publishing",
        clock=container.clock,
        set_fields={**retry, "publish.status": "RUNNING", "publish.error": None},
    )


async def discard_publish(db, campaign: dict, *, container) -> dict:
    """PUBLISH_FAILED -> DRAFT after deleting what was created (children first)."""
    if campaign.get("status") == AdState.PUBLISH_FAILED:
        await delete_meta_objects(db, campaign, container, actor="user")
    fresh = await db.campaigns.find_one({"_id": campaign["_id"]}) or campaign
    return await transition(
        db,
        fresh,
        AdState.DRAFT,
        actor="user",
        reason="publish discarded",
        clock=container.clock,
        set_fields={"publish": None, "meta": {}},
    )


async def recover_interrupted(db, *, clock) -> int:
    """At startup: a PUBLISHING campaign has no running job any more -> PUBLISH_FAILED, ready for Resume."""
    stuck = await db.campaigns.find({"status": AdState.PUBLISHING.value}).to_list(None)
    for campaign in stuck:
        steps = (campaign.get("publish") or {}).get("steps") or []
        step = next((s["name"] for s in steps if s["status"] != "DONE"), None)
        error = {"step": step, "message": INTERRUPTED, "meta_code": None}
        await transition(
            db,
            campaign,
            AdState.PUBLISH_FAILED,
            actor="system",
            reason="interrupted by a server restart",
            clock=clock,
            set_fields={"publish.status": "FAILED", "publish.error": error},
        )
    return len(stuck)
