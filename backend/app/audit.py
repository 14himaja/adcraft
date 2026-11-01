from app.clock import utcnow
from app.observability import correlation_id_var

ACTORS = ("user", "agent", "system")


async def record(
    db,
    *,
    actor: str,
    event_type: str,
    payload: dict,
    user_id=None,
    campaign_id=None,
    session=None,
) -> None:
    if actor not in ACTORS:
        raise ValueError(f"unknown actor {actor!r}")
    await db.audit_log.insert_one(
        {
            "ts": utcnow(),
            "actor": actor,
            "event_type": event_type,
            "payload": payload,
            "user_id": user_id,
            "campaign_id": campaign_id,
            "correlation_id": correlation_id_var.get(),
        },
        session=session,
    )


async def latest_event(db, user_id, event_types: tuple[str, ...]) -> dict | None:
    """Read the latest matching audit event without leaking audit collection access elsewhere."""
    return await db.audit_log.find_one(
        {"user_id": user_id, "event_type": {"$in": list(event_types)}}, sort=[("ts", -1)]
    )
