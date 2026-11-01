from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.clock import FixedClock
from app.services.approvals import ApprovalError, active_approval, approve_version
from app.services.versions import create_version
from tests.factories import insert_campaign

CLOCK = FixedClock(datetime(2026, 10, 6, 9, 0, tzinfo=UTC))
USER = ObjectId()


async def campaign_in_review(db, headline="Ship faster"):
    cid = await insert_campaign(db, status="IN_REVIEW", rev=3, user_id=USER)
    version = await create_version(
        db,
        cid,
        requirements={"fields": {}},
        plan={"lifetime_budget_minor": 5_000_000},
        assets={"variants": [{"headline": headline}]},
        created_by="agent",
        change_summary="v",
        clock=CLOCK,
    )
    return cid, version


async def test_matching_hash_records_approval_and_approves(db):
    cid, v = await campaign_in_review(db)
    approval = await approve_version(
        db,
        cid,
        user_id=USER,
        version=v["version"],
        shown_hash=v["content_hash"],
        clock=CLOCK,
    )
    campaign = await db.campaigns.find_one({"_id": cid})
    assert campaign["status"] == "APPROVED" and campaign["approved_version"] == v["version"]
    assert approval["approved_budget_minor"] == 5_000_000
    assert await db.audit_log.find_one({"event_type": "APPROVAL_RECORDED"})


async def test_stale_hash_is_rejected_and_nothing_is_written(db):
    cid, v = await campaign_in_review(db)
    with pytest.raises(ApprovalError) as exc:
        await approve_version(db, cid, user_id=USER, version=v["version"], shown_hash="0" * 64, clock=CLOCK)
    assert exc.value.reason == "stale" and exc.value.code == "STALE_VERSION"
    assert await db.approvals.count_documents({}) == 0
    assert (await db.campaigns.find_one({"_id": cid}))["status"] == "IN_REVIEW"
    assert await db.audit_log.find_one({"event_type": "APPROVAL_REJECTED"})


async def test_approving_an_older_version_is_stale(db):
    cid, v1 = await campaign_in_review(db)
    await create_version(
        db,
        cid,
        requirements={"fields": {}},
        plan={"lifetime_budget_minor": 5_000_000},
        assets={"variants": [{"headline": "Changed"}]},
        created_by="user",
        change_summary="edit",
        clock=CLOCK,
    )
    with pytest.raises(ApprovalError, match="changed"):
        await approve_version(db, cid, user_id=USER, version=1, shown_hash=v1["content_hash"], clock=CLOCK)


async def test_wrong_state_is_rejected(db):
    cid = await insert_campaign(db, status="COLLECTING", user_id=USER)
    with pytest.raises(ApprovalError) as exc:
        await approve_version(db, cid, user_id=USER, version=1, shown_hash="x", clock=CLOCK)
    assert exc.value.reason == "state"


async def test_second_approval_of_same_version_is_rejected(db):
    cid, v = await campaign_in_review(db)
    await approve_version(
        db, cid, user_id=USER, version=v["version"], shown_hash=v["content_hash"], clock=CLOCK
    )
    with pytest.raises(ApprovalError):
        await approve_version(
            db, cid, user_id=USER, version=v["version"], shown_hash=v["content_hash"], clock=CLOCK
        )
    assert await db.approvals.count_documents({}) == 1


async def test_active_approval_found_then_cleared_by_new_version(db):
    cid, v = await campaign_in_review(db)
    await approve_version(
        db, cid, user_id=USER, version=v["version"], shown_hash=v["content_hash"], clock=CLOCK
    )
    assert await active_approval(db, cid, "PUBLISH")
    await create_version(
        db,
        cid,
        requirements={"fields": {}},
        plan=None,
        assets=None,
        created_by="user",
        change_summary="edit",
        clock=CLOCK,
    )
    assert await active_approval(db, cid, "PUBLISH") is None
