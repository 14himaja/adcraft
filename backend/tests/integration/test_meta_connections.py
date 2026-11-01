from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.clock import FixedClock
from app.meta.connections import (
    MetaNotConnected,
    mark_expired,
    public_view,
    require_connection,
    require_selected,
    save_token,
    select_assets,
)
from app.meta.errors import MetaAuthExpired
from app.security.crypto import decrypt_token

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)
ACCOUNT = {
    "id": "act_1",
    "name": "Acme",
    "currency": "INR",
    "account_status": 1,
    "min_daily_budget_minor": 9673,
}
PAGE = {"id": "page_1", "name": "Acme Page"}
INSTAGRAM = {"id": "ig_1", "username": "acme"}


@pytest.fixture
def clock():
    return FixedClock(NOW)


async def connect(db, settings, clock, user, days=60):
    await save_token(
        db,
        user_id=user,
        token="EAAB-SECRET",
        expires_at=NOW + timedelta(days=days),
        mode="real",
        settings=settings,
        clock=clock,
    )


async def test_token_is_stored_encrypted_and_audited(db, settings, clock):
    user = ObjectId()
    await connect(db, settings, clock, user)
    doc = await db.meta_connections.find_one({"user_id": user})
    assert b"EAAB-SECRET" not in doc["token_ciphertext"]
    assert decrypt_token(settings.token_encryption_key, doc["token_ciphertext"]) == "EAAB-SECRET"
    assert doc["status"] == "ACTIVE"
    entry = await db.audit_log.find_one({"event_type": "META_CONNECTED"})
    assert "EAAB-SECRET" not in str(entry)


async def test_reconnecting_updates_the_same_document(db, settings, clock):
    user = ObjectId()
    await connect(db, settings, clock, user)
    await connect(db, settings, clock, user)
    assert await db.meta_connections.count_documents({"user_id": user}) == 1


async def test_public_view_never_contains_the_token(db, settings, clock):
    user = ObjectId()
    await connect(db, settings, clock, user)
    view = public_view(await db.meta_connections.find_one({"user_id": user}), now=NOW)
    assert "EAAB-SECRET" not in str(view)
    assert not any("token" in key for key in view)
    assert view["status"] == "ACTIVE" and view["expiring_soon"] is False


async def test_expiring_soon_within_7_days(db, settings, clock):
    user = ObjectId()
    await connect(db, settings, clock, user, days=5)
    assert (
        public_view(await db.meta_connections.find_one({"user_id": user}), now=NOW)["expiring_soon"] is True
    )


def test_public_view_without_connection():
    assert public_view(None, now=NOW) == {"status": "NOT_CONNECTED"}


async def test_require_connection_without_one_raises(db, clock):
    with pytest.raises(MetaNotConnected):
        await require_connection(db, ObjectId(), clock=clock)


async def test_require_connection_after_expiry_raises(db, settings, clock):
    user = ObjectId()
    await connect(db, settings, clock, user, days=1)
    clock.advance(days=2)
    with pytest.raises(MetaAuthExpired):
        await require_connection(db, user, clock=clock)


async def test_mark_expired_is_audited_and_blocks(db, settings, clock):
    user = ObjectId()
    await connect(db, settings, clock, user)
    await mark_expired(db, user, clock=clock)
    with pytest.raises(MetaAuthExpired):
        await require_connection(db, user, clock=clock)
    assert await db.audit_log.find_one({"event_type": "META_AUTH_EXPIRED"})


async def test_selection_is_required_then_saved(db, settings, clock):
    user = ObjectId()
    await connect(db, settings, clock, user)
    with pytest.raises(MetaNotConnected):
        await require_selected(db, user, clock=clock)
    saved = await select_assets(db, user, ad_account=ACCOUNT, page=PAGE, instagram=INSTAGRAM, clock=clock)
    assert (saved["ad_account_id"], saved["page_id"], saved["instagram_user_id"]) == (
        "act_1",
        "page_1",
        "ig_1",
    )
    assert saved["min_daily_budget_minor"] == 9673
    assert (await require_selected(db, user, clock=clock))["instagram_username"] == "acme"
