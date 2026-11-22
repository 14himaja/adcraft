"""Integration tests for Image-to-Post Recognition and Selective RAG Architecture.

Verifies:
1. Ingestion of posts with perceptual image hashes & visual fingerprints.
2. Recognition of Instagram & Facebook post images in incoming customer DMs.
3. Handling images with no accompanying text (grounded post greeting).
4. Handling images with specific customer questions (RAG retrieval & answering).
5. Visual ambiguity handling when images are similar.
6. Unknown image fallback.
7. Multiple attachments handling.
8. Strict multi-tenant isolation (Workspace A vs Workspace B).
9. Selective RAG context scoping (only relevant product/chunks, no context bloat).
"""

import io
from PIL import Image, ImageDraw
import pytest
from bson import ObjectId

from app.services.image_matcher import (
    compute_image_fingerprint,
    compute_dhash,
)
from app.services.social_knowledge import ingest_post, process_post_understanding
from app.services.shared_post_resolver import SharedPostContextResolver
from app.services.hybrid_rag import HybridRAG
from app.services.dm import handle_messaging, get_config


def _generate_test_image(pattern: str, color: str) -> tuple[bytes, Image.Image]:
    im = Image.new("RGB", (200, 200), color="white")
    d = ImageDraw.Draw(im)
    if pattern == "smartwatch":
        d.rectangle([50, 50, 150, 150], fill=color)
        d.ellipse([70, 70, 130, 130], fill="black")
    elif pattern == "earbuds":
        d.ellipse([40, 40, 90, 90], fill=color)
        d.ellipse([110, 40, 160, 160], fill=color)
    elif pattern == "cake":
        d.polygon([(100, 20), (30, 170), (170, 170)], fill=color)
    else:
        d.rectangle([10, 10, 190, 190], fill=color)
    
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return buf.getvalue(), im


@pytest.fixture
def test_images():
    img1_bytes, img1_obj = _generate_test_image("smartwatch", "blue")
    img2_bytes, img2_obj = _generate_test_image("cake", "red")
    img3_bytes, img3_obj = _generate_test_image("earbuds", "green")
    return {
        "smartwatch": (img1_bytes, img1_obj),
        "cake": (img2_bytes, img2_obj),
        "earbuds": (img3_bytes, img3_obj),
    }


async def _setup_active_connection(db, user_id, workspace_id, ig_id="ig_12345", page_id="page_12345"):
    await db.users.update_one(
        {"_id": user_id},
        {"$set": {"active_workspace_id": workspace_id, "email": f"{user_id}@test.com"}},
        upsert=True,
    )
    await db.meta_connections.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "instagram_user_id": ig_id,
                "page_id": page_id,
                "status": "ACTIVE",
            }
        },
        upsert=True,
    )
    await db.dm_settings.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "enabled": True,
                "knowledge": "We offer fast nationwide delivery within 2-3 business days. 30-day return policy.",
                "handoff_message": "A team member will connect with you shortly.",
                "business_name": "Apex Electronics",
                "tone": "Helpful and friendly",
            }
        },
        upsert=True,
    )


@pytest.mark.asyncio
async def test_post_ingestion_with_image_fingerprint(db, container, test_images):
    user_id = ObjectId()
    ws_id = "ws_test_ingest"
    img_bytes, img_obj = test_images["smartwatch"]
    
    # Store image in GridFS
    from gridfs import AsyncGridFSBucket
    bucket = AsyncGridFSBucket(db, bucket_name="images")
    gridfs_id = str(await bucket.upload_from_stream("smartwatch.jpg", img_bytes))

    ingest_res = await ingest_post(
        db,
        container,
        user_id=user_id,
        workspace_id=ws_id,
        platform="instagram",
        platform_post_id="post_ig_smartwatch_01",
        title="Apex Pro Smartwatch",
        caption="Get the Apex Pro Smartwatch with Bluetooth calling for ₹2499! Special 20% discount until 2026-11-30.",
        media_reference=gridfs_id,
        source="adcraft",
        auto_process=False,
    )
    assert ingest_res["status"] == "INGESTED"

    # Process post understanding
    proc_res = await process_post_understanding(db, container, ingest_res["id"])
    assert proc_res["status"] == "READY"

    # Verify social_posts document has image_hash and image_fingerprint
    post_doc = await db.social_posts.find_one({"_id": ObjectId(ingest_res["id"])})
    assert post_doc is not None
    assert post_doc.get("image_hash") is not None
    assert post_doc.get("image_fingerprint") is not None
    assert post_doc["image_fingerprint"]["dhash"] == post_doc["image_hash"]

    # Verify knowledge_chunks has an image chunk
    img_chunk = await db.knowledge_chunks.find_one({
        "post_id": ingest_res["id"],
        "chunk_type": "image",
    })
    assert img_chunk is not None
    assert img_chunk["metadata"]["dhash"] == post_doc["image_hash"]


@pytest.mark.asyncio
async def test_instagram_and_facebook_image_match_in_dm(db, container, test_images):
    user_id = ObjectId()
    ws_id = "ws_test_social_match"
    ig_id, page_id = "ig_social_01", "page_social_01"
    await _setup_active_connection(db, user_id, ws_id, ig_id=ig_id, page_id=page_id)

    img_bytes, img_obj = test_images["smartwatch"]
    fp = compute_image_fingerprint(img_obj)

    # Ingest Instagram Post
    ig_post = await db.social_posts.insert_one({
        "workspace_id": ws_id,
        "user_id": user_id,
        "platform": "instagram",
        "platform_post_id": "ig_post_1001",
        "title": "Apex Smartwatch Series 5",
        "caption": "Apex Smartwatch Series 5 with BT Calling. Price ₹2999.",
        "image_hash": fp["dhash"],
        "image_fingerprint": fp,
        "post_status": "published",
        "created_at": container.clock.now(),
    })

    resolver = SharedPostContextResolver(db, container.settings, container=container)

    # Test 1: Customer shares Instagram image attachment with payload bytes
    resolved = await resolver.resolve(
        workspace_id=ws_id,
        message_text="How much is this?",
        attachments=[{"type": "image", "payload": {"image_bytes": img_bytes}}],
    )
    assert resolved is not None
    assert resolved.post_id == str(ig_post.inserted_id)
    assert resolved.match_method in ("image_hash", "visual_similarity")
    assert resolved.confidence >= 0.85

    # Test 2: Customer shares Facebook post image
    fb_img_bytes, fb_img_obj = test_images["cake"]
    fb_fp = compute_image_fingerprint(fb_img_obj)
    fb_post = await db.social_posts.insert_one({
        "workspace_id": ws_id,
        "user_id": user_id,
        "platform": "facebook",
        "platform_post_id": "fb_post_2002",
        "title": "Artisan Chocolate Cake",
        "caption": "Handcrafted Belgian dark chocolate cake for ₹899.",
        "image_hash": fb_fp["dhash"],
        "image_fingerprint": fb_fp,
        "post_status": "published",
        "created_at": container.clock.now(),
    })

    resolved_fb = await resolver.resolve(
        workspace_id=ws_id,
        message_text="Is this available?",
        attachments=[{"type": "image", "payload": {"image_bytes": fb_img_bytes}}],
    )
    assert resolved_fb is not None
    assert resolved_fb.post_id == str(fb_post.inserted_id)
    assert resolved_fb.title == "Artisan Chocolate Cake"


@pytest.mark.asyncio
async def test_image_with_no_accompanying_text(db, container, test_images):
    user_id = ObjectId()
    ws_id = "ws_test_no_text"
    ig_id, page_id = "ig_notext_01", "page_notext_01"
    await _setup_active_connection(db, user_id, ws_id, ig_id=ig_id, page_id=page_id)

    img_bytes, img_obj = test_images["smartwatch"]
    fp = compute_image_fingerprint(img_obj)

    # Insert post and offer
    post = await db.social_posts.insert_one({
        "workspace_id": ws_id,
        "user_id": user_id,
        "platform": "instagram",
        "platform_post_id": "ig_post_smartwatch",
        "title": "Titan Smartwatch",
        "caption": "Titan Smartwatch special launch! Only ₹2499 with 15% discount.",
        "image_hash": fp["dhash"],
        "image_fingerprint": fp,
        "post_status": "published",
        "created_at": container.clock.now(),
    })
    post_id = str(post.inserted_id)

    await db.offers.insert_one({
        "workspace_id": ws_id,
        "post_id": post_id,
        "user_id": user_id,
        "offer_description": "Launch Special",
        "price": 2499,
        "discount": "15%",
        "valid_until": "2026-12-31",
        "offer_status": "ACTIVE",
    })

    # Deliver webhook event with ONLY the image, no message text
    fake_gateway = container.gateway_for({"mode": "fake"})[1]
    fake_gateway.sent_dms.clear()

    webhook_event = {
        "sender": {"id": "customer_notext_123"},
        "recipient": {"id": page_id},
        "timestamp": int(container.clock.now().timestamp() * 1000),
        "message": {
            "mid": "mid_notext_001",
            "attachments": [{"type": "image", "payload": {"image_bytes": img_bytes}}],
        },
    }

    await handle_messaging(db, container, webhook_event)

    # Verify response was sent via fake gateway
    assert len(fake_gateway.sent_dms) == 1
    reply = fake_gateway.sent_dms[0]["text"]
    
    # Grounded answer should recognize Titan Smartwatch, ₹2499, and 15% discount
    assert "Titan Smartwatch" in reply
    assert "2499" in reply
    assert "15%" in reply


@pytest.mark.asyncio
async def test_image_with_customer_question(db, container, test_images):
    user_id = ObjectId()
    ws_id = "ws_test_img_question"
    ig_id, page_id = "ig_q_01", "page_q_01"
    await _setup_active_connection(db, user_id, ws_id, ig_id=ig_id, page_id=page_id)

    img_bytes, img_obj = test_images["cake"]
    fp = compute_image_fingerprint(img_obj)

    post = await db.social_posts.insert_one({
        "workspace_id": ws_id,
        "user_id": user_id,
        "platform": "instagram",
        "platform_post_id": "ig_cake_01",
        "title": "Belgian Chocolate Cake",
        "caption": "Handcrafted Belgian Chocolate Cake for ₹699. Valid until 2026-11-30.",
        "image_hash": fp["dhash"],
        "image_fingerprint": fp,
        "post_status": "published",
        "created_at": container.clock.now(),
    })
    post_id = str(post.inserted_id)

    await db.offers.insert_one({
        "workspace_id": ws_id,
        "post_id": post_id,
        "user_id": user_id,
        "offer_description": "Chocolate Special",
        "price": 699,
        "discount": "20% off",
        "valid_until": "2026-11-30",
        "offer_status": "ACTIVE",
    })

    fake_gateway = container.gateway_for({"mode": "fake"})[1]
    fake_gateway.sent_dms.clear()

    # Customer asks about the price with the shared image
    webhook_event = {
        "sender": {"id": "customer_q_456"},
        "recipient": {"id": page_id},
        "timestamp": int(container.clock.now().timestamp() * 1000),
        "message": {
            "mid": "mid_q_002",
            "text": "What is the price of this?",
            "attachments": [{"type": "image", "payload": {"image_bytes": img_bytes}}],
        },
    }

    await handle_messaging(db, container, webhook_event)

    assert len(fake_gateway.sent_dms) == 1
    reply = fake_gateway.sent_dms[0]["text"]
    assert "699" in reply


@pytest.mark.asyncio
async def test_visually_similar_different_image_and_ambiguity(db, container, test_images):
    user_id = ObjectId()
    ws_id = "ws_test_ambiguity"
    
    img_bytes, img_obj = test_images["smartwatch"]
    fp = compute_image_fingerprint(img_obj)

    # Insert two posts with almost identical image hash (simulating similar product variants)
    p1 = await db.social_posts.insert_one({
        "workspace_id": ws_id,
        "user_id": user_id,
        "platform": "instagram",
        "platform_post_id": "ig_var_01",
        "title": "Smartwatch Black Edition",
        "image_hash": fp["dhash"],
        "image_fingerprint": fp,
        "post_status": "published",
        "created_at": container.clock.now(),
    })
    p2 = await db.social_posts.insert_one({
        "workspace_id": ws_id,
        "user_id": user_id,
        "platform": "instagram",
        "platform_post_id": "ig_var_02",
        "title": "Smartwatch Silver Edition",
        "image_hash": fp["dhash"],  # Identical hash to trigger ambiguity
        "image_fingerprint": fp,
        "post_status": "published",
        "created_at": container.clock.now(),
    })

    resolver = SharedPostContextResolver(db, container.settings, container=container)
    resolved = await resolver.resolve(
        workspace_id=ws_id,
        message_text="How much is this?",
        attachments=[{"type": "image", "payload": {"image_bytes": img_bytes}}],
    )
    assert resolved is not None
    assert resolved.is_ambiguous is True
    assert resolved.candidate_titles is not None
    assert len(resolved.candidate_titles) >= 2
    assert "Smartwatch Black Edition" in resolved.candidate_titles
    assert "Smartwatch Silver Edition" in resolved.candidate_titles


@pytest.mark.asyncio
async def test_unknown_image_fallback(db, container):
    user_id = ObjectId()
    ws_id = "ws_test_unknown"
    ig_id, page_id = "ig_unk_01", "page_unk_01"
    await _setup_active_connection(db, user_id, ws_id, ig_id=ig_id, page_id=page_id)

    # Random unknown image
    random_bytes, _ = _generate_test_image("unknown_star", "magenta")

    fake_gateway = container.gateway_for({"mode": "fake"})[1]
    fake_gateway.sent_dms.clear()

    webhook_event = {
        "sender": {"id": "customer_unk_789"},
        "recipient": {"id": page_id},
        "timestamp": int(container.clock.now().timestamp() * 1000),
        "message": {
            "mid": "mid_unk_003",
            "attachments": [{"type": "image", "payload": {"image_bytes": random_bytes}}],
        },
    }

    await handle_messaging(db, container, webhook_event)

    assert len(fake_gateway.sent_dms) == 1
    reply = fake_gateway.sent_dms[0]["text"]
    assert "I can read text only. Please type your question." in reply

    # Verify thread was flagged for human
    thread = await db.dm_threads.find_one({"user_id": user_id, "customer_id": "customer_unk_789"})
    assert thread["status"] == "NEEDS_HUMAN"


@pytest.mark.asyncio
async def test_multi_tenant_isolation_for_images_and_rag(db, container, test_images):
    user_a = ObjectId()
    user_b = ObjectId()
    ws_a = "workspace_alpha"
    ws_b = "workspace_beta"

    await _setup_active_connection(db, user_a, ws_a, ig_id="ig_alpha", page_id="page_alpha")
    await _setup_active_connection(db, user_b, ws_b, ig_id="ig_beta", page_id="page_beta")

    img_bytes, img_obj = test_images["earbuds"]
    fp = compute_image_fingerprint(img_obj)

    # Post is ONLY published in Workspace A (Alpha)
    post_a = await db.social_posts.insert_one({
        "workspace_id": ws_a,
        "user_id": user_a,
        "platform": "instagram",
        "platform_post_id": "ig_alpha_earbuds",
        "title": "Alpha Wireless Earbuds",
        "caption": "Alpha exclusive earbuds for ₹1999.",
        "image_hash": fp["dhash"],
        "image_fingerprint": fp,
        "post_status": "published",
        "created_at": container.clock.now(),
    })

    resolver = SharedPostContextResolver(db, container.settings, container=container)

    # When query runs for Workspace A, it matches
    res_a = await resolver.resolve(
        workspace_id=ws_a,
        message_text="Details please",
        attachments=[{"type": "image", "payload": {"image_bytes": img_bytes}}],
    )
    assert res_a is not None
    assert res_a.post_id == str(post_a.inserted_id)

    # When query runs for Workspace B, it MUST NOT match Workspace A's post!
    res_b = await resolver.resolve(
        workspace_id=ws_b,
        message_text="Details please",
        attachments=[{"type": "image", "payload": {"image_bytes": img_bytes}}],
    )
    assert res_b is None

    # Hybrid RAG retrieval for Workspace B must never leak Workspace A's post
    rag = HybridRAG(db, container.settings)
    h_b = await rag.retrieve(
        workspace_id=ws_b,
        query="Alpha Wireless Earbuds",
        resolved_post_id=None,
    )
    assert "Alpha exclusive earbuds" not in h_b.prompt_context
    assert h_b.resolved_post is None


@pytest.mark.asyncio
async def test_selective_rag_scoping_and_context_size(db, container):
    """Verifies that HybridRAG selectively retrieves only relevant chunks and products,
    preventing context bloat when the knowledge base has multiple posts, offers, and FAQs."""
    user_id = ObjectId()
    ws_id = "ws_test_selective_rag"

    # Ingest 5 different posts with distinct products and FAQs
    p1 = await db.social_posts.insert_one({
        "workspace_id": ws_id,
        "user_id": user_id,
        "platform": "instagram",
        "platform_post_id": "p1_headphones",
        "title": "Noise Cancelling Headphones",
        "caption": "Noise Cancelling Headphones with 40hr battery for ₹4999.",
        "post_status": "published",
        "created_at": container.clock.now(),
    })
    p1_id = str(p1.inserted_id)

    # Products in workspace
    await db.products.insert_many([
        {"workspace_id": ws_id, "product_name": "Noise Cancelling Headphones", "price": 4999, "product_status": "active"},
        {"workspace_id": ws_id, "product_name": "Running Shoes", "price": 2999, "product_status": "active"},
        {"workspace_id": ws_id, "product_name": "Leather Wallet", "price": 799, "product_status": "active"},
        {"workspace_id": ws_id, "product_name": "Ceramic Coffee Mug", "price": 399, "product_status": "active"},
        {"workspace_id": ws_id, "product_name": "Yoga Mat", "price": 1299, "product_status": "active"},
    ])

    from app.services.embeddings import generate_embedding

    t_warranty = "Q: What is the warranty policy? A: We provide a 1-year replacement warranty on all electronics."
    t_shoe = "Q: Are running shoes washable? A: Hand wash only with mild soap."
    t_mug = "Q: Is the coffee mug microwave safe? A: Yes, it is 100% microwave safe."

    # Chunks for headphones post and general business knowledge
    await db.knowledge_chunks.insert_many([
        {
            "workspace_id": ws_id,
            "post_id": "general_policy_1",
            "chunk_type": "faq",
            "text": t_warranty,
            "embedding": await generate_embedding(t_warranty, container.settings),
            "is_active": True,
        },
        # Chunks for unrelated posts
        {
            "workspace_id": ws_id,
            "post_id": "other_post_1",
            "chunk_type": "faq",
            "text": t_shoe,
            "embedding": await generate_embedding(t_shoe, container.settings),
            "is_active": True,
        },
        {
            "workspace_id": ws_id,
            "post_id": "other_post_2",
            "chunk_type": "faq",
            "text": t_mug,
            "embedding": await generate_embedding(t_mug, container.settings),
            "is_active": True,
        },
    ])

    rag = HybridRAG(db, container.settings)
    h_context = await rag.retrieve(
        workspace_id=ws_id,
        user_id=user_id,
        query="warranty policy",
        resolved_post_id=p1_id,
        top_k=3,
    )

    # 1. Product selection is scoped to headphones, NOT all 5 products
    assert len(h_context.products) <= 2
    prod_names = [p["product_name"] for p in h_context.products]
    assert "Noise Cancelling Headphones" in prod_names
    assert "Running Shoes" not in prod_names
    assert "Ceramic Coffee Mug" not in prod_names

    # 2. Semantic chunks only contain relevant chunks, not coffee mug or running shoes
    assert len(h_context.semantic_chunks) <= 3
    retrieved_texts = [c["text"] for c in h_context.semantic_chunks]
    assert any("warranty" in t for t in retrieved_texts)

    # 3. Prompt context is compact and free of irrelevant products
    assert "Running Shoes" not in h_context.prompt_context
    assert "microwave safe" not in h_context.prompt_context
    assert len(h_context.prompt_context) < 2500  # Strictly bounded context
