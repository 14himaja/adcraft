import hashlib
import json

from pymongo import ReturnDocument

from app import audit
from app.clock import Clock

SNAPSHOT_KEYS = ("requirements", "plan", "assets")


def content_hash(data: dict) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def snapshot(version_doc: dict) -> dict:
    return {key: version_doc.get(key) for key in SNAPSHOT_KEYS}


async def create_version(
    db,
    campaign_id,
    *,
    requirements: dict,
    plan: dict | None,
    assets: dict | None,
    created_by: str,
    change_summary: str,
    clock: Clock,
    session=None,
) -> dict:
    campaign = await db.campaigns.find_one_and_update(
        {"_id": campaign_id},
        {"$inc": {"current_version": 1}},
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    now = clock.now()
    data = {"requirements": requirements, "plan": plan, "assets": assets}
    version = {
        "campaign_id": campaign_id,
        "version": campaign["current_version"],
        **data,
        "content_hash": content_hash(data),
        "created_by": created_by,
        "change_summary": change_summary,
        "created_at": now,
        "schema_version": 1,
    }
    await db.campaign_versions.insert_one(version, session=session)
    revoked = await db.approvals.update_many(
        {"campaign_id": campaign_id, "revoked_at": None},
        {"$set": {"revoked_at": now}},
        session=session,
    )
    if revoked.modified_count:
        await audit.record(
            db,
            actor="system",
            event_type="APPROVAL_REVOKED",
            payload={"reason": f"version {version['version']} created"},
            campaign_id=campaign_id,
            session=session,
        )
    await audit.record(
        db,
        actor=created_by,
        event_type="VERSION_CREATED",
        payload={
            "version": version["version"],
            "content_hash": version["content_hash"],
            "change_summary": change_summary,
        },
        campaign_id=campaign_id,
        session=session,
    )
    return version


def diff_versions(before, after, _path: str = "") -> list[dict]:
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(set(before) | set(after), key=str):
            changes += diff_versions(before.get(key), after.get(key), f"{_path}.{key}" if _path else str(key))
        return changes
    if isinstance(before, list) and isinstance(after, list):
        changes = []
        for i in range(max(len(before), len(after))):
            b = before[i] if i < len(before) else None
            a = after[i] if i < len(after) else None
            changes += diff_versions(b, a, f"{_path}.{i}" if _path else str(i))
        return changes
    return [] if before == after else [{"path": _path, "before": before, "after": after}]
