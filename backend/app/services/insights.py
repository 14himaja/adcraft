"""Insights collection for published campaigns (spec 07 §10)."""

from datetime import date, datetime
from decimal import Decimal

import structlog

from app.clock import Clock
from app.domain.ad_campaign import to_minor
from app.domain.ad_states import AdState
from app.errors import AppError
from app.meta.connections import require_selected

log = structlog.get_logger()


class RateLimited(AppError):
    status, code = 429, "RATE_LIMITED"


def _parse_iso(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None


async def collect(db, campaign: dict, *, container) -> dict:
    """Read insights and ad status from Meta, store on campaign document,
    and mark COMPLETED if past end_date."""
    clock: Clock = container.clock
    today = clock.now().date()

    meta = campaign.get("meta") or {}
    meta_campaign_id = meta.get("campaign_id")
    if not meta_campaign_id:
        return campaign.get("insights") or {}

    connection = await require_selected(db, campaign["user_id"], clock=clock)
    reader = container.gateway_for(connection)[0]

    # Ask for the whole life of the ad, as Ads Manager does: its start or end can be changed there, so
    # delivery may fall outside the dates stored here (that dropped a day of impressions before).
    created = campaign.get("created_at")
    since = min(
        date.fromisoformat(campaign["start_date"]) if campaign.get("start_date") else today,
        created.date() if created else today,
    )
    end_date = date.fromisoformat(campaign["end_date"]) if campaign.get("end_date") else today

    rows = await reader.insights(meta_campaign_id, since, max(end_date, today))

    impressions = sum(int(r.get("impressions", 0)) for r in rows)
    reach = sum(int(r.get("reach", 0)) for r in rows)
    clicks = sum(int(r.get("clicks", 0)) for r in rows)
    spend_minor = sum(to_minor(Decimal(str(r.get("spend", 0)))) for r in rows)
    ctr = (
        round((clicks / impressions * 100), 2)
        if impressions > 0
        else (float(rows[0]["ctr"]) if rows and "ctr" in rows[0] else 0.0)
    )
    cpc_minor = int(spend_minor / clicks) if clicks > 0 else None

    effective_status, issues = None, None
    if ad_id := meta.get("ad_id"):
        try:
            status_data = await reader.ad_status(ad_id)
            effective_status = status_data.get("effective_status")
            issues = status_data.get("issues") or []
        except Exception:
            pass

    insights_block = {
        "impressions": impressions,
        "reach": reach,
        "clicks": clicks,
        "spend_minor": spend_minor,
        "ctr": ctr,
        "cpc_minor": cpc_minor,
        "updated_at": clock.now().isoformat(),
    }

    set_fields = {
        "insights": insights_block,
        "updated_at": clock.now(),
    }
    if effective_status:
        set_fields["meta.effective_status"] = effective_status
    if issues is not None:
        set_fields["meta.issues"] = issues

    if (
        campaign.get("status") in (AdState.ACTIVE.value, AdState.PAUSED.value)
        and campaign.get("end_date")
        and today > date.fromisoformat(campaign["end_date"])
    ):
        set_fields["status"] = AdState.COMPLETED.value

    await db.campaigns.update_one({"_id": campaign["_id"]}, {"$set": set_fields})
    return insights_block


def check_refresh_rate_limit(campaign: dict, clock: Clock) -> None:
    updated_at_str = (campaign.get("insights") or {}).get("updated_at")
    dt = _parse_iso(updated_at_str)
    if dt is not None:
        elapsed = (clock.now() - dt).total_seconds()
        if elapsed < 300:
            raise RateLimited("Insights were refreshed recently; please wait 5 minutes between refreshes")


async def refresh_all_active(db, container) -> int:
    """Background job for app lifespan: refresh insights for ACTIVE/PAUSED campaigns."""
    cursor = db.campaigns.find(
        {
            "status": {"$in": [AdState.ACTIVE.value, AdState.PAUSED.value]},
            "meta.campaign_id": {"$exists": True, "$ne": None},
        }
    )
    count = 0
    async for c in cursor:
        try:
            await collect(db, c, container=container)
            count += 1
        except Exception as exc:
            log.warning("insights_refresh_failed", campaign_id=str(c.get("_id")), error=str(exc))
    return count
