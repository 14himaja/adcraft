from app.domain.workspaces import resolve_workspace_id
"""Organic Instagram feed posts from the connected account (not ads: no spend, no campaign).

Meta fetches the picture itself, so it is served from a signed public URL (PUBLIC_BASE_URL) that only
works for the exact image id it was signed for.
"""

import asyncio
import hashlib
import hmac
from io import BytesIO

from bson import ObjectId
from bson.errors import InvalidId
from gridfs import AsyncGridFSBucket
from PIL import Image, UnidentifiedImageError
import structlog

log = structlog.get_logger()

from app.config import Settings
from app.container import Container
from app.domain.hashtags import format_caption_with_hashtags, validate_hashtag_list
from app.domain.media import ImageRejected, check_instagram_image
from app.errors import AppError, NotFound
from app.media.images import ImageGenerationFailed, normalize_square
from app.meta.connections import require_connection
from app.meta.errors import ErrorClass, MetaError, classify
from app.services import image_store

CAPTION_MAX = 2200  # Instagram's caption limit
NO_INSTAGRAM = "No Instagram professional account is linked to this Facebook Page"


class PublishNotReady(AppError):
    status, code = 409, "ORGANIC_PUBLISH_NOT_READY"


class PostFailed(AppError):
    status, code = 502, "INSTAGRAM_POST_FAILED"


class AccountUnavailable(AppError):
    status, code = 422, "INSTAGRAM_ACCOUNT_UNAVAILABLE"


def _sig(settings: Settings, image_id: str) -> str:
    clean_id = image_id.removesuffix(".jpg").removesuffix(".jpeg")
    key = settings.jwt_secret.encode()
    return hmac.new(key, f"public-image:{clean_id}".encode(), hashlib.sha256).hexdigest()[:32]


def public_image_url(settings: Settings, image_id: str, mode: str = "real") -> str:
    base = (settings.public_base_url or "").rstrip("/")
    if not (base.startswith("https://") or (base.startswith("http://") and settings.app_env in ("development", "test", "local"))):
        raise PublishNotReady(
            "Set PUBLIC_BASE_URL to a public https address so Instagram can fetch the image"
        )
    clean_id = image_id.removesuffix(".jpg").removesuffix(".jpeg")
    return f"{base.rstrip('/')}/public/images/{clean_id}?sig={_sig(settings, clean_id)}"


async def load_public_image(db, settings: Settings, image_id: str, sig: str) -> tuple[bytes, str]:
    clean_id = image_id.removesuffix(".jpg").removesuffix(".jpeg")
    if not hmac.compare_digest(sig, _sig(settings, clean_id)):
        raise NotFound("Image not found")
    try:
        oid = ObjectId(clean_id)
    except (InvalidId, TypeError):
        raise NotFound("Image not found") from None
    file = await db[f"{image_store.BUCKET}.files"].find_one({"_id": oid})
    if file is None:
        raise NotFound("Image not found")
    stream = await AsyncGridFSBucket(db, bucket_name=image_store.BUCKET).open_download_stream(file["_id"])
    content_type = (file.get("metadata") or {}).get("content_type", "image/jpeg")
    return await stream.read(), content_type


def _to_jpeg(data: bytes) -> bytes:
    """Instagram's publishing API only takes JPEG; keep the uploaded framing."""
    try:
        check_instagram_image(data)
        with Image.open(BytesIO(data)) as img:
            out = BytesIO()
            img.convert("RGB").save(out, format="JPEG", quality=90)
    except (ImageRejected, UnidentifiedImageError, OSError) as exc:
        raise image_store.ImageInvalid(str(exc)) from exc
    return out.getvalue()


async def _store(db, user_id, data: bytes, *, source: str, prompt: str, filename: str) -> dict:
    image_id = await image_store.store_image(
        db,
        data,
        user_id=user_id,
        campaign_id=None,
        source=source,
        prompt=prompt,
        content_type="image/jpeg",
        filename=filename,
    )
    return {"id": image_id, "source": source, "prompt": prompt, "filename": filename}


async def upload_image(db, user_id, data: bytes, *, filename: str) -> dict:
    return await _store(db, user_id, _to_jpeg(data), source="uploaded", prompt="", filename=filename)


async def generate_image(db, container: Container, user_id, prompt: str) -> dict:
    try:
        data = normalize_square(await container.image_generator.generate(prompt))
    except ImageRejected as exc:
        raise ImageGenerationFailed(f"The image model returned an unusable image: {exc}") from exc
    return await _store(db, user_id, data, source="generated", prompt=prompt, filename="post.jpg")


async def list_accounts(db, container: Container, user_id) -> dict:
    """Instagram accounts this login can post to, and the Pages that cannot be used (with why)."""
    connection = await require_connection(db, user_id, clock=container.clock)
    reader, _ = container.gateway_for(connection)
    pages = await reader.list_pages()
    linked = await asyncio.gather(*(reader.instagram_account_for_page(p["id"]) for p in pages))
    accounts, unavailable = [], []
    for page, ig in zip(pages, linked, strict=True):
        if ig:
            accounts.append(
                {
                    "instagram_user_id": ig["id"],
                    "username": ig["username"],
                    "page_id": page["id"],
                    "page_name": page["name"],
                }
            )
        else:
            unavailable.append({"page_id": page["id"], "page_name": page["name"], "reason": NO_INSTAGRAM})
    return {"default": connection.get("instagram_user_id"), "accounts": accounts, "unavailable": unavailable}


async def publish_post(
    db,
    container: Container,
    user_id,
    image_id: str,
    caption: str,
    instagram_user_id: str | None = None,
    selected_hashtags: list[str] | None = None,
) -> dict:
    settings = container.settings
    connection = await require_connection(db, user_id, clock=container.clock)
    target = instagram_user_id or connection.get("instagram_user_id")
    if not target:
        raise PublishNotReady("Choose which Instagram account to post to")
    if target != connection.get("instagram_user_id") and target not in {
        a["instagram_user_id"] for a in (await list_accounts(db, container, user_id))["accounts"]
    }:
        raise AccountUnavailable(
            "This login cannot post to that Instagram account. It must be a Business or Creator account "
            "linked to a Facebook Page you manage, or its owner can connect their own login."
        )
    if connection["mode"] == "real" and not settings.allow_organic_publish:
        raise PublishNotReady(
            "Posting to Instagram is switched off on this server (ALLOW_ORGANIC_PUBLISH=false)"
        )
    await image_store.owned_image(db, image_id, user_id)
    url = public_image_url(settings, image_id, mode=connection.get("mode", "real"))
    _, writer = container.gateway_for(connection)
    
    # Format feed caption with selected hashtags (max 5, deduplicated, clean spacing)
    valid_tags, _ = validate_hashtag_list(selected_hashtags or [])
    published_caption = format_caption_with_hashtags(caption, valid_tags)[:CAPTION_MAX]

    post = {
        "user_id": user_id,
        "image_id": image_id,
        "caption": published_caption,
        "selected_hashtags": valid_tags,
        "ig_user_id": target,
        "created_at": container.clock.now(),
    }
    try:
        media_id = await writer.publish_photo(post["ig_user_id"], url, published_caption)
        post |= {"status": "PUBLISHED", "media_id": media_id}
    except (MetaError, TimeoutError, ConnectionError) as exc:
        post |= {"status": "FAILED", "error": str(exc)[:300]}
    await db.organic_posts.insert_one(post)
    if post["status"] == "FAILED":
        raise PostFailed(f"Instagram did not accept the post: {post['error']}")
    try:
        user = await db.users.find_one({"_id": user_id}) or {}
        ws_id = resolve_workspace_id(user=user)
        from app.services import social_knowledge
        await social_knowledge.ingest_post(
            db,
            container,
            user_id=user_id,
            workspace_id=ws_id,
            platform="instagram",
            platform_post_id=str(post.get("media_id")),
            title=f"Instagram Post ({caption[:30]}...)" if caption else "Instagram Post",
            caption=published_caption,
            media_reference=image_id,
            source="adcraft",
            auto_process=True,
        )
    except Exception:
        pass
    return _view(post)


FACEBOOK_PERMISSION = (
    "Facebook posting needs the pages_manage_posts permission. Add it to your Meta login configuration, "
    "then Disconnect and Connect with Facebook again."
)


async def post_campaign(db, container: Container, user_id, campaign: dict, targets: list[str]) -> dict:
    """Post the ad's picture and text as normal free posts (not ads). Each target is tried on its own."""
    settings = container.settings
    if not campaign.get("image_id"):
        raise PublishNotReady("Add an image to the ad first")
    connection = await require_connection(db, user_id, clock=container.clock)
    if connection["mode"] == "real" and not settings.allow_organic_publish:
        raise PublishNotReady("Posting is switched off on this server (ALLOW_ORGANIC_PUBLISH=false)")
    url = public_image_url(settings, campaign["image_id"], mode=connection.get("mode", "real"))
    variant = (campaign.get("variants") or [{}])[campaign.get("selected_variant", 0)]
    parts = (variant.get("headline"), variant.get("primary_text"))
    raw_caption = "\n\n".join(p for p in parts if p)[:CAPTION_MAX]
    hashtags = campaign.get("selected_hashtags") or []
    feed_caption = format_caption_with_hashtags(raw_caption, hashtags)[:CAPTION_MAX]
    _, writer = container.gateway_for(connection)
    page_id, ig_id = connection.get("page_id"), connection.get("instagram_user_id")
    post = {
        "facebook_feed": lambda: writer.publish_facebook_photo(page_id, url, feed_caption),
        "facebook_story": lambda: writer.publish_facebook_story(page_id, url),
        "instagram_feed": lambda: writer.publish_photo(ig_id, url, feed_caption),
        "instagram_story": lambda: writer.publish_photo(ig_id, url, raw_caption, story=True),
    }
    results, posted = {}, {}
    for target in dict.fromkeys(targets):
        try:
            if target.startswith("facebook") and not page_id:
                raise PublishNotReady("No Facebook Page is selected. Please select a Facebook Page in Connected Accounts settings.")
            if target.startswith("instagram") and not ig_id:
                raise PublishNotReady(NO_INSTAGRAM)
            media_id = await post[target]()
            results[target] = {"status": "PUBLISHED", "media_id": media_id, "post_id": media_id}
            posted[f"posted.{target}"] = {"media_id": media_id, "at": container.clock.now().isoformat()}
        except (AppError, MetaError, TimeoutError, ConnectionError) as exc:
            denied = isinstance(exc, MetaError) and classify(exc) == ErrorClass.PERMISSION
            error = FACEBOOK_PERMISSION if denied and target.startswith("facebook") else str(exc)[:300]
            results[target] = {"status": "FAILED", "error": error}
        is_feed = target in ("facebook_feed", "instagram_feed")
        await db.organic_posts.insert_one(
            {
                "user_id": user_id,
                "image_id": campaign["image_id"],
                "caption": feed_caption if is_feed else raw_caption,
                "selected_hashtags": hashtags if is_feed else [],
                "campaign_id": campaign["_id"],
                "target": target,
                "created_at": container.clock.now(),
                **results[target],
            }
        )
        if results[target].get("status") == "PUBLISHED" and results[target].get("media_id"):
            try:
                user = await db.users.find_one({"_id": user_id}) or {}
                ws_id = resolve_workspace_id(campaign=campaign, user=user)
                from app.services import social_knowledge
                is_story = target.endswith("story")
                post_url = f"https://instagram.com/p/{results[target]['media_id']}" if target.startswith("instagram") and not is_story else ""
                await social_knowledge.ingest_post(
                    db,
                    container,
                    user_id=user_id,
                    workspace_id=ws_id,
                    platform="facebook" if target.startswith("facebook") else "instagram",
                    platform_post_id=str(results[target]["media_id"]),
                    post_url=post_url,
                    title=campaign.get("title", ""),
                    caption=feed_caption if is_feed else raw_caption,
                    media_reference=campaign.get("image_id"),
                    media_type="STORY" if is_story else "IMAGE",
                    campaign_id=campaign["_id"],
                    source="adcraft",
                    auto_process=True,
                )
                log.info(
                    "organic_knowledge_ingestion_scheduled",
                    target=target,
                    media_id=results[target]["media_id"],
                    workspace_id=ws_id,
                )
            except Exception as ing_exc:
                log.error(
                    "organic_knowledge_ingestion_failed",
                    target=target,
                    media_id=results[target].get("media_id"),
                    error=str(ing_exc),
                )
    if posted:
        await db.campaigns.update_one({"_id": campaign["_id"]}, {"$set": posted})
    return {"campaign_id": str(campaign["_id"]), "results": results}


def _view(post: dict) -> dict:
    return {
        "id": str(post["_id"]),
        "image_id": post["image_id"],
        "caption": post["caption"],
        "selected_hashtags": post.get("selected_hashtags", []),
        "status": post["status"],
        "media_id": post.get("media_id"),
        "ig_user_id": post.get("ig_user_id"),
        "error": post.get("error"),
        "created_at": post["created_at"].isoformat(),
    }


async def list_posts(db, user_id, *, limit: int = 50) -> list[dict]:
    cursor = db.organic_posts.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    return [_view(p) async for p in cursor]


async def delete_post(db, user_id, post_id: str) -> dict:
    try:
        oid = ObjectId(post_id)
    except (InvalidId, TypeError):
        raise NotFound("Post not found") from None
    post = await db.organic_posts.find_one({"_id": oid, "user_id": user_id})
    if not post:
        raise NotFound("Post not found")
    result = await db.organic_posts.delete_one({"_id": oid, "user_id": user_id})
    if result.deleted_count == 0:
        raise NotFound("Post not found")
    try:
        user = await db.users.find_one({"_id": user_id}) or {}
        ws_id = resolve_workspace_id(user=user)
        from app.services import social_knowledge
        soc = await db.social_posts.find_one({
            "workspace_id": ws_id,
            "$or": [
                {"platform_post_id": str(post.get("media_id"))},
                {"media_reference": post.get("image_id")},
            ]
        })
        if soc:
            await social_knowledge.delete_post_knowledge(db, str(soc["_id"]), ws_id, source="user")
    except Exception:
        pass
    return {"status": "DELETED", "id": post_id}

