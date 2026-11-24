from app.domain.workspaces import resolve_workspace_id
import asyncio
from datetime import timedelta
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
    fresh_active = await db.campaigns.find_one({"_id": campaign_id})
    await container.spawn(ingest_ad_campaign(db, container, fresh_active))


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

async def recover_pending_creative_refreshes(db, container) -> int:
    """At startup: find any published posts missing effective_instagram_media_id and resume polling."""
    try:
        cutoff = container.clock.now() - timedelta(days=7)
        unresolved = db.social_posts.find({
            "post_status": "published",
            "effective_instagram_media_id": None,
            "creative_id": {"$ne": None},
            "created_at": {"$gte": cutoff},
        })
        count = 0
        async for post in unresolved:
            c_id = post.get("creative_id")
            camp_id = post.get("campaign_id")
            p_id = str(post["_id"])
            await container.spawn(
                poll_creative_refresh_job(db, container, camp_id, str(c_id), p_id, delays=(0, 60, 300, 1800))
            )
            count += 1
        return count
    except Exception as exc:
        log.warning("recover_pending_creative_refreshes_failed", error=str(exc))
        return 0


async def ingest_ad_campaign(db, container, campaign: dict) -> dict | None:
    """Ingests the activated ad into the social knowledge base with creative details."""
    try:
        user = await db.users.find_one({"_id": campaign["user_id"]}) or {}
        ws_id = resolve_workspace_id(campaign=campaign, user=user)
        meta = dict(campaign.get("meta") or {})
        ad_id = str(meta.get("ad_id") or campaign["_id"])
        creative_id = meta.get("creative_id")

        effective_ig_id = meta.get("effective_instagram_media_id")
        permalink = meta.get("permalink") or meta.get("instagram_permalink_url")

        # Fetch real creative details via gateway after activation if not already present
        if creative_id and not effective_ig_id:
            try:
                connection = await require_selected(db, campaign["user_id"], clock=container.clock)
                reader, _ = container.gateway_for(connection)
                if hasattr(reader, "get_ad_creative"):
                    c_info = await reader.get_ad_creative(creative_id)
                    effective_ig_id = c_info.get("effective_instagram_media_id")
                    permalink = c_info.get("instagram_permalink_url")
            except Exception as exc:
                log.warning("fetch_ad_creative_failed", creative_id=creative_id, error=str(exc))

        variants = campaign.get("variants") or [{}]
        selected_idx = campaign.get("selected_variant", 0)
        variant = variants[selected_idx] if selected_idx < len(variants) else variants[0]

        headline = variant.get("headline", "")
        primary_text = variant.get("primary_text", "")
        description = variant.get("description", "")
        cta = variant.get("call_to_action", "")
        landing_url = campaign.get("landing_url", "")
        audience = campaign.get("audience") or {}
        start_date = campaign.get("start_date")
        end_date = campaign.get("end_date")
        offer = campaign.get("offer") or campaign.get("idea") or ""

        caption_parts = []
        if headline:
            caption_parts.append(headline)
        if primary_text:
            caption_parts.append(primary_text)
        if description:
            caption_parts.append(description)
        if offer:
            caption_parts.append(f"Special Offer: {offer}")
        if cta:
            caption_parts.append(f"Call to action: {cta}")
        if landing_url:
            caption_parts.append(f"Landing URL: {landing_url}")
        if start_date or end_date:
            caption_parts.append(f"Campaign Dates: {start_date or ''} to {end_date or ''}".strip())
        if audience:
            interests = audience.get("interests")
            if interests:
                names = [i.get("name") if isinstance(i, dict) else str(i) for i in interests]
                caption_parts.append(f"Target Audience: {', '.join(names)}")
        caption = "\n\n".join(caption_parts)

        platform_post_id = str(effective_ig_id or ad_id)
        post_url = permalink or landing_url or f"https://instagram.com/p/{platform_post_id}"

        from app.services import social_knowledge
        res = await social_knowledge.ingest_post(
            db,
            container,
            user_id=campaign["user_id"],
            workspace_id=ws_id,
            platform="instagram",
            platform_post_id=platform_post_id,
            ad_id=ad_id,
            effective_instagram_media_id=str(effective_ig_id) if effective_ig_id else None,
            post_url=post_url,
            title=campaign.get("title", ""),
            caption=caption,
            media_reference=campaign.get("image_id"),
            media_type="IMAGE",
            campaign_id=campaign["_id"],
            ad_campaign_status="active",
            source="adcraft_ad",
            offer=offer,
            landing_url=landing_url,
            cta=cta,
            audience=audience,
            start_date=start_date,
            end_date=end_date,
            creative_id=str(creative_id) if creative_id else None,
            auto_process=True,
        )
        if not effective_ig_id and creative_id:
            p_id = res.get("id") or (res.get("post_id") if isinstance(res, dict) else None)
            await container.spawn(poll_creative_refresh_job(db, container, campaign["_id"], str(creative_id), p_id))
        log.info("ad_knowledge_ingestion_scheduled", campaign_id=str(campaign.get("_id")), ad_id=ad_id, workspace_id=ws_id)
        return res
    except Exception as ing_exc:
        log.warning("ad_knowledge_ingestion_trigger_failed", campaign_id=str(campaign.get("_id")), error=str(ing_exc))
        return None



async def refresh_ad_creative(
    db, container, *, campaign_id=None, post_id=None, creative_id=None, workspace_id=None
) -> bool:
    """Polls get_ad_creative to update social_posts with real effective_instagram_media_id and permalink once available."""
    try:
        from bson import ObjectId
        query = {}
        if post_id:
            query["_id"] = ObjectId(str(post_id)) if ObjectId.is_valid(str(post_id)) else str(post_id)
        elif campaign_id:
            query["campaign_id"] = ObjectId(str(campaign_id)) if ObjectId.is_valid(str(campaign_id)) else str(campaign_id)
        elif creative_id:
            query["creative_id"] = str(creative_id)
        elif workspace_id:
            query["workspace_id"] = str(workspace_id)
            query["effective_instagram_media_id"] = None
        else:
            return False

        post = await db.social_posts.find_one(query)
        if not post:
            return False

        if post.get("effective_instagram_media_id"):
            return True

        c_id = creative_id or post.get("creative_id")
        if not c_id and post.get("campaign_id"):
            camp = await db.campaigns.find_one({"_id": post["campaign_id"]})
            if camp:
                c_id = (camp.get("meta") or {}).get("creative_id")
        if not c_id:
            return False

        user_id = post.get("user_id")
        conn = await db.meta_connections.find_one({"user_id": user_id, "status": "ACTIVE"})
        if not conn and post.get("workspace_id"):
            conn = await db.meta_connections.find_one({"workspace_id": post["workspace_id"], "status": "ACTIVE"})
        if not conn:
            return False

        reader, _ = container.gateway_for(conn)
        if not hasattr(reader, "get_ad_creative"):
            return False

        c_info = await reader.get_ad_creative(c_id)
        new_effective_ig_id = c_info.get("effective_instagram_media_id")
        new_permalink = c_info.get("instagram_permalink_url")
        if not new_effective_ig_id:
            return False

        now = container.clock.now()
        post_url = new_permalink or f"https://instagram.com/p/{new_effective_ig_id}"
        await db.social_posts.update_one(
            {"_id": post["_id"]},
            {
                "$set": {
                    "platform_post_id": str(new_effective_ig_id),
                    "effective_instagram_media_id": str(new_effective_ig_id),
                    "post_url": post_url,
                    "creative_id": str(c_id),
                    "updated_at": now,
                }
            },
        )
        if post.get("campaign_id"):
            await db.campaigns.update_one(
                {"_id": post["campaign_id"]},
                {
                    "$set": {
                        "meta.effective_instagram_media_id": str(new_effective_ig_id),
                        "meta.permalink": post_url,
                    }
                },
            )
        log.info("ad_creative_refreshed", post_id=str(post["_id"]), effective_instagram_media_id=str(new_effective_ig_id))
        return True
    except Exception as exc:
        log.warning("refresh_ad_creative_failed", error=str(exc))
        return False


async def poll_creative_refresh_job(
    db, container, campaign_id, creative_id, post_id, delays=(60, 300, 1800)
) -> None:
    for delay in delays:
        try:
            await asyncio.sleep(delay)
            done = await refresh_ad_creative(
                db, container, campaign_id=campaign_id, creative_id=creative_id, post_id=post_id
            )
            if done:
                break
        except Exception:
            pass
