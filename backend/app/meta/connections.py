from typing import Any
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument

from app import audit
from app.clock import Clock
from app.config import Settings
from app.errors import AppError
from app.meta.errors import MetaAuthExpired
from app.meta.oauth import SCOPES
from app.security.crypto import encrypt_token

EXPIRY_WARNING = timedelta(days=7)

def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

PUBLIC_FIELDS = (
    "ad_account_id",
    "ad_account_name",
    "currency",
    "page_id",
    "page_name",
    "instagram_user_id",
    "instagram_username",
)


class MetaNotConnected(AppError):
    status, code = 409, "META_NOT_CONNECTED"


async def save_token(
    db,
    *,
    user_id,
    token: str,
    expires_at: datetime,
    mode: str,
    settings: Settings,
    clock: Clock,
) -> None:
    now = clock.now()
    await db.meta_connections.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "token_ciphertext": encrypt_token(settings.token_encryption_key, token),
                "token_expires_at": expires_at,
                "scopes": list(SCOPES),
                "status": "ACTIVE",
                "mode": mode,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now, "schema_version": 1},
        },
        upsert=True,
    )
    await audit.record(
        db,
        actor="user",
        event_type="META_CONNECTED",
        payload={"mode": mode, "expires_at": expires_at.isoformat()},
        user_id=user_id,
    )


async def get_connection(db, user_id) -> dict | None:
    return await db.meta_connections.find_one({"user_id": user_id})


async def require_connection(db, user_id, *, clock: Clock) -> dict:
    connection = await get_connection(db, user_id)
    if connection is None:
        raise MetaNotConnected("Connect your Instagram ads account in Settings first")
    expires_at = _ensure_utc(connection["token_expires_at"])
    now = _ensure_utc(clock.now())
    if connection["status"] == "EXPIRED" or expires_at <= now:
        raise MetaAuthExpired("Your Meta connection expired. Reconnect Instagram ads in Settings.")
    return connection


async def require_selected(db, user_id, *, clock: Clock) -> dict:
    connection = await require_connection(db, user_id, clock=clock)
    if not (connection.get("ad_account_id") and connection.get("page_id")):
        raise MetaNotConnected("Pick an ad account and a Page in Settings first")
    return connection


async def require_page(db, user_id, *, clock: Clock) -> dict:
    connection = await require_connection(db, user_id, clock=clock)
    if not connection.get("page_id"):
        raise MetaNotConnected("Select a Facebook Page in Connected Accounts settings first")
    return connection


async def require_instagram(db, user_id, *, clock: Clock) -> dict:
    connection = await require_connection(db, user_id, clock=clock)
    if not connection.get("instagram_user_id"):
        raise MetaNotConnected("Select an Instagram professional account in Connected Accounts settings first")
    return connection


async def select_assets(
    db,
    user_id,
    *,
    ad_account: dict | None = None,
    page: dict | None = None,
    instagram: dict | None = None,
    clock: Clock,
    container: Any = None,
) -> dict:
    updates: dict = {"updated_at": clock.now()}
    if ad_account is not None:
        updates["ad_account_id"] = ad_account["id"]
        updates["ad_account_name"] = ad_account["name"]
        updates["currency"] = ad_account.get("currency", "INR")
        updates["min_daily_budget_minor"] = ad_account.get("min_daily_budget_minor", 9673)
    if page is not None:
        updates["page_id"] = page["id"]
        updates["page_name"] = page["name"]
    if instagram is not None:
        updates["instagram_user_id"] = instagram["id"]
        updates["instagram_username"] = instagram["username"]

    res = await db.meta_connections.find_one_and_update(
        {"user_id": user_id},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if container is not None and res and res.get("page_id"):
        try:
            _, writer = container.gateway_for(res)
            await writer.subscribe_messages(res["page_id"])
        except Exception as exc:
            import structlog
            structlog.get_logger().warning("subscribe_messages_failed_on_select", page_id=res.get("page_id"), error=str(exc))
    return res


async def disconnect_asset(db, user_id, *, asset_type: str, clock: Clock) -> dict:
    """Disconnect or clear a specific asset (ad_account, page, or instagram) without removing the entire Meta OAuth connection."""
    unset_fields: dict = {}
    if asset_type == "ad_account":
        unset_fields = {
            "ad_account_id": "",
            "ad_account_name": "",
            "currency": "",
            "min_daily_budget_minor": "",
        }
    elif asset_type == "page":
        unset_fields = {
            "page_id": "",
            "page_name": "",
        }
    elif asset_type == "instagram":
        unset_fields = {
            "instagram_user_id": "",
            "instagram_username": "",
        }

    res = await db.meta_connections.find_one_and_update(
        {"user_id": user_id},
        {
            "$unset": unset_fields,
            "$set": {"updated_at": clock.now()},
        },
        return_document=ReturnDocument.AFTER,
    )
    if res and not (res.get("ad_account_id") or res.get("page_id") or res.get("instagram_user_id")):
        await db.meta_connections.delete_one({"user_id": user_id})
        return {}
    return res or {}


async def mark_expired(db, user_id, *, clock: Clock) -> None:
    await db.meta_connections.update_one(
        {"user_id": user_id},
        {"$set": {"status": "EXPIRED", "updated_at": clock.now()}},
    )
    await audit.record(db, actor="system", event_type="META_AUTH_EXPIRED", payload={}, user_id=user_id)


def public_view(connection: dict | None, *, now: datetime) -> dict:
    if connection is None:
        return {"status": "NOT_CONNECTED"}
    expires_at = _ensure_utc(connection["token_expires_at"])
    now_utc = _ensure_utc(now)
    return {
        "status": connection["status"],
        "mode": connection["mode"],
        "expires_at": expires_at.isoformat(),
        "expiring_soon": connection["status"] == "ACTIVE" and expires_at - now_utc <= EXPIRY_WARNING,
        **{key: connection.get(key) for key in PUBLIC_FIELDS},
    }
