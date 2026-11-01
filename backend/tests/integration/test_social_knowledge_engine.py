"""Comprehensive tests for Dynamic Social Knowledge Engine, SharedPostContextResolver & Hybrid RAG."""

import pytest
from datetime import UTC, datetime, timedelta
from bson import ObjectId

from app.domain.social_knowledge import ExtractedOffer, ExtractedProduct, PostUnderstandingOutput
from app.services import social_knowledge
from app.services.hybrid_rag import HybridRAG
from app.services.shared_post_resolver import SharedPostContextResolver


@pytest.fixture
def mock_clock():
    class Clock:
        def __init__(self):
            self._now = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)

        def now(self):
            return self._now

        def advance(self, td: timedelta):
            self._now += td

    return Clock()


async def test_post_ingestion_and_understanding_pipeline(db, container):
    """Verifies that an adcraft post is ingested, analyzed, structured and indexed into vector chunks."""
    user_id = ObjectId()
    ws_id = "test_ws_burger"

    ingest_res = await social_knowledge.ingest_post(
        db,
        container,
        user_id=user_id,
        workspace_id=ws_id,
        platform="instagram",
        platform_post_id="ig_burger_101",
        post_url="https://instagram.com/p/ig_burger_101",
        title="Delicious Double Burger Combo",
        caption="Try our handcrafted Double Cheeseburger Combo with crispy fries and drink for only ₹199! Valid until 2026-11-15.",
        media_reference="img_burger_1",
        source="adcraft",
        auto_process=False,  # Run explicitly to assert step-by-step
    )

    assert ingest_res["status"] == "INGESTED"
    post_id = ingest_res["id"]

    # Verify pending state
    post_doc = await db.social_posts.find_one({"_id": ObjectId(post_id)})
    assert post_doc["knowledge_status"] == "PENDING"
    assert post_doc["post_status"] == "published"

    # Process post understanding
    proc_res = await social_knowledge.process_post_understanding(db, container, post_id)
    assert proc_res["status"] == "READY"
    assert proc_res["chunks_indexed"] >= 3

    # Verify structured post
    updated_post = await db.social_posts.find_one({"_id": ObjectId(post_id)})
    assert updated_post["knowledge_status"] == "READY"
    assert "burger" in updated_post["summary"].lower()

    # Verify structured product
    product = await db.products.find_one({"workspace_id": ws_id})
    assert product is not None
    assert product["price"] == 199.0

    # Verify structured offer
    offer = await db.offers.find_one({"post_id": post_id, "workspace_id": ws_id})
    assert offer is not None
    assert offer["price"] == 199.0
    assert offer["valid_until"] == "2026-11-15"
    assert offer["offer_status"] == "ACTIVE"

    # Verify vector knowledge chunks created and active
    chunks = [c async for c in db.knowledge_chunks.find({"post_id": post_id, "is_active": True})]
    assert len(chunks) >= 3
    types = {c["chunk_type"] for c in chunks}
    assert "summary" in types
    assert "offer" in types
    assert all(len(c["embedding"]) == 64 for c in chunks)


async def test_offer_validity_and_unknown_expiry_escalation(db, container):
    """Verifies that an offer without expiry is marked UNKNOWN_VALIDITY and triggers escalation."""
    user_id = ObjectId()
    ws_id = "test_ws_unknown_expiry"

    # Ingest a post without an expiry date
    res = await social_knowledge.ingest_post(
        db,
        container,
        user_id=user_id,
        workspace_id=ws_id,
        platform="instagram",
        platform_post_id="ig_special_promo",
        title="Special Pizza Deal",
        caption="Large Farmhouse Pizza with Garlic Bread at ₹299. Special discount this week!",
        auto_process=True,
    )
    post_id = res["id"]
    await social_knowledge.process_post_understanding(db, container, post_id)

    offer = await db.offers.find_one({"post_id": post_id})
    assert offer["valid_until"] is None
    assert offer["offer_status"] == "UNKNOWN_VALIDITY"

    # Hybrid RAG retrieval should flag unknown_validity
    rag = HybridRAG(db, container.settings)
    h_context = await rag.retrieve(workspace_id=ws_id, query="Is this pizza deal valid today?", resolved_post_id=post_id)
    assert h_context.unknown_validity is True
    assert "expiry is UNKNOWN" in h_context.prompt_context

    # DM Agent response should escalate with MISSING_OFFER_EXPIRY
    from app.agents.dm_agent import answer_dm
    ans = await answer_dm(
        knowledge={"prompt_context": h_context.prompt_context},
        history=[],
        message="Is this pizza deal valid today?",
        settings=container.settings,
    )
    assert ans.needs_human is True
    assert ans.escalation_reason == "MISSING_OFFER_EXPIRY"


async def test_expired_offer_handling(db, container):
    """Verifies that expired offers are marked EXPIRED and excluded from active claims."""
    user_id = ObjectId()
    ws_id = "test_ws_expired"

    res = await social_knowledge.ingest_post(
        db,
        container,
        user_id=user_id,
        workspace_id=ws_id,
        platform="instagram",
        platform_post_id="ig_past_offer",
        title="Halloween Special Offer",
        caption="Halloween discount valid until 2026-10-10 at ₹99.",
        auto_process=True,
    )
    post_id = res["id"]
    await social_knowledge.process_post_understanding(db, container, post_id)

    offer = await db.offers.find_one({"post_id": post_id})
    assert offer["offer_status"] == "EXPIRED"

    rag = HybridRAG(db, container.settings)
    h_context = await rag.retrieve(workspace_id=ws_id, query="Can I get this Halloween offer?", resolved_post_id=post_id)
    assert h_context.is_expired is True
    assert "THIS OFFER HAS EXPIRED" in h_context.prompt_context

    from app.agents.dm_agent import answer_dm
    ans = await answer_dm(
        knowledge={"prompt_context": h_context.prompt_context},
        history=[],
        message="Can I get this Halloween offer?",
        settings=container.settings,
    )
    assert "expired" in ans.text.lower()


async def test_shared_post_context_resolver_priorities(db, container):
    """Tests the resolution hierarchy: exact ID > URL > attachment > caption > semantic."""
    user_id = ObjectId()
    ws_id = "test_ws_resolver"

    # Seed 3 posts
    p1 = await social_knowledge.ingest_post(
        db, container, user_id=user_id, workspace_id=ws_id,
        platform="instagram", platform_post_id="post_exact_123",
        post_url="https://instagram.com/p/post_exact_123",
        title="Handcrafted Coffee and Pastry",
        caption="Enjoy rich roasted espresso with fresh blueberry muffin.",
        auto_process=True,
    )
    await social_knowledge.process_post_understanding(db, container, p1["id"])

    p2 = await social_knowledge.ingest_post(
        db, container, user_id=user_id, workspace_id=ws_id,
        platform="instagram", platform_post_id="reel_pasta_456",
        post_url="https://instagram.com/reel/reel_pasta_456",
        title="Authentic Italian Pasta Night",
        caption="Creamy Alfredo and Truffle pasta made fresh daily.",
        auto_process=True,
    )
    await social_knowledge.process_post_understanding(db, container, p2["id"])

    resolver = SharedPostContextResolver(db, container.settings)

    # 1. Match by exact platform ID in attachment
    res1 = await resolver.resolve(
        workspace_id=ws_id,
        attachments=[{"type": "share", "id": "post_exact_123"}],
    )
    assert res1 is not None
    assert res1.post_id == p1["id"]
    assert res1.match_method == "exact_platform_id"

    # 2. Match by URL in message text
    res2 = await resolver.resolve(
        workspace_id=ws_id,
        message_text="Hey! Can I get this? https://instagram.com/reel/reel_pasta_456",
    )
    assert res2 is not None
    assert res2.post_id == p2["id"]
    assert res2.match_method == "exact_url"

    # 3. Match by caption substring
    res3 = await resolver.resolve(
        workspace_id=ws_id,
        message_text="Do you still have the rich roasted espresso with fresh blueberry muffin?",
    )
    assert res3 is not None
    assert res3.post_id == p1["id"]
    assert res3.match_method in ("caption_match", "semantic_similarity")

    # 4. Semantic similarity match
    res4 = await resolver.resolve(
        workspace_id=ws_id,
        message_text="Tell me about the truffle alfredo noodles dinner",
    )
    assert res4 is not None
    assert res4.post_id == p2["id"]
    assert res4.match_method == "semantic_similarity"


async def test_post_deletion_lifecycle_and_rag_exclusion(db, container):
    """Verifies that deleting a post immediately removes its active chunks from vector retrieval."""
    user_id = ObjectId()
    ws_id = "test_ws_deletion"

    p = await social_knowledge.ingest_post(
        db, container, user_id=user_id, workspace_id=ws_id,
        platform="instagram", platform_post_id="ig_delete_target",
        title="Temporary Weekend Special",
        caption="Temporary dessert weekend special at ₹75.",
        auto_process=True,
    )
    post_id = p["id"]
    await social_knowledge.process_post_understanding(db, container, post_id)

    # Confirm it is initially retrievable
    chunks_before = [c async for c in db.knowledge_chunks.find({"post_id": post_id, "is_active": True})]
    assert len(chunks_before) > 0

    # Delete the post
    del_res = await social_knowledge.delete_post_knowledge(db, post_id, ws_id, source="user")
    assert del_res["status"] == "DELETED"

    # Confirm chunks are deactivated
    chunks_after = [c async for c in db.knowledge_chunks.find({"post_id": post_id, "is_active": True})]
    assert len(chunks_after) == 0

    # Confirm audit logged
    audit = await db.post_deletion_audit.find_one({"post_id": post_id, "workspace_id": ws_id})
    assert audit is not None
    assert audit["platform_post_id"] == "ig_delete_target"

    # Resolver should not return deleted post
    resolver = SharedPostContextResolver(db, container.settings)
    res = await resolver.resolve(workspace_id=ws_id, message_text="Temporary dessert weekend special")
    assert res is None


async def test_separate_ad_campaign_status_from_organic_post(db, container):
    """Verifies that stopping a paid campaign leaves the organic post published and searchable for DMs."""
    user_id = ObjectId()
    ws_id = "test_ws_ad_status"
    campaign_id = ObjectId()

    p = await social_knowledge.ingest_post(
        db, container, user_id=user_id, workspace_id=ws_id,
        platform="instagram", platform_post_id="ig_ad_organic_combo",
        title="Monsoon Raincoat Offer",
        caption="Waterproof Raincoats at ₹499 during the monsoon sale.",
        campaign_id=campaign_id,
        ad_campaign_status="active",
        auto_process=True,
    )
    post_id = p["id"]
    await social_knowledge.process_post_understanding(db, container, post_id)

    # Stop the paid campaign
    await db.social_posts.update_many(
        {"campaign_id": campaign_id},
        {"$set": {"ad_campaign_status": "stopped"}},
    )

    # Post must remain published and searchable
    post = await db.social_posts.find_one({"_id": ObjectId(post_id)})
    assert post["ad_campaign_status"] == "stopped"
    assert post["post_status"] == "published"

    resolver = SharedPostContextResolver(db, container.settings)
    resolved = await resolver.resolve(workspace_id=ws_id, message_text="Monsoon Raincoat Offer")
    assert resolved is not None
    assert resolved.post_id == post_id


async def test_multi_tenant_workspace_isolation(db, container):
    """Ensures knowledge retrieval strictly isolates between Workspace A and Workspace B."""
    user_a = ObjectId()
    user_b = ObjectId()
    ws_a = "workspace_alpha"
    ws_b = "workspace_beta"

    # Workspace A post
    await social_knowledge.ingest_post(
        db, container, user_id=user_a, workspace_id=ws_a,
        platform="instagram", platform_post_id="ig_alpha_secret",
        title="Alpha Luxury Watch",
        caption="Exclusive Swiss Chronograph Watch at ₹50000.",
        auto_process=True,
    )
    # Workspace B post
    await social_knowledge.ingest_post(
        db, container, user_id=user_b, workspace_id=ws_b,
        platform="instagram", platform_post_id="ig_beta_shoes",
        title="Beta Running Shoes",
        caption="Trail runner shoes at ₹2000.",
        auto_process=True,
    )

    resolver = SharedPostContextResolver(db, container.settings)

    # Search for Alpha post in Workspace B must return None
    res_in_b = await resolver.resolve(workspace_id=ws_b, message_text="Alpha Luxury Watch Swiss Chronograph")
    assert res_in_b is None

    # Search in Workspace A succeeds
    res_in_a = await resolver.resolve(workspace_id=ws_a, message_text="Alpha Luxury Watch Swiss Chronograph")
    assert res_in_a is not None
    assert "Alpha Luxury Watch" in res_in_a.title

