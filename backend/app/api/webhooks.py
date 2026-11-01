import hashlib
import hmac
import json

import structlog
from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

from app import audit
from app.api.deps import ContainerDep, DbDep, SettingsDep
from app.clock import utcnow
from app.errors import AppError
from app.services import dm

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = structlog.get_logger()


class Forbidden(AppError):
    status, code = 403, "FORBIDDEN"


def _signature_ok(secret: str, body: bytes, header: str) -> bool:
    if not secret or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


@router.get("/instagram", response_class=PlainTextResponse)
async def verify(
    db: DbDep,
    settings: SettingsDep,
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
) -> str:
    expected = settings.meta_webhook_verify_token
    ok = mode == "subscribe" and bool(expected) and hmac.compare_digest(token, expected)
    await db.webhook_status.update_one(
        {"_id": "instagram"}, {"$set": {"verified": ok, "checked_at": utcnow()}}, upsert=True
    )
    if not ok:
        raise Forbidden("Webhook verification failed")
    return challenge


async def _handle(db, container, event: dict) -> None:
    try:
        await dm.handle_messaging(db, container, event)
    except Exception:  # a bad event must not stop the rest of the batch
        log.exception("dm_event_failed")


def _extract_events(payload: dict) -> list[dict]:
    events: list[dict] = []
    for entry in payload.get("entry", []):
        entry_id = entry.get("id")
        for m in entry.get("messaging", []):
            if isinstance(m, dict):
                ev = dict(m)
                if entry_id and "entry_id" not in ev:
                    ev["entry_id"] = entry_id
                events.append(ev)
        for change in entry.get("changes", []):
            if not isinstance(change, dict):
                continue
            val = change.get("value")
            if isinstance(val, dict):
                if isinstance(val.get("messaging"), list):
                    for m in val["messaging"]:
                        if isinstance(m, dict):
                            ev = dict(m)
                            if entry_id and "entry_id" not in ev:
                                ev["entry_id"] = entry_id
                            events.append(ev)
                elif any(
                    k in val for k in ("message", "reaction", "story_mention", "story_reply", "postback")
                ):
                    ev = dict(val)
                    if entry_id and "entry_id" not in ev:
                        ev["entry_id"] = entry_id
                    events.append(ev)
    return events


@router.post("/instagram")
async def receive(request: Request, db: DbDep, settings: SettingsDep, container: ContainerDep) -> dict:
    body = await request.body()
    if not _signature_ok(settings.meta_app_secret, body, request.headers.get("x-hub-signature-256", "")):
        log.warning("instagram_webhook_delivery", object="instagram", event_count=0, signature_ok=False)
        raise Forbidden("Bad webhook signature")
    try:
        payload = json.loads(body)
    except ValueError:
        raise Forbidden("Bad webhook body") from None
    events = _extract_events(payload)
    log.info(
        "instagram_webhook_delivery", object=payload.get("object"),
        event_count=len(events), signature_ok=True,
    )
    if settings.app_env != "production":
        await audit.record(
            db, actor="system", event_type="WEBHOOK_RAW",
            payload={"object": payload.get("object"), "body": body[:4096].decode("utf-8", errors="replace")},
        )
    for event in events:
        await container.spawn(_handle(db, container, event))
    return {"ok": True}
