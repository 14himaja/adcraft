import pytest
from pymongo.errors import DuplicateKeyError

from app.db import ensure_indexes


async def test_user_email_is_unique(db):
    await db.users.insert_one({"email": "a@example.com"})
    with pytest.raises(DuplicateKeyError):
        await db.users.insert_one({"email": "a@example.com"})


async def test_insights_unique_per_object_level_day(db):
    row = {"meta_object_id": "1", "level": "ad", "day": "2026-10-01"}
    await db.insights_daily.insert_one(dict(row))
    with pytest.raises(DuplicateKeyError):
        await db.insights_daily.insert_one(dict(row))


async def test_versions_unique_per_campaign(db):
    await db.campaign_versions.insert_one({"campaign_id": 1, "version": 1})
    with pytest.raises(DuplicateKeyError):
        await db.campaign_versions.insert_one({"campaign_id": 1, "version": 1})


async def test_publish_runs_unique_per_campaign_version(db):
    await db.publish_runs.insert_one({"campaign_id": 1, "version": 1})
    with pytest.raises(DuplicateKeyError):
        await db.publish_runs.insert_one({"campaign_id": 1, "version": 1})


async def test_ensure_indexes_is_idempotent(db):
    await ensure_indexes(db)  # second run must not raise


async def test_replica_set_supports_transactions(db):
    async def txn(session):
        await db.users.insert_one({"email": "t@example.com"}, session=session)

    async with db.client.start_session() as session:
        await session.with_transaction(txn)
    assert await db.users.count_documents({"email": "t@example.com"}) == 1
