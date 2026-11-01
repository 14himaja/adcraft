from app import audit
from app.clock import Clock
from app.domain.states import CampaignState
from app.errors import AppError, NotFound
from app.services.transitions import transition

_CODES = {"stale": "STALE_VERSION", "missing": "APPROVAL_REQUIRED", "state": "ILLEGAL_TRANSITION"}


class ApprovalError(AppError):
    status = 409

    def __init__(self, reason: str, message: str):
        super().__init__(message, {"reason": reason})
        self.reason = reason
        self.code = _CODES[reason]


async def approve_version(db, campaign_id, *, user_id, version: int, shown_hash: str, clock: Clock) -> dict:
    async def txn(session) -> dict:
        campaign = await db.campaigns.find_one({"_id": campaign_id}, session=session)
        if campaign is None:
            raise NotFound("Campaign not found")
        if campaign["status"] != CampaignState.IN_REVIEW:
            raise ApprovalError(
                "state", f"Only a campaign in review can be approved (it is {campaign['status']})"
            )
        version_doc = await db.campaign_versions.find_one(
            {"campaign_id": campaign_id, "version": version}, session=session
        )
        if (
            version_doc is None
            or version != campaign["current_version"]
            or version_doc["content_hash"] != shown_hash
        ):
            raise ApprovalError(
                "stale", "The campaign changed since you reviewed it. Review the latest version."
            )
        approval = {
            "campaign_id": campaign_id,
            "version": version,
            "user_id": user_id,
            "action": "PUBLISH",
            "content_hash": shown_hash,
            "approved_budget_minor": (version_doc.get("plan") or {}).get("lifetime_budget_minor"),
            "created_at": clock.now(),
            "revoked_at": None,
        }
        await db.approvals.insert_one(approval, session=session)
        await transition(
            db,
            campaign_id,
            to=CampaignState.APPROVED,
            expected_rev=campaign["rev"],
            actor="user",
            reason=f"approved version {version}",
            session=session,
        )
        await db.campaigns.update_one(
            {"_id": campaign_id},
            {"$set": {"approved_version": version}},
            session=session,
        )
        await audit.record(
            db,
            actor="user",
            event_type="APPROVAL_RECORDED",
            payload={"action": "PUBLISH", "version": version, "content_hash": shown_hash},
            user_id=user_id,
            campaign_id=campaign_id,
            session=session,
        )
        return approval

    try:
        async with db.client.start_session() as session:
            return await session.with_transaction(txn)
    except ApprovalError as exc:
        await audit.record(
            db,
            actor="user",
            event_type="APPROVAL_REJECTED",
            payload={"reason": exc.reason, "version": version},
            user_id=user_id,
            campaign_id=campaign_id,
        )
        raise


async def active_approval(db, campaign_id, action: str, *, session=None) -> dict | None:
    campaign = await db.campaigns.find_one({"_id": campaign_id}, session=session)
    if campaign is None:
        return None
    version_doc = await db.campaign_versions.find_one(
        {"campaign_id": campaign_id, "version": campaign["current_version"]}, session=session
    )
    if version_doc is None:
        return None
    return await db.approvals.find_one(
        {
            "campaign_id": campaign_id,
            "action": action,
            "revoked_at": None,
            "version": version_doc["version"],
            "content_hash": version_doc["content_hash"],
        },
        sort=[("created_at", -1)],
        session=session,
    )
