"""Dynamic Social Knowledge Engine: Ingestion, understanding, lifecycle & vector indexing."""

import asyncio
from datetime import UTC, datetime
from bson import ObjectId
from bson.errors import InvalidId

import structlog
from app.agents.post_understanding_agent import understand_post
from app.clock import utcnow
from app.container import Container
from app.errors import NotFound
from app.meta.connections import require_connection
from app.services.embeddings import generate_embedding
from app.services.user_ai import settings_for_user

log = structlog.get_logger()


def _to_oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        raise NotFound("Resource not found") from None


async def ingest_post(
    db,
    container: Container,
    *,
    user_id,
    workspace_id: str,
    platform: str,
    platform_post_id: str,
    ad_id: str | None = None,
    effective_instagram_media_id: str | None = None,
    post_url: str = "",
    title: str = "",
    caption: str = "",
    media_reference: str | None = None,
    media_type: str = "IMAGE",
    campaign_id: str | ObjectId | None = None,
    ad_campaign_status: str = "none",
    source: str = "adcraft",
    published_at: datetime | None = None,
    auto_process: bool = True,
    offer: str | dict | None = None,
    landing_url: str | None = None,
    cta: str | None = None,
    audience: dict | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    creative_id: str | None = None,
) -> dict:
    """Ingests a published post into social_posts idempotently and schedules understanding."""
    now = container.clock.now()
    published_at = published_at or now

    campaign_oid = None
    if campaign_id:
        try:
            campaign_oid = ObjectId(str(campaign_id))
        except (InvalidId, TypeError):
            campaign_oid = None

    filter_query = {
        "workspace_id": workspace_id,
        "platform": platform,
    }
    match_or = [{"platform_post_id": str(platform_post_id)}]
    if ad_id:
        match_or.append({"ad_id": str(ad_id)})
        match_or.append({"platform_post_id": str(ad_id)})
    if effective_instagram_media_id:
        match_or.append({"effective_instagram_media_id": str(effective_instagram_media_id)})
        match_or.append({"platform_post_id": str(effective_instagram_media_id)})
    if campaign_oid:
        match_or.append({"campaign_id": campaign_oid})
    if creative_id:
        match_or.append({"creative_id": str(creative_id)})
    filter_query["$or"] = match_or

    post_doc = {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "platform": platform,
        "platform_post_id": str(platform_post_id),
        "ad_id": str(ad_id) if ad_id else None,
        "creative_id": str(creative_id) if creative_id else None,
        "effective_instagram_media_id": str(effective_instagram_media_id) if effective_instagram_media_id else None,
        "post_url": post_url or f"https://instagram.com/p/{platform_post_id}",
        "title": title or "",
        "caption": caption or "",
        "media_reference": media_reference,
        "media_type": media_type,
        "campaign_id": campaign_oid,
        "published_at": published_at,
        "post_status": "published",
        "ad_campaign_status": ad_campaign_status,
        "source": source,
        "offer": offer,
        "landing_url": landing_url,
        "cta": cta,
        "audience": audience,
        "start_date": start_date,
        "end_date": end_date,
        "updated_at": now,
    }

    existing = await db.social_posts.find_one(filter_query)
    if existing:
        await db.social_posts.update_one(
            {"_id": existing["_id"]},
            {"$set": post_doc},
        )
        post_id = str(existing["_id"])
    else:
        post_doc["knowledge_status"] = "PENDING"
        post_doc["created_at"] = now
        res = await db.social_posts.insert_one(post_doc)
        post_id = str(res.inserted_id)

    # Track knowledge processing job
    await db.knowledge_jobs.update_one(
        {"post_id": post_id, "workspace_id": workspace_id},
        {
            "$set": {
                "job_type": "INGEST",
                "status": "PENDING",
                "updated_at": now,
            },
            "$setOnInsert": {
                "post_id": post_id,
                "workspace_id": workspace_id,
                "retry_count": 0,
                "created_at": now,
            },
        },
        upsert=True,
    )

    if auto_process:
        await container.spawn(process_post_understanding(db, container, post_id))

    return {
        "id": post_id,
        "platform_post_id": platform_post_id,
        "workspace_id": workspace_id,
        "status": "INGESTED",
    }


async def process_post_understanding(db, container: Container, post_id: str) -> dict:
    """Processes post understanding with PostUnderstandingAgent and indexes vector chunks."""
    oid = _to_oid(post_id)
    post = await db.social_posts.find_one({"_id": oid})
    if not post:
        raise NotFound("Post not found")

    workspace_id = post["workspace_id"]
    user_id = post["user_id"]
    now = container.clock.now()

    await db.social_posts.update_one({"_id": oid}, {"$set": {"knowledge_status": "PROCESSING", "updated_at": now}})
    await db.knowledge_jobs.update_one(
        {"post_id": post_id, "workspace_id": workspace_id},
        {"$set": {"status": "PROCESSING", "updated_at": now}},
    )

    try:
        user_settings = await settings_for_user(db, user_id, container.settings)
        extracted = await understand_post(
            platform=post["platform"],
            caption=post.get("caption", ""),
            title=post.get("title", ""),
            media_type=post.get("media_type", "IMAGE"),
            settings=user_settings,
        )

        # 1. Update social_posts with extracted core fields
        await db.social_posts.update_one(
            {"_id": oid},
            {
                "$set": {
                    "post_type": extracted.post_type,
                    "subject": extracted.subject,
                    "summary": extracted.summary,
                    "keywords": extracted.keywords,
                    "knowledge_status": "READY",
                    "updated_at": now,
                }
            },
        )

        # 2. Store or update structured knowledge metadata
        await db.post_knowledge.update_one(
            {"post_id": post_id, "workspace_id": workspace_id},
            {
                "$set": {
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "post_id": post_id,
                    "summary": extracted.summary,
                    "extracted_metadata": extracted.model_dump(),
                    "knowledge_status": "READY",
                    "indexed_version": 1,
                    "processed_at": now,
                }
            },
            upsert=True,
        )

        # 3. Store structured products
        for prod in extracted.products:
            await db.products.update_one(
                {"workspace_id": workspace_id, "product_name": prod.name},
                {
                    "$set": {
                        "workspace_id": workspace_id,
                        "user_id": user_id,
                        "product_name": prod.name,
                        "description": prod.description,
                        "price": prod.price,
                        "currency": prod.currency,
                        "product_status": "active",
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )

        # 4. Store structured offer
        if extracted.offer:
            offer = extracted.offer
            # Check offer expiry
            offer_status = offer.status
            v_until = offer.valid_until or post.get("end_date")
            if v_until:
                try:
                    exp_date = datetime.strptime(v_until, "%Y-%m-%d").date()
                    now_date = now.date() if hasattr(now, "date") else utcnow().date()
                    if exp_date < now_date:
                        offer_status = "EXPIRED"
                except Exception:
                    pass

            await db.offers.update_one(
                {"workspace_id": workspace_id, "post_id": post_id},
                {
                    "$set": {
                        "workspace_id": workspace_id,
                        "user_id": user_id,
                        "post_id": post_id,
                        "offer_description": offer.description,
                        "price": offer.price,
                        "currency": offer.currency,
                        "discount": offer.discount,
                        "valid_from": offer.valid_from or post.get("start_date"),
                        "valid_until": v_until,
                        "terms_and_conditions": offer.terms_and_conditions,
                        "offer_status": offer_status,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
        elif post.get("offer"):
            offer_desc = str(post["offer"])
            offer_status = "ACTIVE"
            v_until = post.get("end_date")
            if v_until:
                try:
                    exp_date = datetime.strptime(v_until, "%Y-%m-%d").date()
                    now_date = now.date() if hasattr(now, "date") else utcnow().date()
                    if exp_date < now_date:
                        offer_status = "EXPIRED"
                except Exception:
                    pass
            await db.offers.update_one(
                {"workspace_id": workspace_id, "post_id": post_id},
                {
                    "$set": {
                        "workspace_id": workspace_id,
                        "user_id": user_id,
                        "post_id": post_id,
                        "offer_description": offer_desc,
                        "valid_from": post.get("start_date"),
                        "valid_until": v_until,
                        "terms_and_conditions": [],
                        "offer_status": offer_status,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )

        # 5. Image fingerprinting and image-to-post indexing
        image_fp = None
        media_ref = post.get("media_reference")
        if media_ref:
            try:
                from app.services.image_matcher import (
                    compute_image_fingerprint,
                    fetch_image_from_gridfs,
                    fetch_image_from_url,
                )
                ref_str = str(media_ref)
                img = None
                if ref_str.startswith("http://") or ref_str.startswith("https://"):
                    img = await fetch_image_from_url(ref_str)
                else:
                    img = await fetch_image_from_gridfs(db, ref_str)
                if img:
                    image_fp = compute_image_fingerprint(img)
                    await db.social_posts.update_one(
                        {"_id": oid},
                        {
                            "$set": {
                                "image_fingerprint": image_fp,
                                "image_hash": image_fp["dhash"],
                                "media_id": str(post.get("platform_post_id") or ""),
                                "updated_at": now,
                            }
                        },
                    )
            except Exception as img_err:
                log.warning("post_image_fingerprint_failed", post_id=post_id, error=str(img_err))

        # 6. Generate and index knowledge chunks with embeddings
        # Clear old chunks for this post
        await db.knowledge_chunks.delete_many({"post_id": post_id, "workspace_id": workspace_id})

        chunks = []
        # Chunk 1: Post Summary
        summary_text = f"Post: {extracted.subject}. Summary: {extracted.summary}"
        chunks.append({
            "chunk_type": "summary",
            "text": summary_text,
            "metadata": {"subject": extracted.subject, "post_type": extracted.post_type},
        })

        # Chunk 2: Full Caption & Keywords
        if post.get("caption"):
            caption_text = f"Caption: {post['caption']}. Keywords: {', '.join(extracted.keywords)}"
            chunks.append({
                "chunk_type": "caption",
                "text": caption_text,
                "metadata": {"keywords": extracted.keywords},
            })

        # Chunk 3: Offer details if present
        if extracted.offer or post.get("offer"):
            off = extracted.offer
            if off:
                off_text = f"Special Offer: {off.description}. Price: ₹{off.price if off.price else 'N/A'}. "
                if off.discount:
                    off_text += f"Discount: {off.discount}. "
                v_until = off.valid_until or post.get("end_date")
                if v_until:
                    off_text += f"Valid until: {v_until}. "
                status = off.status
            else:
                off_text = f"Special Offer: {post['offer']}. "
                if post.get("end_date"):
                    off_text += f"Valid until: {post['end_date']}. "
                status = "ACTIVE"
            chunks.append({
                "chunk_type": "offer",
                "text": off_text,
                "metadata": {"offer_status": status, "valid_until": post.get("end_date") or getattr(off, "valid_until", None)},
            })

        # Chunk 4: Anticipated FAQs
        for faq in extracted.anticipated_faqs:
            faq_text = f"Q: {faq.question} A: {faq.answer}"
            chunks.append({
                "chunk_type": "faq",
                "text": faq_text,
                "metadata": {"question": faq.question},
            })

        # Chunk 5: Campaign Action Details (CTA, Landing URL, Target Audience, Dates)
        action_parts = []
        if post.get("cta"):
            action_parts.append(f"Call to Action: {post['cta']}")
        if post.get("landing_url"):
            action_parts.append(f"Landing URL / Website: {post['landing_url']}")
        if post.get("start_date") or post.get("end_date"):
            action_parts.append(f"Campaign Active Dates: {post.get('start_date', '')} to {post.get('end_date', '')}".strip())
        if post.get("audience"):
            aud = post["audience"]
            if isinstance(aud, dict) and aud.get("interests"):
                names = [i.get("name") if isinstance(i, dict) else str(i) for i in aud["interests"]]
                action_parts.append(f"Target Audience: {', '.join(names)}")
        if action_parts:
            chunks.append({
                "chunk_type": "campaign_action",
                "text": "Campaign Details: " + ". ".join(action_parts),
                "metadata": {
                    "cta": post.get("cta"),
                    "landing_url": post.get("landing_url"),
                    "dates": f"{post.get('start_date', '')} to {post.get('end_date', '')}",
                },
            })

        # Chunk 6: Image visual chunk
        if image_fp:
            chunks.append({
                "chunk_type": "image",
                "text": f"Visual image content of post '{extracted.subject or post.get('title', 'Post')}'. Visual hash: {image_fp['dhash']}. Aspect ratio: {image_fp['aspect_ratio']}.",
                "metadata": {
                    "dhash": image_fp["dhash"],
                    "ahash": image_fp["ahash"],
                    "aspect_ratio": image_fp["aspect_ratio"],
                },
            })

        # Insert chunks with embeddings
        for ch in chunks:
            emb = await generate_embedding(ch["text"], user_settings)
            chunk_doc = {
                "workspace_id": workspace_id,
                "business_id": workspace_id,
                "user_id": user_id,
                "post_id": post_id,
                "platform": post.get("platform", "instagram"),
                "platform_post_id": post["platform_post_id"],
                "ad_id": post.get("ad_id"),
                "effective_instagram_media_id": post.get("effective_instagram_media_id"),
                "campaign_id": str(post.get("campaign_id")) if post.get("campaign_id") else None,
                "post_type": extracted.post_type,
                "post_url": post.get("post_url", ""),
                "chunk_type": ch["chunk_type"],
                "text": ch["text"],
                "embedding": emb,
                "metadata": ch["metadata"],
                "is_active": True,
                "created_at": now,
            }
            await db.knowledge_chunks.insert_one(chunk_doc)

        await db.knowledge_jobs.update_one(
            {"post_id": post_id, "workspace_id": workspace_id},
            {"$set": {"status": "READY", "completed_at": now, "updated_at": now}},
        )

        return {"status": "READY", "post_id": post_id, "chunks_indexed": len(chunks)}

    except Exception as exc:
        log.exception("process_post_understanding_failed", post_id=post_id, error=str(exc))
        await db.social_posts.update_one(
            {"_id": oid},
            {"$set": {"knowledge_status": "FAILED", "updated_at": now}},
        )
        from pymongo import ReturnDocument
        job = await db.knowledge_jobs.find_one_and_update(
            {"post_id": post_id, "workspace_id": workspace_id},
            {
                "$set": {
                    "status": "FAILED",
                    "error_details": str(exc)[:300],
                    "updated_at": now,
                },
                "$inc": {"retry_count": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        retry_count = job.get("retry_count", 1) if job else 1
        MAX_RETRIES = 3
        if retry_count < MAX_RETRIES:
            delay = (2 ** (retry_count - 1)) * 0.5
            if getattr(container, "retry_wait", None) is not None and "wait_none" in str(container.retry_wait):
                delay = 0
            elif getattr(container.settings, "app_env", "") == "test":
                delay = 0

            async def _retry_post_understanding(db_ref, cont_ref, p_id: str, wait_s: float):
                if wait_s > 0:
                    await asyncio.sleep(wait_s)
                await process_post_understanding(db_ref, cont_ref, p_id)

            await container.spawn(_retry_post_understanding(db, container, post_id, delay))

        return {"status": "FAILED", "post_id": post_id, "error": str(exc)}


async def delete_post_knowledge(db, post_id: str, workspace_id: str, source: str = "user") -> dict:
    """Marks post deleted, removes active chunks from vector retrieval, writes audit record."""
    oid = _to_oid(post_id)
    post = await db.social_posts.find_one({"_id": oid, "workspace_id": workspace_id})
    if not post:
        raise NotFound("Post not found")

    now = utcnow()
    # 1. Update post status
    await db.social_posts.update_one(
        {"_id": oid},
        {"$set": {"post_status": "deleted", "knowledge_status": "DELETED", "deleted_at": now, "updated_at": now}},
    )

    # 2. Deactivate vector chunks so they are immediately excluded from retrieval
    await db.knowledge_chunks.update_many(
        {"post_id": post_id, "workspace_id": workspace_id},
        {"$set": {"is_active": False, "updated_at": now}},
    )

    # 3. Deactivate associated offers
    await db.offers.update_many(
        {"post_id": post_id, "workspace_id": workspace_id},
        {"$set": {"offer_status": "INACTIVE", "updated_at": now}},
    )

    # 4. Record deletion audit
    await db.post_deletion_audit.insert_one({
        "workspace_id": workspace_id,
        "post_id": post_id,
        "platform": post.get("platform", "unknown"),
        "platform_post_id": post.get("platform_post_id"),
        "deletion_source": source,
        "deleted_at": now,
    })

    return {"status": "DELETED", "post_id": post_id}


async def reconcile_offers(db, container: Container, workspace_id: str | None = None) -> dict:
    """Checks all active offers for expiry and marks expired ones."""
    now = container.clock.now()
    query = {"offer_status": "ACTIVE"}
    if workspace_id:
        query["workspace_id"] = workspace_id

    cursor = db.offers.find(query)
    expired_count = 0
    async for off in cursor:
        valid_until = off.get("valid_until")
        if valid_until:
            try:
                exp = datetime.strptime(valid_until, "%Y-%m-%d").date()
                now_date = now.date() if hasattr(now, "date") else utcnow().date()
                if exp < now_date:
                    await db.offers.update_one(
                        {"_id": off["_id"]},
                        {"$set": {"offer_status": "EXPIRED", "updated_at": now}},
                    )
                    # Also update chunks metadata
                    await db.knowledge_chunks.update_many(
                        {"post_id": off["post_id"], "chunk_type": "offer"},
                        {"$set": {"metadata.offer_status": "EXPIRED", "updated_at": now}},
                    )
                    expired_count += 1
            except Exception:
                pass

    return {"reconciled_at": now.isoformat(), "expired_count": expired_count}


async def sync_external_posts(db, container: Container, user_id, workspace_id: str) -> dict:
    """Discovers externally published posts from Meta and ingests new ones."""
    connection = await require_connection(db, user_id, clock=container.clock)
    reader, _ = container.gateway_for(connection)

    page_id = connection.get("page_id")
    ig_id = connection.get("instagram_user_id")

    if not (page_id or ig_id):
        return {"synced": 0, "message": "No Facebook Page or Instagram account selected"}

    synced_count = 0
    now = container.clock.now()

    # Discover posts via gateway or direct graph API query
    external_posts = []
    if hasattr(reader, "list_recent_posts"):
        try:
            external_posts = await reader.list_recent_posts(page_id=page_id, ig_user_id=ig_id)
        except Exception as exc:
            log.warning("list_recent_posts_failed", error=str(exc))

    if not external_posts and ig_id:
        try:
            token = getattr(reader, "_token", None) or getattr(reader, "token", None)
            if not token and "token_ciphertext" in connection:
                from app.security.crypto import decrypt_token
                token = decrypt_token(container.settings.token_encryption_key, connection["token_ciphertext"])
            if token:
                import httpx
                url = f"https://graph.facebook.com/v21.0/{ig_id}/media?fields=id,caption,media_type,permalink,timestamp,media_url&limit=25&access_token={token}"
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        for item in resp.json().get("data", []):
                            external_posts.append({
                                "platform": "instagram",
                                "id": str(item.get("id")),
                                "caption": item.get("caption") or "",
                                "permalink": item.get("permalink") or f"https://instagram.com/p/{item.get('id')}",
                                "media_type": item.get("media_type", "IMAGE"),
                                "media_url": item.get("media_url"),
                                "timestamp": item.get("timestamp"),
                            })
                    else:
                        log.warning("graph_api_media_fetch_error", status=resp.status_code, error=resp.text)
        except Exception as ig_fetch_exc:
            log.warning("direct_ig_media_fetch_failed", error=str(ig_fetch_exc))

    for p in external_posts:
        platform = p.get("platform", "instagram")
        p_id = str(p.get("id"))
        caption = p.get("caption") or p.get("message", "")
        first_line = caption.split("\n")[0].strip() if caption else "Instagram Post"
        title = p.get("title") or first_line[:80]
        existing = await db.social_posts.find_one({
            "workspace_id": workspace_id,
            "platform": platform,
            "platform_post_id": p_id,
        })
        if not existing or existing.get("knowledge_status") != "READY":
            await ingest_post(
                db,
                container,
                user_id=user_id,
                workspace_id=workspace_id,
                platform=platform,
                platform_post_id=p_id,
                post_url=p.get("permalink", f"https://instagram.com/p/{p_id}"),
                title=title,
                caption=caption,
                media_reference=p.get("media_url"),
                media_type=p.get("media_type", "IMAGE"),
                source="external_sync",
                published_at=p.get("timestamp") or now,
                auto_process=True,
            )
            synced_count += 1

    return {"synced": synced_count, "total_discovered": len(external_posts)}


async def get_knowledge_status(db, user_id, workspace_id: str) -> dict:
    """Returns operational stats for dynamic knowledge management."""
    total_posts = await db.social_posts.count_documents({"workspace_id": workspace_id})
    active_posts = await db.social_posts.count_documents({"workspace_id": workspace_id, "post_status": "published"})
    deleted_posts = await db.social_posts.count_documents({"workspace_id": workspace_id, "post_status": "deleted"})
    ready_knowledge = await db.social_posts.count_documents({"workspace_id": workspace_id, "knowledge_status": "READY"})
    pending_jobs = await db.knowledge_jobs.count_documents({"workspace_id": workspace_id, "status": "PENDING"})
    failed_jobs = await db.knowledge_jobs.count_documents({"workspace_id": workspace_id, "status": "FAILED"})
    active_offers = await db.offers.count_documents({"workspace_id": workspace_id, "offer_status": "ACTIVE"})
    expired_offers = await db.offers.count_documents({"workspace_id": workspace_id, "offer_status": "EXPIRED"})

    return {
        "workspace_id": workspace_id,
        "total_posts": total_posts,
        "active_posts": active_posts,
        "deleted_posts": deleted_posts,
        "ready_knowledge": ready_knowledge,
        "pending_jobs": pending_jobs,
        "failed_jobs": failed_jobs,
        "active_offers": active_offers,
        "expired_offers": expired_offers,
    }

async def reprocess_pending_or_failed_jobs(db, container: Container) -> int:
    """Finds all PENDING or FAILED knowledge jobs and re-runs understanding."""
    cursor = db.knowledge_jobs.find({"status": {"$in": ["PENDING", "FAILED"]}})
    count = 0
    async for job in cursor:
        post_id = job.get("post_id")
        if not post_id:
            continue
        try:
            oid = _to_oid(post_id)
            post = await db.social_posts.find_one({"_id": oid})
        except Exception:
            post = None
        if post and post.get("post_status") != "deleted":
            await db.knowledge_jobs.update_one(
                {"_id": job["_id"]},
                {"$set": {"status": "PENDING", "updated_at": container.clock.now()}},
            )
            await container.spawn(process_post_understanding(db, container, str(post_id)))
            count += 1
    return count


async def deactivate_campaign_knowledge(db, campaign_id, *, clock=None, status: str = "paused") -> None:
    """Deactivates chunks and updates social posts when a campaign is paused, ended, or deleted."""
    now = clock.now() if clock else utcnow()
    camp_id_str = str(campaign_id)
    camps = [camp_id_str]
    try:
        camps.append(ObjectId(camp_id_str))
    except Exception:
        pass

    set_fields = {"ad_campaign_status": status, "updated_at": now}
    if status == "deleted":
        set_fields["post_status"] = "deleted"
        set_fields["deleted_at"] = now

    await db.social_posts.update_many(
        {"campaign_id": {"$in": camps}},
        {"$set": set_fields},
    )

    post_ids = [str(p["_id"]) async for p in db.social_posts.find({"campaign_id": {"$in": camps}}, {"_id": 1})]

    chunk_filter = [{"campaign_id": {"$in": [camp_id_str, *camps]}}]
    if post_ids:
        chunk_filter.append({"post_id": {"$in": post_ids}})

    await db.knowledge_chunks.update_many(
        {"$or": chunk_filter},
        {"$set": {"is_active": False, "updated_at": now}},
    )

    if post_ids:
        await db.offers.update_many(
            {"post_id": {"$in": post_ids}},
            {"$set": {"offer_status": "INACTIVE", "updated_at": now}},
        )


async def backfill_image_fingerprints(db, workspace_id: str | None = None) -> dict:
    """Computes image fingerprints and hashes for published posts lacking them."""
    from app.services.image_matcher import (
        compute_image_fingerprint,
        fetch_image_from_gridfs,
        fetch_image_from_url,
    )
    query: dict[str, Any] = {
        "post_status": "published",
        "$or": [{"image_hash": None}, {"image_fingerprint": None}],
    }
    if workspace_id:
        query["workspace_id"] = workspace_id

    cursor = db.social_posts.find(query)
    updated, failed = 0, 0
    async for post in cursor:
        ref = post.get("media_reference")
        if not ref:
            continue
        try:
            ref_str = str(ref)
            img = (
                await fetch_image_from_url(ref_str)
                if ref_str.startswith("http")
                else await fetch_image_from_gridfs(db, ref_str)
            )
            if img:
                fp = compute_image_fingerprint(img)
                await db.social_posts.update_one(
                    {"_id": post["_id"]},
                    {
                        "$set": {
                            "image_fingerprint": fp,
                            "image_hash": fp["dhash"],
                            "media_id": str(post.get("platform_post_id") or ""),
                        }
                    },
                )
                updated += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    return {"updated": updated, "failed": failed}


