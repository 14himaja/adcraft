from pymongo import ReturnDocument

from app import audit
from app.clock import utcnow
from app.domain.states import CampaignState, can_transition
from app.errors import AppError, NotFound


class IllegalTransition(AppError):
    status, code = 409, "ILLEGAL_TRANSITION"


class ConcurrentModification(AppError):
    status, code = 409, "CONCURRENT_MODIFICATION"


async def transition(
    db,
    campaign_id,
    *,
    to: CampaignState,
    expected_rev: int,
    actor: str,
    reason: str,
    session=None,
) -> dict:
    campaign = await db.campaigns.find_one({"_id": campaign_id}, session=session)
    if campaign is None:
        raise NotFound("Campaign not found")
    current = CampaignState(campaign["status"])
    if not can_transition(current, to):
        await audit.record(
            db,
            actor=actor,
            event_type="TRANSITION_BLOCKED",
            payload={"from": current, "to": to, "reason": reason},
            campaign_id=campaign_id,
            session=session,
        )
        raise IllegalTransition(f"A campaign cannot move from {current} to {to}", {"from": current, "to": to})
    updated = await db.campaigns.find_one_and_update(
        {"_id": campaign_id, "status": current, "rev": expected_rev},
        {"$set": {"status": to, "updated_at": utcnow()}, "$inc": {"rev": 1}},
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    if updated is None:
        raise ConcurrentModification("The campaign was changed by another request; reload and try again")
    await audit.record(
        db,
        actor=actor,
        event_type="STATE_TRANSITION",
        payload={"from": current, "to": to, "reason": reason, "rev": updated["rev"]},
        campaign_id=campaign_id,
        session=session,
    )
    return updated
