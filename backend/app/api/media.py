from fastapi import APIRouter, Response, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep, DbDep, SettingsDep, UserDep
from app.domain.rules import IMAGE_MAX_BYTES
from app.services import image_store
from app.services.ad_campaigns import get_owned, serialize

router = APIRouter(tags=["media"])


class GenerateImageBody(BaseModel):
    prompt: str = Field("", max_length=500)


class UseImageBody(BaseModel):
    image_id: str = Field(min_length=1, max_length=40)


@router.post("/campaigns/{campaign_id}/image/generate")
async def generate_image(
    campaign_id: str,
    body: GenerateImageBody,
    user: UserDep,
    db: DbDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> dict:
    campaign = await get_owned(db, campaign_id, user["_id"])
    doc = await image_store.generate_campaign_image(
        db, campaign, container.image_generator, extra=body.prompt, settings=settings, clock=container.clock
    )
    return serialize(doc, settings)


@router.post("/campaigns/{campaign_id}/image")
async def upload_image(
    campaign_id: str,
    file: UploadFile,
    user: UserDep,
    db: DbDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> dict:
    campaign = await get_owned(db, campaign_id, user["_id"])
    data = await file.read(IMAGE_MAX_BYTES + 1)  # one byte over lets the size check reject it
    doc = await image_store.upload_campaign_image(
        db, campaign, data, filename=file.filename or "upload", settings=settings, clock=container.clock
    )
    return serialize(doc, settings)


@router.put("/campaigns/{campaign_id}/image")
async def use_image(
    campaign_id: str,
    body: UseImageBody,
    user: UserDep,
    db: DbDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> dict:
    campaign = await get_owned(db, campaign_id, user["_id"])
    doc = await image_store.use_library_image(
        db, campaign, body.image_id, settings=settings, clock=container.clock
    )
    return serialize(doc, settings)


@router.get("/images/{image_id}")
async def get_image(image_id: str, user: UserDep, db: DbDep) -> Response:
    data, content_type = await image_store.load_image(db, image_id, user["_id"])
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/media")
async def list_media(user: UserDep, db: DbDep) -> list[dict]:
    return await image_store.list_images(db, user["_id"])


@router.delete("/media/{image_id}")
async def delete_media(image_id: str, user: UserDep, db: DbDep) -> dict:
    await image_store.delete_image(db, image_id, user["_id"])
    return {"status": "DELETED", "id": image_id}
