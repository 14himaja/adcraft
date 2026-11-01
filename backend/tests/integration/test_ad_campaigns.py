import pytest
from bson import ObjectId

from app.services.ad_campaigns import create_draft, update_draft
from app.services.transitions import ConcurrentModification


async def test_update_with_a_stale_revision_is_refused(db, settings, clock):
    campaign = await create_draft(
        db, user_id=ObjectId(), fields={"title": "A"}, settings=settings, clock=clock
    )
    await update_draft(db, campaign, {"title": "B"}, settings=settings, clock=clock)
    with pytest.raises(ConcurrentModification):
        await update_draft(db, campaign, {"title": "C"}, settings=settings, clock=clock)  # still rev 0


async def test_create_and_update_are_audited(db, settings, clock):
    campaign = await create_draft(
        db, user_id=ObjectId(), fields={"title": "A"}, settings=settings, clock=clock
    )
    await update_draft(db, campaign, {"title": "B"}, settings=settings, clock=clock)
    events = [e["event_type"] async for e in db.audit_log.find({"campaign_id": campaign["_id"]})]
    assert events == ["CAMPAIGN_CREATED", "CAMPAIGN_UPDATED"]
