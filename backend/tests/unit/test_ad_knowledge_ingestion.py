"""Tests for Ad -> DM knowledge ingestion:
1. Publisher ingests ad with real Instagram media ID and permalink, plus CTA, offer, landing_url, audience, dates.
2. Ingestion reliability: retry with backoff on FAILED, and startup re-running of PENDING/FAILED jobs.
3. Ad lifecycle: re-ingest on resume (_go_live), chunk deactivation on pause, complete, and delete.
4. Security: HybridRAG isolation - two users never see each other's dm_settings, no unrestricted fallback.
5. Workspace ID resolver: single source of truth prioritizing campaign then user active workspace.
6. DM Resolution: resolves shared ad by exact ad_id and effective_instagram_media_id.
"""

import copy
import re
from datetime import UTC, datetime
from bson import ObjectId
import pytest

from app.clock import FixedClock
from app.config import Settings
from app.container import Container
from app.domain.ad_states import AdState
from app.domain.workspaces import resolve_workspace_id
from app.meta.fake import FakeAdsGateway
from app.meta.publisher import ingest_ad_campaign
from app.services import ad_lifecycle, social_knowledge
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
                elif op == "$nin":
                    str_op_vals = {str(x) for x in op_val}
                    if str(doc_val) in str_op_vals:
                        return False
                elif op == "$regex":
                    flags = re.IGNORECASE if val.get("$options") == "i" else 0
                    if not re.search(op_val, str(doc_val or ""), flags):
                        return False
            continue

        # Direct equality check (handling string and ObjectId equivalency)
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
        self.docs.append(d)
        class Res:
            inserted_id = d["_id"]
        return Res()

    async def find_one(self, filter_query: dict | None = None, projection=None):
        filter_query = filter_query or {}
        for d in self.docs:
            if _matches(d, filter_query):
                return copy.deepcopy(d)
        return None

    def find(self, filter_query: dict | None = None, projection=None):
        filter_query = filter_query or {}
        matched = [copy.deepcopy(d) for d in self.docs if _matches(d, filter_query)]
        return MockCursor(matched)

    async def count_documents(self, filter_query: dict | None = None) -> int:
        filter_query = filter_query or {}
        return sum(1 for d in self.docs if _matches(d, filter_query))

    async def update_one(self, filter_query: dict, update: dict, upsert: bool = False, session=None, **kwargs):
        for d in self.docs:
            if _matches(d, filter_query):
                self._apply_update(d, update)
                return
        if upsert:
            new_doc = copy.deepcopy(filter_query)
            if "$or" in new_doc:
                first = new_doc.pop("$or")[0]
                new_doc.update(first)
            if "_id" not in new_doc:
                new_doc["_id"] = ObjectId()
            if "$setOnInsert" in update:
                new_doc.update(copy.deepcopy(update["$setOnInsert"]))
            self._apply_update(new_doc, update)
            self.docs.append(new_doc)

    async def update_many(self, filter_query: dict, update: dict, session=None, **kwargs):
        for d in self.docs:
            if _matches(d, filter_query):
                self._apply_update(d, update)

    async def delete_one(self, filter_query: dict, session=None, **kwargs):
        for i, d in enumerate(self.docs):
            if _matches(d, filter_query):
                del self.docs[i]
                return

    async def delete_many(self, filter_query: dict, session=None, **kwargs):
        self.docs = [d for d in self.docs if not _matches(d, filter_query)]

    async def find_one_and_update(self, filter_query: dict, update: dict, return_document=None, upsert=False, session=None, **kwargs):
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

    def _apply_update(self, target: dict, update: dict):
        if "$set" in update:
            for k, v in update["$set"].items():
                if "." in k:
                    parts = k.split(".")
                    cur = target
                    for p in parts[:-1]:
                        cur = cur.setdefault(p, {})
                    cur[parts[-1]] = copy.deepcopy(v)
                else:
                    target[k] = copy.deepcopy(v)
        if "$inc" in update:
            for k, v in update["$inc"].items():
                target[k] = target.get(k, 0) + v
        if "$unset" in update:
            for k in update["$unset"]:
                target.pop(k, None)


class MockDb:
    def __init__(self):
        self._cols: dict[str, MockCollection] = {}

    def __getattr__(self, name: str) -> MockCollection:
        if name not in self._cols:
            self._cols[name] = MockCollection(name)
        return self._cols[name]

    def __getitem__(self, name: str) -> MockCollection:
        return getattr(self, name)


@pytest.fixture
def mock_db():
    return MockDb()


@pytest.fixture
def test_clock():
    return FixedClock(datetime(2026, 11, 5, 10, 0, tzinfo=UTC))


@pytest.fixture
def test_container(test_clock):
    import base64
    settings = Settings(
        _env_file=None,
        app_env="test",
        mongodb_uri="mongodb://localhost:27017",
        jwt_secret="t" * 32,
        token_encryption_key=base64.b64encode(bytes(range(32))).decode(),
        meta_mode="fake",
        llm_provider="scripted",
        allow_real_ad_spend=True,
        safe_mode_no_spend=False,
    )
    fake_gateway = FakeAdsGateway()

    async def run_inline(coro):
        await coro

    return Container(
        settings=settings,
        clock=test_clock,
        gateway_for=lambda conn: (fake_gateway, fake_gateway),
        image_generator=None,
        spawn=run_inline,
        retry_wait=None,
    )


# --- 1. Workspace ID Resolver Tests ---

def test_workspace_id_resolution_order():
    # Case 1: Campaign has explicit workspace_id
    camp = {"workspace_id": "ws_campaign_explicit", "title": "Test Ad"}
    user = {"active_workspace_id": "ws_user_profile"}
    assert resolve_workspace_id(campaign=camp, user=user) == "ws_campaign_explicit"

    # Case 2: Campaign has no workspace_id, user has active_workspace_id
    camp_no_ws = {"title": "Test Ad"}
    assert resolve_workspace_id(campaign=camp_no_ws, user=user) == "ws_user_profile"

    # Case 3: Neither has workspace_id -> falls back to default
    assert resolve_workspace_id(campaign={}, user={}) == "synxait"
    assert resolve_workspace_id(default="custom_default") == "custom_default"


# --- 2. Ingest Ad with Creative IDs & Metadata Tests ---

@pytest.mark.asyncio
async def test_publish_ad_ingests_creative_media_and_campaign_metadata(mock_db, test_container):
    user_id = ObjectId()
    camp_id = ObjectId()

    # Pre-populate user and meta connection
    await mock_db.users.insert_one({"_id": user_id, "active_workspace_id": "ws_agency_1"})
    await mock_db.meta_connections.insert_one({
        "user_id": user_id,
        "workspace_id": "ws_agency_1",
        "ad_account_id": "act_123",
        "page_id": "page_123",
        "instagram_user_id": "ig_user_123",
        "status": "ACTIVE",
        "token_expires_at": datetime(2027, 1, 1, tzinfo=UTC),
    })

    # Fake gateway objects
    fake_gw = test_container.gateway_for({})[0]
    fake_gw.objects["creative_999"] = {
        "edge": "adcreatives",
        "effective_instagram_media_id": "17841416182311813_ad_post",
        "instagram_permalink_url": "https://instagram.com/p/CREATIVE_SHORTCODE_999",
    }

    campaign = {
        "_id": camp_id,
        "user_id": user_id,
        "workspace_id": "ws_agency_1",
        "title": "Gourmet Pizza Promo",
        "idea": "50% off on all artisan wood-fired pizzas this weekend only!",
        "landing_url": "https://priyapizza.example.com/deal",
        "start_date": "2026-11-06",
        "end_date": "2026-11-08",
        "audience": {
            "interests": [{"id": "6001", "name": "Pizza"}, {"id": "6002", "name": "Italian food"}],
        },
        "selected_variant": 0,
        "variants": [
            {
                "headline": "Crispy Wood-Fired Pizza Deal",
                "primary_text": "Enjoy authentic Italian pizza delivered fresh to your door.",
                "description": "50% discount applied automatically at checkout.",
                "call_to_action": "ORDER_NOW",
            }
        ],
        "meta": {
            "campaign_id": "camp_meta_1",
            "adset_id": "adset_meta_1",
            "creative_id": "creative_999",
            "ad_id": "ad_meta_1001",
        },
        "status": AdState.ACTIVE.value,
        "rev": 1,
    }
    await mock_db.campaigns.insert_one(campaign)

    # Ingest the ad
    res = await ingest_ad_campaign(mock_db, test_container, campaign)
    assert res is not None
    assert res["status"] == "INGESTED"

    # Verify social_posts document
    post = await mock_db.social_posts.find_one({"campaign_id": camp_id})
    assert post is not None
    assert post["ad_id"] == "ad_meta_1001"
    assert post["effective_instagram_media_id"] == "17841416182311813_ad_post"
    assert post["platform_post_id"] == "17841416182311813_ad_post"
    assert post["post_url"] == "https://instagram.com/p/CREATIVE_SHORTCODE_999"
    assert post["cta"] == "ORDER_NOW"
    assert post["landing_url"] == "https://priyapizza.example.com/deal"
    assert post["start_date"] == "2026-11-06"
    assert post["end_date"] == "2026-11-08"
    assert "50% off" in post["offer"]

    # Verify knowledge_chunks exist and are active
    chunks = [c async for c in mock_db.knowledge_chunks.find({"post_id": res["id"]})]
    assert len(chunks) >= 3
    assert all(c["is_active"] is True for c in chunks)
    assert any(c["chunk_type"] == "campaign_action" for c in chunks)

    action_chunk = next(c for c in chunks if c["chunk_type"] == "campaign_action")
    assert "ORDER_NOW" in action_chunk["text"]
    assert "https://priyapizza.example.com/deal" in action_chunk["text"]
    assert "2026-11-06" in action_chunk["text"]


# --- 3. DM Resolution by Exact ID Tests ---

@pytest.mark.asyncio
async def test_dm_shares_ad_resolves_by_exact_id(mock_db, test_container):
    ws_id = "ws_agency_1"
    ad_id = "120254994914340712"
    effective_media_id = "17841416182311813_post_999"

    # Insert published ad post into social_posts
    await mock_db.social_posts.insert_one({
        "workspace_id": ws_id,
        "platform_post_id": effective_media_id,
        "ad_id": ad_id,
        "effective_instagram_media_id": effective_media_id,
        "title": "Double Cheeseburger Deal",
        "caption": "Handcrafted Double Cheeseburger for ₹199! Use code BURGER50.",
        "post_url": f"https://instagram.com/p/{effective_media_id}",
        "post_status": "published",
        "ad_campaign_status": "active",
    })

    resolver = SharedPostContextResolver(mock_db, test_container.settings)

    # Resolution A: Customer shares the ad as an attachment with ad_id
    resolved_by_ad = await resolver.resolve(
        workspace_id=ws_id,
        attachments=[{"type": "share", "id": ad_id}],
    )
    assert resolved_by_ad is not None
    assert resolved_by_ad.match_method == "exact_platform_id"
    assert resolved_by_ad.title == "Double Cheeseburger Deal"

    # Resolution B: Customer shares with effective_instagram_media_id
    resolved_by_ig = await resolver.resolve(
        workspace_id=ws_id,
        attachments=[{"type": "share", "id": effective_media_id}],
    )
    assert resolved_by_ig is not None
    assert resolved_by_ig.match_method == "exact_platform_id"
    assert resolved_by_ig.title == "Double Cheeseburger Deal"

    # Resolution C: Customer mentions explicit ad ID in text
    resolved_by_text = await resolver.resolve(
        workspace_id=ws_id,
        message_text=f"Is the deal in ad #{ad_id} still available?",
    )
    assert resolved_by_text is not None
    assert resolved_by_text.match_method == "exact_platform_id"

    # Resolution D: Customer mentions effective media ID in text
    resolved_by_ig_text = await resolver.resolve(
        workspace_id=ws_id,
        message_text=f"Hello, I saw your post id: {effective_media_id}",
    )
    assert resolved_by_ig_text is not None
    assert resolved_by_ig_text.match_method == "exact_platform_id"


# --- 4. Security Isolation: Two Users Never See Each Other's dm_settings ---

@pytest.mark.asyncio
async def test_security_two_users_never_see_each_others_dm_settings(mock_db, test_container):
    user_alice = ObjectId()
    user_bob = ObjectId()
    user_carol = ObjectId()

    # User Alice's DM settings
    await mock_db.dm_settings.insert_one({
        "user_id": user_alice,
        "workspace_id": "ws_alice",
        "business_name": "Alice Bakery",
        "knowledge": "Secret Sourdough Recipe with 48h fermentation. Open 7am-4pm.",
        "tone": "Warm and artisanal",
    })

    # User Bob's DM settings
    await mock_db.dm_settings.insert_one({
        "user_id": user_bob,
        "workspace_id": "ws_bob",
        "business_name": "Bob Auto Repairs",
        "knowledge": "Specializes in German transmission repairs. Warranty 2 years.",
        "tone": "Direct and professional",
    })

    rag = HybridRAG(mock_db, test_container.settings)

    # Query for Alice passing user_id=user_alice
    ctx_alice = await rag.retrieve(
        workspace_id="ws_alice",
        user_id=user_alice,
        query="What is your recipe and hours?",
    )
    assert "Secret Sourdough Recipe" in ctx_alice.prompt_context
    assert "Alice Bakery" in ctx_alice.prompt_context
    assert "German transmission" not in ctx_alice.prompt_context
    assert "Bob Auto" not in ctx_alice.prompt_context

    # Query for Bob passing user_id=user_bob
    ctx_bob = await rag.retrieve(
        workspace_id="ws_bob",
        user_id=user_bob,
        query="What services do you offer?",
    )
    assert "German transmission" in ctx_bob.prompt_context
    assert "Bob Auto Repairs" in ctx_bob.prompt_context
    assert "Secret Sourdough" not in ctx_bob.prompt_context
    assert "Alice Bakery" not in ctx_bob.prompt_context

    # Query for Carol who has NO dm_settings configured
    ctx_carol = await rag.retrieve(
        workspace_id="ws_carol",
        user_id=user_carol,
        query="Tell me about your business",
    )
    # MUST NOT fallback to Alice or Bob's settings!
    assert ctx_carol.general_knowledge == ""
    assert "Secret Sourdough" not in ctx_carol.prompt_context
    assert "German transmission" not in ctx_carol.prompt_context
    assert "Alice Bakery" not in ctx_carol.prompt_context
    assert "Bob Auto" not in ctx_carol.prompt_context


# --- 5. Ad Lifecycle: Pause, Resume, Delete, and End Deactivation Tests ---

@pytest.mark.asyncio
async def test_lifecycle_chunk_deactivation_and_resume_reingestion(mock_db, test_container):
    user_id = ObjectId()
    camp_id = ObjectId()
    ws_id = "ws_lifecycle_test"

    await mock_db.users.insert_one({"_id": user_id, "active_workspace_id": ws_id})
    await mock_db.meta_connections.insert_one({
        "user_id": user_id,
        "workspace_id": ws_id,
        "ad_account_id": "act_test",
        "page_id": "page_test",
        "instagram_user_id": "ig_test",
        "status": "ACTIVE",
        "token_expires_at": datetime(2027, 1, 1, tzinfo=UTC),
    })

    fake_gw = test_container.gateway_for({})[0]
    fake_gw.objects["creative_lifecycle"] = {
        "edge": "adcreatives",
        "effective_instagram_media_id": "ig_media_lifecycle",
        "instagram_permalink_url": "https://instagram.com/p/lifecycle",
    }
    fake_gw.objects["camp_obj_1"] = {"edge": "campaigns", "params": {}, "status": "ACTIVE"}

    campaign = {
        "_id": camp_id,
        "user_id": user_id,
        "workspace_id": ws_id,
        "title": "Weekend Mega Sale",
        "idea": "Buy 1 Get 1 Free on all items",
        "landing_url": "https://example.com/bogo",
        "selected_variant": 0,
        "variants": [{"headline": "BOGO Mega Sale", "primary_text": "Great savings", "description": "BOGO", "call_to_action": "SHOP_NOW"}],
        "meta": {"campaign_id": "camp_obj_1", "creative_id": "creative_lifecycle", "ad_id": "ad_obj_1"},
        "status": AdState.ACTIVE.value,
        "rev": 1,
    }
    await mock_db.campaigns.insert_one(campaign)

    # 1. Ingest ad initially
    await ingest_ad_campaign(mock_db, test_container, campaign)
    active_chunks = [c async for c in mock_db.knowledge_chunks.find({"campaign_id": str(camp_id), "is_active": True})]
    assert len(active_chunks) > 0

    # 2. Pause campaign -> chunks become is_active=False
    await ad_lifecycle.pause(mock_db, campaign, container=test_container)
    paused_chunks = [c async for c in mock_db.knowledge_chunks.find({"campaign_id": str(camp_id), "is_active": True})]
    assert len(paused_chunks) == 0

    paused_post = await mock_db.social_posts.find_one({"campaign_id": camp_id})
    assert paused_post["ad_campaign_status"] == "paused"

    # 3. Resume campaign -> _go_live re-ingests and chunks become is_active=True
    fresh_paused = await mock_db.campaigns.find_one({"_id": camp_id})
    await ad_lifecycle.resume(mock_db, fresh_paused, container=test_container)

    resumed_chunks = [c async for c in mock_db.knowledge_chunks.find({"campaign_id": str(camp_id), "is_active": True})]
    assert len(resumed_chunks) > 0
    resumed_post = await mock_db.social_posts.find_one({"campaign_id": camp_id})
    assert resumed_post["ad_campaign_status"] == "active"

    # 4. Deactivate on deletion
    await social_knowledge.deactivate_campaign_knowledge(mock_db, camp_id, clock=test_container.clock, status="deleted")
    deleted_chunks = [c async for c in mock_db.knowledge_chunks.find({"campaign_id": str(camp_id), "is_active": True})]
    assert len(deleted_chunks) == 0
    deleted_post = await mock_db.social_posts.find_one({"campaign_id": camp_id})
    assert deleted_post["ad_campaign_status"] == "deleted"
    assert deleted_post["post_status"] == "deleted"


# --- 6. Ingestion Reliability: Retry with Backoff & Startup Reprocessing ---

@pytest.mark.asyncio
async def test_failed_ingestion_retries_and_startup_reprocesses(mock_db, test_container, monkeypatch):
    user_id = ObjectId()
    ws_id = "ws_reliability"
    call_count = {"count": 0}

    # Monkeypatch understand_post to fail twice, then succeed
    async def mock_understand_post(*args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] < 3:
            raise RuntimeError("Temporary Meta/LLM API rate limit error")
        from app.domain.social_knowledge import PostUnderstandingOutput
        return PostUnderstandingOutput(
            post_type="special_offer",
            subject="Coffee Offer",
            summary="Artisan coffee discount",
            keywords=["coffee", "latte"],
            confidence_score=1.0,
        )

    monkeypatch.setattr("app.services.social_knowledge.understand_post", mock_understand_post)

    # 1. Ingest post (auto_process=True triggers process_post_understanding)
    res = await social_knowledge.ingest_post(
        mock_db,
        test_container,
        user_id=user_id,
        workspace_id=ws_id,
        platform="instagram",
        platform_post_id="post_retry_test",
        title="Fresh Brew Coffee",
        caption="Try our artisan roast",
        auto_process=True,
    )
    post_id = res["id"]

    # In test mode, spawn runs inline, so failure triggers retry with delay=0 immediately
    job = await mock_db.knowledge_jobs.find_one({"post_id": post_id})
    assert job is not None
    # Called 3 times: initial attempt + 2 retries -> success!
    assert call_count["count"] == 3
    assert job["status"] == "READY"

    post = await mock_db.social_posts.find_one({"_id": ObjectId(post_id)})
    assert post["knowledge_status"] == "READY"

    # 2. Test startup recovery for PENDING or FAILED jobs
    # Create an orphaned FAILED job
    orphaned_id = ObjectId()
    await mock_db.social_posts.insert_one({
        "_id": orphaned_id,
        "workspace_id": ws_id,
        "user_id": user_id,
        "platform": "instagram",
        "platform_post_id": "orphaned_post_1",
        "title": "Orphaned Post",
        "caption": "Re-run me on startup",
        "post_status": "published",
        "knowledge_status": "FAILED",
    })
    await mock_db.knowledge_jobs.insert_one({
        "post_id": str(orphaned_id),
        "workspace_id": ws_id,
        "status": "FAILED",
        "retry_count": 3,
    })

    # Call startup reprocess
    reprocessed = await social_knowledge.reprocess_pending_or_failed_jobs(mock_db, test_container)
    assert reprocessed == 1

    recovered_job = await mock_db.knowledge_jobs.find_one({"post_id": str(orphaned_id)})
    assert recovered_job["status"] == "READY"

    recovered_post = await mock_db.social_posts.find_one({"_id": orphaned_id})
    assert recovered_post["knowledge_status"] == "READY"


@pytest.mark.asyncio
async def test_creative_refresh_on_delay_and_dm_resolve_miss(mock_db, test_container):
    user_id = ObjectId()
    camp_id = ObjectId()
    ws_id = "ws_delay_test"
    creative_id = "cr_test_delay_123"

    await mock_db.users.insert_one({"_id": user_id, "active_workspace_id": ws_id})
    await mock_db.meta_connections.insert_one({
        "user_id": user_id,
        "workspace_id": ws_id,
        "ad_account_id": "act_delay",
        "page_id": "page_delay",
        "instagram_user_id": "ig_delay",
        "status": "ACTIVE",
        "token_expires_at": datetime(2027, 1, 1, tzinfo=UTC),
    })

    campaign = {
        "_id": camp_id,
        "user_id": user_id,
        "workspace_id": ws_id,
        "title": "Delayed Creative Ad Campaign",
        "meta": {
            "ad_id": "ad_delay_999",
            "creative_id": creative_id,
            "effective_instagram_media_id": None,
            "permalink": None,
        },
        "content": {"headline": "Delayed Head", "primary_text": "Delayed Text"},
        "offer": {"discount": "10% off"},
        "landing_url": "https://synxait.com/delayed",
        "call_to_action": "LEARN_MORE",
        "target_audience": "Tech enthusiasts",
        "start_date": "2026-05-01",
        "end_date": "2026-06-01",
        "status": "ACTIVE",
    }

    # Step 1: Ingest ad campaign where FakeAdsGateway returns None at first
    from app.meta.publisher import ingest_ad_campaign, refresh_ad_creative

    async def defer(coro):  # background polling must not run inline in this test
        coro.close()

    test_container.spawn = defer
    await ingest_ad_campaign(mock_db, test_container, campaign)

    post = await mock_db.social_posts.find_one({"campaign_id": campaign["_id"]})
    assert post is not None
    # Initially effective_instagram_media_id is None because first poll returns None
    assert post["effective_instagram_media_id"] is None
    assert post["platform_post_id"] == "ad_delay_999"

    # Step 2: DM resolve miss occurs when customer shares the real IG media ID
    # SharedPostContextResolver should invoke refresh_ad_creative on miss and find the match
    resolver = SharedPostContextResolver(mock_db, test_container.settings, container=test_container)
    resolved = await resolver.resolve(
        workspace_id=ws_id,
        message_text="",
        attachments=[{"type": "share", "id": f"ig_media_{creative_id}"}],
    )

    assert resolved is not None
    assert resolved.platform_post_id == f"ig_media_{creative_id}"

    # Verify social_posts was updated with effective_instagram_media_id and post_url
    updated_post = await mock_db.social_posts.find_one({"_id": post["_id"]})
    assert updated_post["effective_instagram_media_id"] == f"ig_media_{creative_id}"
    assert updated_post["platform_post_id"] == f"ig_media_{creative_id}"
    assert f"ig_media_{creative_id}" in updated_post["post_url"]


@pytest.mark.asyncio
async def test_startup_recovers_pending_creative_refreshes(mock_db, test_container):
    from app.meta.publisher import recover_pending_creative_refreshes

    async def defer(coro):
        coro.close()

    test_container.spawn = defer
    post_id = ObjectId()
    await mock_db.social_posts.insert_one({
        "_id": post_id,
        "created_at": test_container.clock.now(),
        "workspace_id": "ws_startup_recovery",
        "post_status": "published",
        "effective_instagram_media_id": None,
        "creative_id": "cr_startup_123",
        "platform_post_id": "ad_startup_123",
    })

    count = await recover_pending_creative_refreshes(mock_db, test_container)
    assert count == 1
