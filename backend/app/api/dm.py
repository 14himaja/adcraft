from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, Field, StringConstraints

from app import audit
from app.api.deps import ContainerDep, DbDep, UserDep
from app.services import dm

router = APIRouter(prefix="/dm", tags=["dm"])
Text = Annotated[str, StringConstraints(strip_whitespace=True)]


class ConfigBody(BaseModel):
    enabled: bool
    business_name: Text = Field("", max_length=120)
    tone: Text = Field("Friendly and concise", max_length=200)
    knowledge: Text = Field("", max_length=6000)
    handoff_message: Text = Field(dm.DEFAULT_HANDOFF, min_length=1, max_length=300)


class MessageBody(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    post_id: str | None = None


@router.get("/config")
async def get_config(user: UserDep, db: DbDep) -> dict:
    return await dm.get_config(db, user["_id"])


@router.put("/config")
async def save_config(body: ConfigBody, user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    return await dm.save_config(db, container, user["_id"], body.model_dump())


@router.post("/preview")
async def preview(body: MessageBody, user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    return await dm.preview(db, container, user["_id"], body.message, post_id=body.post_id)


@router.get("/escalations")
async def escalations(user: UserDep, db: DbDep, container: ContainerDep) -> list[dict]:
    cursor = db.dm_threads.find({"user_id": user["_id"], "status": "NEEDS_HUMAN"}).sort("updated_at", -1)
    return [dm._view(t, container.clock.now()) async for t in cursor]


@router.get("/threads")
async def threads(user: UserDep, db: DbDep, container: ContainerDep) -> list[dict]:
    return await dm.list_threads(db, user["_id"], now=container.clock.now())


@router.get("/summary")
async def summary(user: UserDep, db: DbDep) -> dict:
    return await dm.summary(db, user["_id"])


@router.get("/status")
async def status(user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    summary = await dm.summary(db, user["_id"])
    verification = await db.webhook_status.find_one({"_id": "instagram"})
    latest_error = await audit.latest_event(db, user["_id"], ("DM_AI_FAILED", "DM_SEND_FAILED"))
    connection = await db.meta_connections.find_one({"user_id": user["_id"], "status": "ACTIVE"})
    subscribed = False
    if connection:
        try:
            gateway, _ = container.gateway_for(connection)
            subscribed = await gateway.messages_subscribed(connection["page_id"])
        except Exception:
            subscribed = False
    return {
        "agent_enabled": summary["enabled"],
        "webhook_verified": bool(verification and verification.get("verified")),
        "webhook_subscribed": subscribed,
        "last_inbound_at": summary["last_inbound_at"],
        "last_error": latest_error["event_type"] if latest_error else None,
    }


@router.get("/threads/{thread_id}")
async def thread(thread_id: str, user: UserDep, db: DbDep) -> dict:
    return await dm.get_thread(db, user["_id"], thread_id)


@router.post("/threads/{thread_id}/reply")
async def reply(thread_id: str, body: MessageBody, user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    return await dm.reply_as_human(db, container, user["_id"], thread_id, body.message)


@router.post("/threads/{thread_id}/resume")
async def resume(thread_id: str, user: UserDep, db: DbDep) -> dict:
    return await dm.resume_bot(db, user["_id"], thread_id)


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, user: UserDep, db: DbDep) -> dict:
    await dm.delete_thread(db, user["_id"], thread_id)
    return {"status": "DELETED"}
