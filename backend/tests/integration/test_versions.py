from datetime import UTC, datetime

from app.clock import FixedClock
from app.services.versions import content_hash, create_version, snapshot
from tests.factories import insert_campaign

CLOCK = FixedClock(datetime(2026, 10, 6, 9, 0, tzinfo=UTC))


async def make_version(db, cid, headline="Old"):
    return await create_version(
        db,
        cid,
        requirements={"fields": {}},
        plan={"lifetime_budget_minor": 5_000_000},
        assets={"variants": [{"headline": headline}]},
        created_by="agent",
        change_summary="test",
        clock=CLOCK,
    )


async def test_versions_are_numbered_sequentially(db):
    cid = await insert_campaign(db)
    assert (await make_version(db, cid))["version"] == 1
    assert (await make_version(db, cid, headline="New"))["version"] == 2
    assert (await db.campaigns.find_one({"_id": cid}))["current_version"] == 2


async def test_version_stores_hash_of_its_snapshot(db):
    cid = await insert_campaign(db)
    version = await make_version(db, cid)
    assert version["content_hash"] == content_hash(snapshot(version))


async def test_new_version_revokes_active_approvals(db):
    cid = await insert_campaign(db)
    await make_version(db, cid)
    await db.approvals.insert_one({"campaign_id": cid, "action": "PUBLISH", "revoked_at": None})
    await make_version(db, cid, headline="Changed")
    assert await db.approvals.count_documents({"campaign_id": cid, "revoked_at": None}) == 0
    assert await db.audit_log.find_one({"event_type": "APPROVAL_REVOKED"})


async def test_version_creation_is_audited(db):
    cid = await insert_campaign(db)
    await make_version(db, cid)
    entry = await db.audit_log.find_one({"event_type": "VERSION_CREATED"})
    assert entry["payload"]["version"] == 1
