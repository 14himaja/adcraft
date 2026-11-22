from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from gridfs import AsyncGridFSBucket

from app import audit
from app.config import Settings
from app.domain.hashtags import format_caption_with_hashtags, validate_hashtag_list
from app.integrations.base.errors import IntegrationAuthExpired, IntegrationNotConnected
from app.integrations.base.models import PlatformId, PublishContent, PublishResult
from app.integrations.oauth import tenant_scope
from app.integrations.registry import get_adapter
from app.integrations.service import _ensure_active_token
from app.services import image_store, organic


async def _load_image_payload(
    db, settings: Settings, user_id, image_id: str | None
) -> tuple[str | None, bytes | None, str | None]:
    if not image_id:
        return None, None, None
    await image_store.owned_image(db, image_id, user_id)
    try:
        oid = ObjectId(image_id)
    except (InvalidId, TypeError):
        return None, None, None
    file_doc = await db[f"{image_store.BUCKET}.files"].find_one({"_id": oid})
    data = None
    content_type = "image/jpeg"
    if file_doc is not None:
        stream = await AsyncGridFSBucket(db, bucket_name=image_store.BUCKET).open_download_stream(file_doc["_id"])
        data = await stream.read()
        content_type = (file_doc.get("metadata") or {}).get("content_type", "image/jpeg")

    url = None
    if (settings.public_base_url or "").startswith(("http://", "https://")):
        try:
            url = organic.public_image_url(settings, image_id)
        except Exception:
            url = None
    return url, data, content_type


async def preview_multi_publish(
    db,
    user: dict,
    *,
    platforms: list[PlatformId],
    text: str,
    title: str | None,
    link_url: str | None,
    image_id: str | None,
    hashtags: list[str],
    targets: dict[str, str],
    settings: Settings,
    clock,
) -> dict[str, Any]:
    user_id, org_id, _ = tenant_scope(user)
    valid_tags, tag_errors = validate_hashtag_list(hashtags or [])
    previews: dict[str, Any] = {}

    for pid in dict.fromkeys(platforms):
        adapter = get_adapter(pid)
        defn = adapter.definition(settings)
        errors: list[str] = list(tag_errors)
        conn_status = "NOT_CONNECTED"
        target_id = targets.get(pid)
        target_name = None
        try:
            conn, _ = await _ensure_active_token(db, user_id, org_id, pid, settings=settings, clock=clock)
            conn_status = conn.get("status", "ACTIVE")
            target_id = target_id or conn.get("selected_target_id") or conn.get("platform_account_id")
            target_name = conn.get("selected_target_name") or conn.get("account_display_name")
            content = PublishContent(
                text=text,
                title=title,
                link_url=link_url,
                image_id=image_id,
                hashtags=valid_tags,
                target_id=target_id,
                target_name=target_name,
            )
            errors.extend(adapter.validate_publish(content, conn))
        except (IntegrationNotConnected, IntegrationAuthExpired) as exc:
            errors.append(exc.message)

        formatted_text = format_caption_with_hashtags(text or "", valid_tags)
        if link_url and pid == "x" and link_url not in formatted_text:
            formatted_text = f"{formatted_text}\n{link_url}".strip()

        previews[pid] = {
            "platform": pid,
            "name": defn.name,
            "connection_status": conn_status,
            "target_id": target_id,
            "target_name": target_name,
            "formatted_text": formatted_text,
            "character_count": len(formatted_text),
            "max_text_length": defn.capabilities.max_text_length,
            "valid": len(errors) == 0,
            "errors": errors,
        }

    return {"previews": previews}


async def publish_multi_platform(
    db,
    user: dict,
    *,
    platforms: list[PlatformId],
    text: str,
    title: str | None,
    link_url: str | None,
    image_id: str | None,
    hashtags: list[str],
    targets: dict[str, str],
    settings: Settings,
    clock,
    container=None,
) -> dict[str, Any]:
    user_id, org_id, tenant_id = tenant_scope(user)
    valid_tags, _ = validate_hashtag_list(hashtags or [])
    image_url, image_bytes, image_ct = await _load_image_payload(db, settings, user_id, image_id)
    now = clock.now()

    results: dict[str, dict[str, Any]] = {}
    for pid in dict.fromkeys(platforms):
        adapter = get_adapter(pid)
        try:
            conn, access_token = await _ensure_active_token(
                db, user_id, org_id, pid, settings=settings, clock=clock
            )
            target_id = targets.get(pid) or conn.get("selected_target_id") or conn.get("platform_account_id")
            target_name = conn.get("selected_target_name") or conn.get("account_display_name")
            if conn.get("mode") == "fake" and image_id and not image_url:
                image_url = f"https://fake.adcraft.local/public/images/{image_id}"

            content = PublishContent(
                text=text,
                title=title,
                link_url=link_url,
                image_id=image_id,
                image_url=image_url,
                image_bytes=image_bytes,
                image_content_type=image_ct,
                hashtags=valid_tags,
                target_id=target_id,
                target_name=target_name,
                media_type="IMAGE" if image_id else ("LINK" if link_url else "TEXT"),
            )
            validation_errors = adapter.validate_publish(content, conn)
            if validation_errors:
                result = PublishResult(
                    platform=pid,
                    status="FAILED",
                    target_id=target_id,
                    target_name=target_name,
                    error="; ".join(validation_errors),
                    error_code="PLATFORM_VALIDATION_FAILED",
                )
            else:
                result = await adapter.publish(
                    access_token, content, conn, settings, container=container
                )
        except (IntegrationNotConnected, IntegrationAuthExpired) as exc:
            result = PublishResult(
                platform=pid,
                status="FAILED",
                error=exc.message,
                error_code=exc.code,
            )

        res_dict = result.to_dict()
        results[pid] = res_dict
        await db.social_publish_history.insert_one(
            {
                "user_id": user_id,
                "organization_id": org_id,
                "tenant_id": tenant_id,
                "platform": pid,
                "title": title,
                "text": text,
                "link_url": link_url,
                "image_id": image_id,
                "hashtags": valid_tags,
                "target_id": result.target_id,
                "target_name": result.target_name,
                "status": result.status,
                "platform_post_id": result.platform_post_id,
                "post_url": result.post_url,
                "error": result.error,
                "error_code": result.error_code,
                "created_at": now,
            }
        )

    await audit.record(
        db,
        actor="user",
        event_type="MULTI_PLATFORM_PUBLISH",
        payload={
            "organization_id": org_id,
            "platforms": list(results.keys()),
            "published": [p for p, r in results.items() if r["status"] == "PUBLISHED"],
            "failed": [p for p, r in results.items() if r["status"] == "FAILED"],
        },
        user_id=user_id,
    )
    return {"results": results}


async def list_publish_history(db, user: dict, *, limit: int = 50) -> list[dict]:
    user_id, org_id, _ = tenant_scope(user)
    cursor = db.social_publish_history.find(
        {"user_id": user_id, "organization_id": org_id}
    ).sort("created_at", -1).limit(limit)
    items: list[dict] = []
    async for doc in cursor:
        items.append(
            {
                "id": str(doc["_id"]),
                "platform": doc["platform"],
                "title": doc.get("title"),
                "text": doc.get("text", ""),
                "link_url": doc.get("link_url"),
                "image_id": doc.get("image_id"),
                "hashtags": doc.get("hashtags", []),
                "target_id": doc.get("target_id"),
                "target_name": doc.get("target_name"),
                "status": doc["status"],
                "platform_post_id": doc.get("platform_post_id"),
                "post_url": doc.get("post_url"),
                "error": doc.get("error"),
                "created_at": doc["created_at"].isoformat(),
            }
        )
    return items

