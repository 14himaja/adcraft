"""API tests for Dynamic Social Knowledge Engine endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.auth import hash_password
from app.clock import utcnow
from app.main import create_app


@pytest.fixture
async def authed_client(db, container):
    """Client authenticated with a user having active_workspace_id."""
    user_doc = {
        "email": "owner@brand.com",
        "name": "Brand Owner",
        "workspace_name": "Brand Workspace",
        "active_workspace_id": "ws_brand_1",
        "password_hash": hash_password("ValidPassword123"),
        "created_at": utcnow(),
    }
    res = await db.users.insert_one(user_doc)
    user_id = str(res.inserted_id)

    app = create_app(container.settings, db=db, container=container)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        login_res = await c.post(
            "/auth/login",
            json={"email": "owner@brand.com", "password": "ValidPassword123"},
        )
        assert login_res.status_code == 200
        yield c, user_id


async def test_knowledge_api_ingest_process_patch_delete(authed_client, db):
    client, _ = authed_client

    # 1. Ingest
    res = await client.post(
        "/knowledge/posts/ingest",
        json={
            "platform": "instagram",
            "platform_post_id": "ig_api_post_1",
            "title": "Summer Smoothie Bowl",
            "caption": "Refreshing tropical smoothie bowl at ₹150! Valid until 2026-11-20.",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "INGESTED"
    post_id = data["id"]

    # 2. Get status
    status_res = await client.get("/knowledge/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["total_posts"] >= 1

    # 3. List posts
    list_res = await client.get("/knowledge/posts")
    assert list_res.status_code == 200
    posts = list_res.json()
    assert any(p["id"] == post_id for p in posts)

    # 4. Resolve shared post
    resolve_res = await client.post(
        "/knowledge/resolve-shared-post",
        json={"message_text": "Tell me about the Summer Smoothie Bowl"},
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["resolved"] is True
    assert resolve_res.json()["post"]["post_id"] == post_id

    # 5. Retrieve Hybrid context
    retrieve_res = await client.post(
        "/knowledge/retrieve",
        json={"query": "How much is the smoothie bowl?", "resolved_post_id": post_id},
    )
    assert retrieve_res.status_code == 200
    h_data = retrieve_res.json()
    assert "Smoothie Bowl" in h_data["prompt_context"]
    assert "₹150" in h_data["prompt_context"]

    # 6. Patch post
    patch_res = await client.patch(
        f"/knowledge/posts/{post_id}",
        json={"title": "Updated Super Smoothie Bowl"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "UPDATED"

    # 7. DM preview with post context
    preview_res = await client.post(
        "/dm/preview",
        json={"message": "What is the price of the smoothie bowl?", "post_id": post_id},
    )
    assert preview_res.status_code == 200
    assert "150" in preview_res.json()["reply"]

    # 8. Reconcile offers
    offer_sync_res = await client.post("/knowledge/offers/sync")
    assert offer_sync_res.status_code == 200
    assert "expired_count" in offer_sync_res.json()

    # 9. Delete post
    del_res = await client.delete(f"/knowledge/posts/{post_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "DELETED"

    # Verify status updated
    after_status = (await client.get("/knowledge/status")).json()
    assert after_status["deleted_posts"] >= 1

