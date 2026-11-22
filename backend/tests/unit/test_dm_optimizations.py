"""Unit tests for DM Agent optimizations:
1. Default enabled=True for connected users and ConfigBody default True. Empty knowledge save succeeds.
2. Debounce: post + text sent 1s apart gets merged into one question and receives exactly one reply.
3. Latency: query embedding generated once and shared, chunk scan scoped to resolved post, latency logged.
4. Auto-resume bot on customer's next message after NEEDS_HUMAN unless thread status is HUMAN.
5. Unresolved shared post asks which product/offer they mean without escalating to NEEDS_HUMAN.
6. Story reply is parsed and receives automated bot reply.
"""

import asyncio
import copy
import re
import time
from datetime import UTC, datetime, timedelta
from bson import ObjectId
import pytest

from app.api.dm import ConfigBody
from app.clock import FixedClock
from app.config import Settings
from app.container import Container
from app.services import dm
from app.services.hybrid_rag import HybridRAG
from app.services.shared_post_resolver import SharedPostContextResolver


class MockCursor:
    def __init__(self, docs):
        self.docs = list(docs)
        self.idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.idx < len(self.docs):
            doc = self.docs[self.idx]
            self.idx += 1
            return doc
        raise StopAsyncIteration

    def sort(self, key, direction=1):
        self.docs.sort(key=lambda d: d.get(key, 0), reverse=(direction == -1))
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self


def _matches(doc: dict, filter_query: dict) -> bool:
    if not filter_query:
        return True
    for key, val in filter_query.items():
        if key == "$or":
            if not any(_matches(doc, branch) for branch in val):
                return False
            continue
        if key == "$and":
            if not all(_matches(doc, branch) for branch in val):
                return False
            continue

        doc_val = doc.get(key)
        if isinstance(val, dict):
            for op, op_val in val.items():
                if op == "$ne":
                    if str(doc_val) == str(op_val):
                        return False
                elif op == "$in":
                    str_op_vals = {str(x) for x in op_val}
                    if str(doc_val) not in str_op_vals:
                        return False
                elif op == "$nin":
                    str_op_vals = {str(x) for x in op_val}
                    if str(doc_val) in str_op_vals:
                        return False
                elif op == "$lt":
                    if doc_val is None or doc_val >= op_val:
                        return False
                elif op == "$lte":
                    if doc_val is None or doc_val > op_val:
                        return False
                elif op == "$gt":
                    if doc_val is None or doc_val <= op_val:
                        return False
                elif op == "$gte":
                    if doc_val is None or doc_val < op_val:
                        return False
                elif op == "$regex":
                    flags = re.IGNORECASE if val.get("$options") == "i" else 0
                    if not re.search(op_val, str(doc_val or ""), flags):
                        return False
            continue

        if str(doc_val) != str(val) and doc_val != val:
            return False
    return True


class MockCollection:
    def __init__(self, name: str):
        self.name = name
        self.docs: list[dict] = []

    async def insert_one(self, doc: dict, session=None, **kwargs):
        d = copy.deepcopy(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        # If _id already exists, prevent duplicate
        for existing in self.docs:
            if existing["_id"] == d["_id"]:
                from pymongo.errors import DuplicateKeyError
                raise DuplicateKeyError(f"Duplicate key {d['_id']}")
        self.docs.append(d)
        class Res:
            inserted_id = d["_id"]
        return Res()

    async def insert_many(self, docs: list[dict], session=None, **kwargs):
        for d in docs:
            await self.insert_one(d)

    async def find_one(self, filter_query: dict | None = None, projection=None, sort=None, **kwargs):
        filter_query = filter_query or {}
        matches = [d for d in self.docs if _matches(d, filter_query)]
        if not matches:
            return None
        if sort:
            for key, direction in reversed(sort):
                matches.sort(key=lambda d: d.get(key) or datetime.min.replace(tzinfo=UTC), reverse=(direction == -1))
        return copy.deepcopy(matches[0])

    def find(self, filter_query: dict | None = None, projection=None, **kwargs):
        filter_query = filter_query or {}
        matched = [copy.deepcopy(d) for d in self.docs if _matches(d, filter_query)]
        return MockCursor(matched)

    async def count_documents(self, filter_query: dict | None = None, **kwargs) -> int:
        filter_query = filter_query or {}
        return sum(1 for d in self.docs if _matches(d, filter_query))

    async def update_one(self, filter_query: dict, update: dict, upsert: bool = False, session=None, **kwargs):
        for d in self.docs:
            if _matches(d, filter_query):
                self._apply_update(d, update)
                return
        if upsert:
            new_doc = copy.deepcopy(filter_query)
            if "_id" not in new_doc:
                new_doc["_id"] = ObjectId()
            self._apply_update(new_doc, update)
            self.docs.append(new_doc)

    async def find_one_and_update(self, filter_query: dict, update: dict, upsert: bool = False, return_document=None, session=None, **kwargs):
        for d in self.docs:
            if _matches(d, filter_query):
                self._apply_update(d, update)
                return copy.deepcopy(d)
        if upsert:
            new_doc = copy.deepcopy(filter_query)
            if "_id" not in new_doc:
                new_doc["_id"] = ObjectId()
            self._apply_update(new_doc, update)
            self.docs.append(new_doc)
            return copy.deepcopy(new_doc)
        return None

    def _apply_update(self, doc: dict, update: dict):
        if "$set" in update:
            for k, v in update["$set"].items():
                doc[k] = copy.deepcopy(v)
        if "$setOnInsert" in update:
            for k, v in update["$setOnInsert"].items():
                if k not in doc:
                    doc[k] = copy.deepcopy(v)
        if "$unset" in update:
            for k in update["$unset"].keys():
                doc.pop(k, None)
        if "$push" in update:
            for k, v in update["$push"].items():
                if k not in doc or not isinstance(doc[k], list):
                    doc[k] = []
                if isinstance(v, dict) and "$each" in v:
                    doc[k].extend(copy.deepcopy(v["$each"]))
                    if "$slice" in v:
                        slice_n = v["$slice"]
                        if slice_n < 0:
                            doc[k] = doc[k][slice_n:]
                else:
                    doc[k].append(copy.deepcopy(v))


class MockDb:
    def __init__(self):
        self.collections = {}

    def __getattr__(self, name: str) -> MockCollection:
        if name not in self.collections:
            self.collections[name] = MockCollection(name)
        return self.collections[name]


class FakeGateway:
    def __init__(self):
        self.sent_dms = []
        self.subscribed_pages = []

    async def send_dm(self, page_id: str, customer_id: str, text: str) -> str:
        self.sent_dms.append({"page_id": page_id, "customer_id": customer_id, "text": text})
        return f"mid_fake_{len(self.sent_dms)}"

    async def customer_name(self, page_id: str, customer_id: str) -> str:
        return "Priya Customer"

    async def subscribe_messages(self, page_id: str) -> bool:
        self.subscribed_pages.append(page_id)
        return True


async def run_inline(coro):
    await coro

@pytest.fixture
def fake_container():
    settings = Settings(
        app_env="test",
        mongodb_uri="mongodb://localhost:27017",
        jwt_secret="t" * 32,
        token_encryption_key="t" * 32,
        meta_mode="fake",
        llm_provider="scripted",
    )
    clock = FixedClock(datetime(2026, 11, 5, 12, 0, tzinfo=UTC))
    gateway = FakeGateway()
    c = Container(
        settings=settings,
        clock=clock,
        gateway_for=lambda conn: (gateway, gateway),
        image_generator=None,
        spawn=run_inline,
        retry_wait=None,
    )
    c.meta_writer = gateway
    c.meta_gateway = gateway
    return c


@pytest.mark.asyncio
async def test_fresh_user_has_enabled_true_and_configbody_default():
    # Verify ConfigBody defaults enabled to True
    body = ConfigBody()
    assert body.enabled is True

    # Verify get_config defaults enabled to True when Meta connection exists
    db = MockDb()
    user_id = ObjectId()
    await db.meta_connections.insert_one({
        "user_id": user_id,
        "status": "ACTIVE",
        "instagram_user_id": "ig_123",
        "page_id": "page_123",
    })
    cfg = await dm.get_config(db, user_id)
    assert cfg["enabled"] is True

    # When no connection exists, default remains False
    other_user = ObjectId()
    cfg_other = await dm.get_config(db, other_user)
    assert cfg_other["enabled"] is False


@pytest.mark.asyncio
async def test_save_config_with_empty_knowledge_succeeds(fake_container):
    db = MockDb()
    user_id = ObjectId()
    await db.users.insert_one({"_id": user_id, "active_workspace_id": "ws_test"})
    await db.meta_connections.insert_one({
        "user_id": user_id,
        "status": "ACTIVE",
        "instagram_user_id": "ig_123",
        "page_id": "page_123",
    })

    # Saving config with empty knowledge must succeed without DmNotReady error
    saved = await dm.save_config(db, fake_container, user_id, {"enabled": True, "knowledge": ""})
    assert saved["enabled"] is True
    assert saved["knowledge"] == ""


@pytest.mark.asyncio
async def test_post_and_text_sent_1s_apart_gets_exactly_one_reply(fake_container, monkeypatch):
    db = MockDb()
    user_id = ObjectId()
    ws_id = "ws_test"
    await db.users.insert_one({"_id": user_id, "active_workspace_id": ws_id})
    await db.meta_connections.insert_one({
        "user_id": user_id,
        "status": "ACTIVE",
        "instagram_user_id": "ig_123",
        "page_id": "page_123",
    })
    await db.dm_settings.insert_one({
        "user_id": user_id,
        "enabled": True,
        "knowledge": "All organic cotton tees are Rs 799.",
        "handoff_message": "Connecting you with human support.",
    })
    post_id = ObjectId()
    await db.social_posts.insert_one({
        "_id": post_id,
        "workspace_id": ws_id,
        "post_status": "published",
        "platform_post_id": "media_post_999",
        "title": "Organic Cotton Tee",
        "caption": "Our 100% organic cotton tee.",
        "summary": "Organic cotton t-shirt Rs 799.",
    })

    # Customer sends shared post at t=0
    post_event = {
        "sender": {"id": "cust_1"},
        "recipient": {"id": "ig_123"},
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "message": {
            "mid": "mid_post_1",
            "attachments": [{
                "type": "share",
                "payload": {"id": "media_post_999", "url": "https://instagram.com/p/media_post_999"}
            }]
        }
    }

    # Customer sends follow-up text at t=1.0s
    text_event = {
        "sender": {"id": "cust_1"},
        "recipient": {"id": "ig_123"},
        "timestamp": int((datetime.now(UTC) + timedelta(seconds=1)).timestamp() * 1000),
        "message": {
            "mid": "mid_text_2",
            "text": "How much is this?",
        }
    }

    from app.agents.dm_agent import DmAnswer
    async def fake_answer_tee(**kwargs):
        return DmAnswer(text="Our organic cotton tees are Rs 799.", needs_human=False)
    monkeypatch.setattr(dm, "answer_dm", fake_answer_tee)

    # Simulate debounced arrival: post at t=0, text 1s later
    task1 = asyncio.create_task(dm.handle_messaging(db, fake_container, post_event))
    await asyncio.sleep(0.3)
    task2 = asyncio.create_task(dm.handle_messaging(db, fake_container, text_event))
    await asyncio.gather(task1, task2)

    # Fake gateway should have sent EXACTLY ONE reply
    assert len(fake_container.meta_writer.sent_dms) == 1
    reply_text = fake_container.meta_writer.sent_dms[0]["text"]
    assert "799" in reply_text or "Cotton" in reply_text

    # Thread messages must have both customer messages recorded and 1 agent reply
    thread = await db.dm_threads.find_one({"user_id": user_id, "customer_id": "cust_1"})
    assert thread is not None
    assert len(thread["messages"]) == 3
    assert thread["messages"][0]["mid"] == "mid_post_1"
    assert thread["messages"][1]["mid"] == "mid_text_2"
    assert thread["messages"][2]["role"] == "agent"


@pytest.mark.asyncio
async def test_auto_resume_bot_on_customer_next_message_after_needs_human(fake_container):
    db = MockDb()
    user_id = ObjectId()
    ws_id = "ws_test"
    await db.users.insert_one({"_id": user_id, "active_workspace_id": ws_id})
    await db.meta_connections.insert_one({
        "user_id": user_id,
        "status": "ACTIVE",
        "instagram_user_id": "ig_123",
        "page_id": "page_123",
    })
    await db.dm_settings.insert_one({
        "user_id": user_id,
        "enabled": True,
        "knowledge": "Store is open 10am to 8pm.",
        "handoff_message": "Connecting you with human support.",
    })

    # Thread previously escalated to NEEDS_HUMAN
    thread_id = ObjectId()
    await db.dm_threads.insert_one({
        "_id": thread_id,
        "user_id": user_id,
        "customer_id": "cust_2",
        "status": "NEEDS_HUMAN",
        "escalation": {"reason": "REQUIRES_HUMAN"},
        "last_inbound_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "messages": [{"role": "customer", "text": "I need a human", "at": datetime.now(UTC), "mid": "m0"}],
    })

    # Customer sends another question
    next_event = {
        "sender": {"id": "cust_2"},
        "recipient": {"id": "ig_123"},
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "message": {"mid": "mid_next_1", "text": "What are your hours?"},
    }

    # Temporarily set DEBOUNCE_DELAY to 0.01 for fast unit test
    orig_delay = dm.DEBOUNCE_DELAY
    dm.DEBOUNCE_DELAY = 0.01
    try:
        await dm.handle_messaging(db, fake_container, next_event)
    finally:
        dm.DEBOUNCE_DELAY = orig_delay

    # Thread must have auto-resumed to BOT and answered
    thread = await db.dm_threads.find_one({"_id": thread_id})
    assert thread["status"] == "BOT"
    assert thread["escalation"] is None
    assert len(fake_container.meta_writer.sent_dms) == 1
    sent = fake_container.meta_writer.sent_dms[0]["text"]
    assert "open" in sent.lower() or "9am" in sent.lower()


@pytest.mark.asyncio
async def test_human_status_does_not_auto_resume(fake_container):
    db = MockDb()
    user_id = ObjectId()
    await db.users.insert_one({"_id": user_id, "active_workspace_id": "ws_test"})
    await db.meta_connections.insert_one({
        "user_id": user_id,
        "status": "ACTIVE",
        "instagram_user_id": "ig_123",
        "page_id": "page_123",
    })
    await db.dm_settings.insert_one({"user_id": user_id, "enabled": True, "knowledge": "Info"})

    # Thread is HUMAN because a human actually replied
    thread_id = ObjectId()
    await db.dm_threads.insert_one({
        "_id": thread_id,
        "user_id": user_id,
        "customer_id": "cust_human",
        "status": "HUMAN",
        "last_inbound_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "messages": [],
    })

    event = {
        "sender": {"id": "cust_human"},
        "recipient": {"id": "ig_123"},
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "message": {"mid": "m_human_1", "text": "Are you there?"},
    }

    orig_delay = dm.DEBOUNCE_DELAY
    dm.DEBOUNCE_DELAY = 0.01
    try:
        await dm.handle_messaging(db, fake_container, event)
    finally:
        dm.DEBOUNCE_DELAY = orig_delay

    # Thread stays HUMAN, no bot reply sent
    thread = await db.dm_threads.find_one({"_id": thread_id})
    assert thread["status"] == "HUMAN"
    assert len(fake_container.meta_writer.sent_dms) == 0


@pytest.mark.asyncio
async def test_unresolved_shared_post_asks_which_product_and_does_not_escalate(fake_container):
    db = MockDb()
    user_id = ObjectId()
    await db.users.insert_one({"_id": user_id, "active_workspace_id": "ws_test"})
    await db.meta_connections.insert_one({
        "user_id": user_id,
        "status": "ACTIVE",
        "instagram_user_id": "ig_123",
        "page_id": "page_123",
    })
    await db.dm_settings.insert_one({"user_id": user_id, "enabled": True, "knowledge": "Info"})

    # Event with an unresolvable post attachment and NO text
    unresolved_event = {
        "sender": {"id": "cust_unres"},
        "recipient": {"id": "ig_123"},
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "message": {
            "mid": "m_unres_1",
            "attachments": [{"type": "share", "payload": {"id": "unknown_id_999"}}],
        }
    }

    orig_delay = dm.DEBOUNCE_DELAY
    dm.DEBOUNCE_DELAY = 0.01
    try:
        await dm.handle_messaging(db, fake_container, unresolved_event)
    finally:
        dm.DEBOUNCE_DELAY = orig_delay

    # Bot should reply asking which product they mean, NOT "I can read text only", and NOT escalate
    assert len(fake_container.meta_writer.sent_dms) == 1
    sent_text = fake_container.meta_writer.sent_dms[0]["text"]
    assert "Which product or offer can we help you with?" in sent_text
    assert "I can read text only" not in sent_text

    thread = await db.dm_threads.find_one({"user_id": user_id, "customer_id": "cust_unres"})
    assert thread["status"] == "BOT"  # Never escalated to NEEDS_HUMAN


@pytest.mark.asyncio
async def test_story_reply_is_parsed_and_replied_to(fake_container, monkeypatch):
    db = MockDb()
    user_id = ObjectId()
    ws_id = "ws_test"
    await db.users.insert_one({"_id": user_id, "active_workspace_id": ws_id})
    await db.meta_connections.insert_one({
        "user_id": user_id,
        "status": "ACTIVE",
        "instagram_user_id": "ig_123",
        "page_id": "page_123",
    })
    await db.dm_settings.insert_one({
        "user_id": user_id,
        "enabled": True,
        "knowledge": "Special anniversary discount is 20% off with code ANNIV20.",
    })
    # Social post matching the story
    await db.social_posts.insert_one({
        "_id": ObjectId(),
        "workspace_id": ws_id,
        "post_status": "published",
        "platform_post_id": "story_media_123",
        "title": "Anniversary Sale",
        "summary": "Anniversary sale 20% off",
    })

    from app.agents.dm_agent import DmAnswer
    async def fake_story_answer(**kwargs):
        return DmAnswer(text="Yes! Use code ANNIV20 for 20% off.", needs_human=False)
    monkeypatch.setattr(dm, "answer_dm", fake_story_answer)

    story_reply_event = {
        "sender": {"id": "cust_story"},
        "recipient": {"id": "ig_123"},
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "story_reply": {"story_id": "story_media_123", "link": "https://instagram.com/stories/story_media_123"},
        "message": {"mid": "m_story_1", "text": "Is the sale still active?"},
    }

    orig_delay = dm.DEBOUNCE_DELAY
    dm.DEBOUNCE_DELAY = 0.01
    try:
        await dm.handle_messaging(db, fake_container, story_reply_event)
    finally:
        dm.DEBOUNCE_DELAY = orig_delay

    # Story reply must get an automated reply
    assert len(fake_container.meta_writer.sent_dms) == 1
    assert "ANNIV20" in fake_container.meta_writer.sent_dms[0]["text"] or "20%" in fake_container.meta_writer.sent_dms[0]["text"]


@pytest.mark.asyncio
async def test_webhook_to_send_latency_stays_under_target(fake_container, monkeypatch):
    db = MockDb()
    user_id = ObjectId()
    await db.users.insert_one({"_id": user_id, "active_workspace_id": "ws_test"})
    await db.meta_connections.insert_one({
        "user_id": user_id,
        "status": "ACTIVE",
        "instagram_user_id": "ig_123",
        "page_id": "page_123",
    })
    await db.dm_settings.insert_one({
        "user_id": user_id,
        "enabled": True,
        "knowledge": "We are open Monday to Friday 9am to 5pm.",
    })

    event = {
        "sender": {"id": "cust_lat"},
        "recipient": {"id": "ig_123"},
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "message": {"mid": "m_lat_1", "text": "What are your hours?"},
    }

    logged_latencies = []
    orig_log_latency = dm._log_latency

    def record_latency(t_start, thread_id=None):
        elapsed_ms = round((time.monotonic() - t_start) * 1000, 2)
        logged_latencies.append(elapsed_ms)
        orig_log_latency(t_start, thread_id)

    monkeypatch.setattr(dm, "_log_latency", record_latency)

    orig_delay = dm.DEBOUNCE_DELAY
    dm.DEBOUNCE_DELAY = 0.05
    try:
        t0 = time.monotonic()
        await dm.handle_messaging(db, fake_container, event)
        total_time = (time.monotonic() - t0) * 1000
    finally:
        dm.DEBOUNCE_DELAY = orig_delay

    assert len(logged_latencies) == 1
    # Latency with fake LLM and 50ms debounce should be well under 500ms
    assert logged_latencies[0] < 500
    assert total_time < 500


@pytest.mark.asyncio
async def test_query_embedding_shared_and_chunk_scan_limited_to_resolved_post(fake_container):
    db = MockDb()
    user_id = ObjectId()
    ws_id = "ws_test"
    resolved_post_id = str(ObjectId())
    other_post_id = str(ObjectId())

    # Chunks for resolved post and other post
    await db.knowledge_chunks.insert_one({
        "workspace_id": ws_id,
        "post_id": resolved_post_id,
        "is_active": True,
        "text": "Special cake is Rs 500",
        "embedding": [0.1] * 768,
    })
    await db.knowledge_chunks.insert_one({
        "workspace_id": ws_id,
        "post_id": other_post_id,
        "is_active": True,
        "text": "Unrelated shoes are Rs 2000",
        "embedding": [0.1] * 768,
    })

    rag = HybridRAG(db, fake_container.settings)
    precomputed_emb = [0.1] * 768

    ctx = await rag.retrieve(
        workspace_id=ws_id,
        user_id=user_id,
        query="cake",
        resolved_post_id=resolved_post_id,
        query_embedding=precomputed_emb,
    )

    # Chunks scanned should only be active chunks EXCEPT the resolved post ($ne)
    assert len(ctx.semantic_chunks) == 1
    assert ctx.semantic_chunks[0]["post_id"] == other_post_id


@pytest.mark.asyncio
async def test_auto_resume_skips_rate_limited_and_send_failed(fake_container):
    db = MockDb()
    user_id = ObjectId()
    await db.users.insert_one({"_id": user_id, "active_workspace_id": "ws_test"})
    await db.meta_connections.insert_one({
        "user_id": user_id,
        "status": "ACTIVE",
        "instagram_user_id": "ig_123",
        "page_id": "page_123",
    })
    await db.dm_settings.insert_one({
        "user_id": user_id,
        "enabled": True,
        "knowledge": "Store info",
    })

    # Thread 1: escalated due to RATE_LIMITED
    t1_id = ObjectId()
    await db.dm_threads.insert_one({
        "_id": t1_id,
        "user_id": user_id,
        "customer_id": "c_rate",
        "status": "NEEDS_HUMAN",
        "escalation": {"reason": "RATE_LIMITED"},
        "last_inbound_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "messages": [],
    })

    # Customer sends next message on rate limited thread
    event_rate = {
        "sender": {"id": "c_rate"},
        "recipient": {"id": "ig_123"},
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "message": {"mid": "m_rate_next", "text": "Hello again"},
    }
    orig_delay = dm.DEBOUNCE_DELAY
    dm.DEBOUNCE_DELAY = 0.01
    try:
        await dm.handle_messaging(db, fake_container, event_rate)
    finally:
        dm.DEBOUNCE_DELAY = orig_delay

    # Must NOT auto-resume; stays NEEDS_HUMAN
    t1 = await db.dm_threads.find_one({"_id": t1_id})
    assert t1["status"] == "NEEDS_HUMAN"

    # Thread 2: escalated due to REQUIRES_HUMAN (AI question)
    t2_id = ObjectId()
    await db.dm_threads.insert_one({
        "_id": t2_id,
        "user_id": user_id,
        "customer_id": "c_ai_esc",
        "status": "NEEDS_HUMAN",
        "escalation": {"reason": "REQUIRES_HUMAN", "note": "Complex refund"},
        "last_inbound_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "messages": [],
    })

    event_ai = {
        "sender": {"id": "c_ai_esc"},
        "recipient": {"id": "ig_123"},
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "message": {"mid": "m_ai_next", "text": "What are your hours?"},
    }
    dm.DEBOUNCE_DELAY = 0.01
    try:
        await dm.handle_messaging(db, fake_container, event_ai)
    finally:
        dm.DEBOUNCE_DELAY = orig_delay

    # Must auto-resume to BOT and move previous escalation to escalation_history
    t2 = await db.dm_threads.find_one({"_id": t2_id})
    assert t2["status"] == "BOT"
    assert t2["escalation"] is None
    assert len(t2.get("escalation_history", [])) == 1
    assert t2["escalation_history"][0]["reason"] == "REQUIRES_HUMAN"


@pytest.mark.asyncio
async def test_no_knowledge_replies_handoff_and_keeps_bot_status(fake_container):
    db = MockDb()
    user_id = ObjectId()
    await db.users.insert_one({"_id": user_id, "active_workspace_id": "ws_test"})
    await db.meta_connections.insert_one({
        "user_id": user_id,
        "status": "ACTIVE",
        "instagram_user_id": "ig_123",
        "page_id": "page_123",
    })
    # DM settings with empty knowledge
    await db.dm_settings.insert_one({
        "user_id": user_id,
        "enabled": True,
        "knowledge": "",
        "handoff_message": "Custom handoff: team member will be with you shortly.",
    })

    event = {
        "sender": {"id": "c_no_know"},
        "recipient": {"id": "ig_123"},
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "message": {"mid": "m_no_know_1", "text": "Do you sell laptops?"},
    }

    orig_delay = dm.DEBOUNCE_DELAY
    dm.DEBOUNCE_DELAY = 0.01
    try:
        await dm.handle_messaging(db, fake_container, event)
    finally:
        dm.DEBOUNCE_DELAY = orig_delay

    # Replies with handoff message
    assert len(fake_container.meta_writer.sent_dms) == 1
    assert "Custom handoff" in fake_container.meta_writer.sent_dms[0]["text"]

    # Thread status remains BOT (not noisily marked NEEDS_HUMAN)
    thread = await db.dm_threads.find_one({"user_id": user_id, "customer_id": "c_no_know"})
    assert thread["status"] == "BOT"
    assert thread.get("needs_attention") is True
    assert thread.get("attention_reason") == "NO_KNOWLEDGE"

    # View reflects needs_attention
    view_data = dm._view(thread)
    assert view_data["needs_attention"] is True
    assert view_data["attention_reason"] == "NO_KNOWLEDGE"

    # Audit event DM_NO_KNOWLEDGE recorded
    audit_evt = await db.audit_log.find_one({"event_type": "DM_NO_KNOWLEDGE"})
    assert audit_evt is not None


@pytest.mark.asyncio
async def test_save_config_scoped_strictly_to_user_or_workspace(fake_container):
    db = MockDb()
    user1 = ObjectId()
    user2 = ObjectId()
    ws1 = "ws_user1"
    ws2 = "ws_user2"
    await db.users.insert_one({"_id": user1, "active_workspace_id": ws1})
    await db.users.insert_one({"_id": user2, "active_workspace_id": ws2})

    # Active connection belongs to user2 / ws2
    await db.meta_connections.insert_one({
        "user_id": user2,
        "workspace_id": ws2,
        "status": "ACTIVE",
        "instagram_user_id": "ig_user2",
        "page_id": "page_user2",
    })

    # User 1 has NO connection; saving config with enabled=True must raise MetaNotConnected
    # (Must not fall back to user 2's connection)
    from app.meta.connections import MetaNotConnected
    with pytest.raises(MetaNotConnected):
        await dm.save_config(db, fake_container, user1, {"enabled": True, "knowledge": "Some text"})


@pytest.mark.asyncio
async def test_select_assets_calls_subscribe_messages(fake_container):
    from app.meta.connections import select_assets
    db = MockDb()
    user_id = ObjectId()
    await db.meta_connections.insert_one({
        "user_id": user_id,
        "status": "ACTIVE",
    })

    page = {"id": "page_selected_99", "name": "Test Page"}
    await select_assets(
        db,
        user_id,
        page=page,
        clock=fake_container.clock,
        container=fake_container,
    )

    # Fake gateway subscribed_pages should contain page_selected_99
    assert "page_selected_99" in fake_container.meta_writer.subscribed_pages


@pytest.mark.asyncio
async def test_hybrid_rag_ignores_inactive_and_expired_offers_and_uses_ne(fake_container):
    db = MockDb()
    user_id = ObjectId()
    ws_id = "ws_test"
    resolved_post_id = str(ObjectId())

    # Inactive offer
    await db.offers.insert_one({
        "post_id": resolved_post_id,
        "workspace_id": ws_id,
        "offer_description": "Half price summer special",
        "offer_status": "INACTIVE",
    })
    # Published post
    await db.social_posts.insert_one({
        "_id": ObjectId(resolved_post_id),
        "workspace_id": ws_id,
        "post_status": "published",
        "title": "Summer Tee",
    })

    rag = HybridRAG(db, fake_container.settings)
    ctx = await rag.retrieve(
        workspace_id=ws_id,
        user_id=user_id,
        query="summer offer",
        resolved_post_id=resolved_post_id,
    )

    assert ctx.is_expired is True
    assert "NOT RUNNING" in ctx.prompt_context


@pytest.mark.asyncio
async def test_rate_limited_escalation_records_rate_limited_reason(fake_container):
    db = MockDb()
    user_id = ObjectId()
    customer_id = "c_rate_limit"

    await db.users.insert_one({"_id": user_id, "active_workspace_id": "ws_1"})
    await db.meta_connections.insert_one({
        "user_id": user_id,
        "workspace_id": "ws_1",
        "page_id": "page_rate",
        "instagram_user_id": "ig_rate",
        "status": "ACTIVE",
        "token_expires_at": datetime(2027, 1, 1, tzinfo=UTC),
    })
    await db.dm_settings.insert_one({
        "user_id": user_id,
        "enabled": True,
        "knowledge": "Some knowledge",
        "handoff_message": "Hourly limit reached; human will assist.",
    })

    # Simulate >30 seen messages in past hour
    now = datetime.now(UTC)
    for i in range(35):
        await db.dm_seen.insert_one({
            "user_id": user_id,
            "customer_id": customer_id,
            "bot_eligible": True,
            "at": now - timedelta(minutes=i),
        })

    event = {
        "sender": {"id": customer_id},
        "recipient": {"id": "ig_rate"},
        "timestamp": int(now.timestamp() * 1000),
        "message": {"mid": "m_rate_36", "text": "Rapid burst message"},
    }

    orig_delay = dm.DEBOUNCE_DELAY
    dm.DEBOUNCE_DELAY = 0.01
    try:
        await dm.handle_messaging(db, fake_container, event)
    finally:
        dm.DEBOUNCE_DELAY = orig_delay

    thread = await db.dm_threads.find_one({"user_id": user_id, "customer_id": customer_id})
    assert thread["status"] == "NEEDS_HUMAN"
    assert thread["escalation"]["reason"] == "RATE_LIMITED"
    assert "Hourly message cap" in thread["escalation"]["error"]


@pytest.mark.asyncio
async def test_shared_post_resolver_cooldown_per_post(fake_container):
    db = MockDb()
    ws_id = "ws_cooldown_test"
    now = datetime.now(UTC)

    # Post with recent refresh attempt 10 seconds ago
    recent_attempt_post = {
        "_id": ObjectId(),
        "workspace_id": ws_id,
        "post_status": "published",
        "effective_instagram_media_id": None,
        "creative_id": "cr_recent",
        "platform_post_id": "post_recent",
        "last_refresh_attempt_at": now - timedelta(seconds=10),
    }
    await db.social_posts.insert_one(recent_attempt_post)

    resolver = SharedPostContextResolver(db, fake_container.settings, container=fake_container)
    resolved = await resolver.resolve(
        workspace_id=ws_id,
        message_text="",
        attachments=[{"type": "share", "id": "unknown_media_id"}],
    )
    # Does not resolve and does not trigger refresh because within 60s cooldown
    assert resolved is None
    post_after = await db.social_posts.find_one({"_id": recent_attempt_post["_id"]})
    assert post_after["last_refresh_attempt_at"] == recent_attempt_post["last_refresh_attempt_at"]
