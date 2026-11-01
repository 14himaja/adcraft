import asyncio

import pytest
from bson import ObjectId

from app.domain.states import CampaignState as S
from app.errors import NotFound
from app.services.transitions import ConcurrentModification, IllegalTransition, transition
from tests.factories import insert_campaign


async def test_allowed_transition_updates_status_and_rev(db):
    cid = await insert_campaign(db)
    updated = await transition(db, cid, to=S.PLANNING, expected_rev=0, actor="system", reason="ready")
    assert (updated["status"], updated["rev"]) == ("PLANNING", 1)


async def test_transition_is_audited(db):
    cid = await insert_campaign(db)
    await transition(db, cid, to=S.PLANNING, expected_rev=0, actor="system", reason="ready")
    entry = await db.audit_log.find_one({"event_type": "STATE_TRANSITION"})
    assert entry["payload"]["from"] == "COLLECTING" and entry["payload"]["to"] == "PLANNING"
    assert entry["campaign_id"] == cid


async def test_illegal_transition_is_refused_and_audited(db):
    cid = await insert_campaign(db, status="IN_REVIEW", rev=3)
    with pytest.raises(IllegalTransition):
        await transition(db, cid, to=S.PUBLISHING, expected_rev=3, actor="agent", reason="skip approval")
    assert (await db.campaigns.find_one({"_id": cid}))["status"] == "IN_REVIEW"
    assert await db.audit_log.find_one({"event_type": "TRANSITION_BLOCKED"})


async def test_stale_rev_is_a_concurrent_modification(db):
    cid = await insert_campaign(db, rev=4)
    with pytest.raises(ConcurrentModification):
        await transition(db, cid, to=S.PLANNING, expected_rev=3, actor="user", reason="stale tab")


async def test_only_one_of_two_simultaneous_transitions_wins(db):
    cid = await insert_campaign(db)
    results = await asyncio.gather(
        transition(db, cid, to=S.PLANNING, expected_rev=0, actor="user", reason="a"),
        transition(db, cid, to=S.PLANNING, expected_rev=0, actor="user", reason="b"),
        return_exceptions=True,
    )
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, ConcurrentModification) for r in results) == 1
    assert (await db.campaigns.find_one({"_id": cid}))["rev"] == 1


async def test_unknown_campaign_is_not_found(db):
    with pytest.raises(NotFound):
        await transition(db, ObjectId(), to=S.PLANNING, expected_rev=0, actor="user", reason="x")
