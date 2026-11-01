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
) -> dict:
    """Ingests a published post into social_posts idempotently and schedules understanding."""
    now = container.clock.now()
    published_at = published_at or now

    filter_query = {
        "workspace_id": workspace_id,
        "platform": platform,
        "platform_post_id": str(platform_post_id),
    }

    campaign_oid = None
    if campaign_id:
        try:
            campaign_oid = ObjectId(str(campaign_id))
        except (InvalidId, TypeError):
            campaign_oid = None

    post_doc = {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "platform": platform,
        "platform_post_id": str(platform_post_id),
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
            if offer.valid_until:
                try:
                    exp_date = datetime.strptime(offer.valid_until, "%Y-%m-%d").date()
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
                        "valid_from": offer.valid_from,
                        "valid_until": offer.valid_until,
                        "terms_and_conditions": offer.terms_and_conditions,
                        "offer_status": offer_status,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )

        # 5. Generate and index knowledge chunks with embeddings
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
        if extracted.offer:
            off = extracted.offer
            off_text = f"Special Offer: {off.description}. Price: ₹{off.price if off.price else 'N/A'}. "
            if off.discount:
                off_text += f"Discount: {off.discount}. "
            if off.valid_until:
                off_text += f"Valid until: {off.valid_until}. "
            chunks.append({
                "chunk_type": "offer",
                "text": off_text,
                "metadata": {"offer_status": off.status, "valid_until": off.valid_until},
            })

        # Chunk 4: Anticipated FAQs
        for faq in extracted.anticipated_faqs:
            faq_text = f"Q: {faq.question} A: {faq.answer}"
            chunks.append({
                "chunk_type": "faq",
                "text": faq_text,
                "metadata": {"question": faq.question},
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
        await db.knowledge_jobs.update_one(
            {"post_id": post_id, "workspace_id": workspace_id},
            {
                "$set": {
                    "status": "FAILED",
                    "error_details": str(exc)[:300],
                    "updated_at": now,
                },
                "$inc": {"retry_count": 1},
            },
        )
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
