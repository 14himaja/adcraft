"""Ad images in GridFS bucket `images` and attaching them to DRAFT campaigns (spec 07 §7)."""

from bson import ObjectId
from bson.errors import InvalidId
from gridfs import AsyncGridFSBucket

from app.clock import Clock
from app.config import Settings
from app.domain.media import ImageRejected, check_instagram_image
from app.errors import AppError, NotFound
from app.media.images import ImageGenerationFailed, ImageGenerator, build_prompt, normalize_square
from app.services.ad_campaigns import require_editable, update_draft

BUCKET = "images"
class ImageInvalid(AppError):
    status, code = 422, "IMAGE_REJECTED"


async def store_image(
    db, data: bytes, *, user_id, campaign_id, source: str, prompt: str, content_type: str, filename: str
) -> str:
    metadata = {
        "user_id": user_id,
        "campaign_id": campaign_id,
        "source": source,
        "prompt": prompt,
        "content_type": content_type,
    }
    bucket = AsyncGridFSBucket(db, bucket_name=BUCKET)
    return str(await bucket.upload_from_stream(filename, data, metadata=metadata))


async def owned_image(db, image_id: str, user_id) -> dict:
    try:
        oid = ObjectId(image_id)
    except (InvalidId, TypeError):
        raise NotFound("Image not found") from None
    file = await db[f"{BUCKET}.files"].find_one({"_id": oid, "metadata.user_id": user_id})
    if file is None:
        raise NotFound("Image not found")
    return file


async def load_image(db, image_id: str, user_id) -> tuple[bytes, str]:
    file = await owned_image(db, image_id, user_id)
    stream = await AsyncGridFSBucket(db, bucket_name=BUCKET).open_download_stream(file["_id"])
    return await stream.read(), file["metadata"]["content_type"]


class ImageInUse(AppError):
    status, code = 409, "IMAGE_IN_USE"


async def list_images(db, user_id) -> list[dict]:
    cursor = db[f"{BUCKET}.files"].find({"metadata.user_id": user_id}).sort([("uploadDate", -1), ("_id", -1)])
    files = [f async for f in cursor]
    camp_ids = []
    for f in files:
        cid = f.get("metadata", {}).get("campaign_id")
        if cid:
            try:
                camp_ids.append(ObjectId(cid) if isinstance(cid, str) else cid)
            except Exception:
                pass
    camp_map = {}
    if camp_ids:
        camps = await db.campaigns.find({"_id": {"$in": camp_ids}}, {"title": 1}).to_list(len(camp_ids))
        camp_map = {str(c["_id"]): c.get("title", "") for c in camps}

    return [
        {
            "id": str(f["_id"]),
            "filename": f["filename"],
            "source": f["metadata"]["source"],
            "prompt": f["metadata"].get("prompt", ""),
            "created_at": f["uploadDate"].isoformat(),
            "source_campaign": camp_map.get(str(f["metadata"].get("campaign_id"))),
        }
        for f in files
    ]


async def delete_image(db, image_id: str, user_id) -> None:
    file = await owned_image(db, image_id, user_id)
    used = await db.campaigns.find_one({"user_id": user_id, "image_id": str(file["_id"])})
    if used:
        raise ImageInUse("Cannot delete an image that is used by a campaign")
    bucket = AsyncGridFSBucket(db, bucket_name=BUCKET)
    await bucket.delete(file["_id"])


async def _attach(db, campaign_id, image_id: str, *, settings: Settings, clock: Clock, actor: str) -> dict:
    fresh = await db.campaigns.find_one({"_id": campaign_id})  # generation can take ~20 s; use the latest rev
    if fresh is None:
        raise NotFound("Campaign not found")
    return await update_draft(db, fresh, {"image_id": image_id}, settings=settings, clock=clock, actor=actor)


async def generate_campaign_image(
    db, campaign: dict, generator: ImageGenerator, *, extra: str, settings: Settings, clock: Clock
) -> dict:
    require_editable(campaign)
    prompt = build_prompt(campaign.get("image_prompt") or campaign.get("title") or "Product photo", extra)
    try:
        data = normalize_square(await generator.generate(prompt))
    except ImageRejected as exc:
        raise ImageGenerationFailed(f"The image model returned an unusable image: {exc}") from exc
    image_id = await store_image(
        db,
        data,
        user_id=campaign["user_id"],
        campaign_id=campaign["_id"],
        source="generated",
        prompt=prompt,
        content_type="image/jpeg",
        filename=f"generated-{campaign['_id']}.jpg",
    )
    return await _attach(db, campaign["_id"], image_id, settings=settings, clock=clock, actor="agent")


async def upload_campaign_image(
    db, campaign: dict, data: bytes, *, filename: str, settings: Settings, clock: Clock
) -> dict:
    require_editable(campaign)
    try:
        check_instagram_image(data)  # reject undersized or unsupported sources before any upscaling
        data = normalize_square(data)
    except ImageRejected as exc:
        raise ImageInvalid(str(exc)) from exc
    image_id = await store_image(
        db,
        data,
        user_id=campaign["user_id"],
        campaign_id=campaign["_id"],
        source="uploaded",
        prompt="",
        content_type="image/jpeg",
        filename=f"{filename.rsplit('.', 1)[0]}.jpg",
    )
    return await _attach(db, campaign["_id"], image_id, settings=settings, clock=clock, actor="user")


async def use_library_image(db, campaign: dict, image_id: str, *, settings: Settings, clock: Clock) -> dict:
    require_editable(campaign)
    await owned_image(db, image_id, campaign["user_id"])
    return await update_draft(db, campaign, {"image_id": image_id}, settings=settings, clock=clock)
