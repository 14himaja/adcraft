from typing import Annotated

from fastapi import APIRouter, Response, UploadFile
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import ContainerDep, DbDep, SettingsDep, UserDep
from app.domain.rules import IMAGE_MAX_BYTES
from app.services import organic

router = APIRouter(prefix="/organic", tags=["organic"])
public_router = APIRouter(tags=["organic"])  # no login: Instagram fetches the image itself


class PostBody(BaseModel):
    image_id: str = Field(min_length=1, max_length=40)
    caption: Annotated[str, StringConstraints(strip_whitespace=True, max_length=organic.CAPTION_MAX)] = ""
    instagram_user_id: str | None = Field(None, pattern=r"^\w{1,40}$")  # default: the connected account
    selected_hashtags: list[str] = Field(default_factory=list, max_length=5)


class ImagePromptBody(BaseModel):
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


@router.post("/images")
async def upload_image(file: UploadFile, user: UserDep, db: DbDep) -> dict:
    data = await file.read(IMAGE_MAX_BYTES + 1)  # one byte over lets the size check reject it
    return await organic.upload_image(db, user["_id"], data, filename=file.filename or "upload.jpg")


@router.post("/images/generate")
async def generate_image(body: ImagePromptBody, user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    return await organic.generate_image(db, container, user["_id"], body.prompt)


@router.get("/accounts")
async def accounts(user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    return await organic.list_accounts(db, container, user["_id"])


@router.post("/posts")
async def publish(body: PostBody, user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    return await organic.publish_post(
        db,
        container,
        user["_id"],
        body.image_id,
        body.caption,
        body.instagram_user_id,
        body.selected_hashtags,
    )


@router.get("/posts")
async def posts(user: UserDep, db: DbDep) -> list[dict]:
    return await organic.list_posts(db, user["_id"])


@router.delete("/posts/{post_id}")
async def delete_post(post_id: str, user: UserDep, db: DbDep) -> dict:
    return await organic.delete_post(db, user["_id"], post_id)



@public_router.get("/public/images/{image_id}")
async def public_image(image_id: str, sig: str, db: DbDep, settings: SettingsDep) -> Response:
    clean_id = image_id.removesuffix(".jpg").removesuffix(".jpeg")
    data, content_type = await organic.load_public_image(db, settings, clean_id, sig)
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=300",
            "Content-Disposition": f'inline; filename="{clean_id}.jpg"',
        },
    )
