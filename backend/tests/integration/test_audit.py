import pytest

from app.audit import record
from app.observability import correlation_id_var


async def test_record_inserts_event_with_correlation_id(db):
    token = correlation_id_var.set("cid-123")
    try:
        await record(db, actor="system", event_type="TEST_EVENT", payload={"k": 1})
    finally:
        correlation_id_var.reset(token)
    doc = await db.audit_log.find_one({"event_type": "TEST_EVENT"})
    assert doc["actor"] == "system"
    assert doc["payload"] == {"k": 1}
    assert doc["correlation_id"] == "cid-123"
    assert doc["ts"].tzinfo is not None


async def test_record_rejects_unknown_actor(db):
    with pytest.raises(ValueError):
        await record(db, actor="model", event_type="X", payload={})
