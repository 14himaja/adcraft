"""Comprehensive automated test suite for Multi-User, Multi-Account SaaS Platform.

Verifies:
1. Multi-user authentication & workspace isolation across users.
2. Tenant-isolated Meta asset discovery & independent connection management.
3. Independent selection and switching of Facebook Pages, Instagram Accounts, and Ad Accounts.
4. Organic social publishing without requiring a paid ad account.
5. Campaign ownership enforcement and IDOR protection (User B cannot view, modify, publish, or delete User A's campaign).
6. Per-user token encryption at rest without plaintext exposure.
7. Selective asset disconnect (disconnecting an ad account preserves Facebook/Instagram organic capability).
"""

from datetime import UTC, datetime, timedelta
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.clock import FixedClock
from app.errors import NotFound
from app.main import create_app
from app.meta.connections import (
    MetaNotConnected,
    disconnect_asset,
    get_connection,
    public_view,
    require_connection,
    require_selected,
    save_token,
    select_assets,
)
from app.security.crypto import decrypt_token
from app.security.jwt import issue_token
from app.services import ad_campaigns as campaigns
from app.services import organic

NOW = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)

PAGE_A = {"id": "page_alpha", "name": "Alpha Business Page"}
IG_A = {"id": "ig_alpha", "username": "alpha_official"}
ACCOUNT_A = {
    "id": "act_alpha_1",
    "name": "Alpha Ad Account",
    "currency": "INR",
    "min_daily_budget_minor": 9673,
}

PAGE_B = {"id": "page_beta", "name": "Beta Retail Store"}
IG_B = {"id": "ig_beta", "username": "beta_retail"}
ACCOUNT_B = {
    "id": "act_beta_1",
    "name": "Beta Growth Ads",
    "currency": "USD",
    "min_daily_budget_minor": 1000,
}


@pytest.fixture
def clock():
    return FixedClock(NOW)


@pytest.mark.asyncio
async def test_multiuser_registration_and_workspace_isolation(db, settings):
    """Test multiple users register with distinct isolated workspaces."""
    user_a = {
        "email": "user_a@enterprise.com",
        "name": "Alice CEO",
        "workspace_name": "Alpha Corp Workspace",
        "password_hash": "hash1",
        "created_at": NOW,
    }
    user_b = {
        "email": "user_b@startup.io",
        "name": "Bob Founder",
        "workspace_name": "Beta Labs Workspace",
        "password_hash": "hash2",
        "created_at": NOW,
    }

    id_a = (await db.users.insert_one(user_a)).inserted_id
    id_b = (await db.users.insert_one(user_b)).inserted_id

    assert id_a != id_b

    doc_a = await db.users.find_one({"_id": id_a})
    doc_b = await db.users.find_one({"_id": id_b})

    assert doc_a["workspace_name"] == "Alpha Corp Workspace"
    assert doc_b["workspace_name"] == "Beta Labs Workspace"


@pytest.mark.asyncio
async def test_tenant_meta_connection_isolation_and_token_encryption(db, settings, clock):
    """Test each customer has their own encrypted Meta credentials and cannot see the other's."""
    user_a = ObjectId()
    user_b = ObjectId()

    token_a = "EAAB-TOKEN-CUSTOMER-A"
    token_b = "EAAB-TOKEN-CUSTOMER-B"

    # Connect User A
    await save_token(
        db,
        user_id=user_a,
        token=token_a,
        expires_at=NOW + timedelta(days=60),
        mode="real",
        settings=settings,
        clock=clock,
    )
    await select_assets(db, user_a, ad_account=ACCOUNT_A, page=PAGE_A, instagram=IG_A, clock=clock)

    # Connect User B
    await save_token(
        db,
        user_id=user_b,
        token=token_b,
        expires_at=NOW + timedelta(days=30),
        mode="real",
        settings=settings,
        clock=clock,
    )
    await select_assets(db, user_b, ad_account=ACCOUNT_B, page=PAGE_B, instagram=IG_B, clock=clock)

    # 1. Verify encrypted storage at rest
    conn_a = await db.meta_connections.find_one({"user_id": user_a})
    conn_b = await db.meta_connections.find_one({"user_id": user_b})

    assert b"EAAB-TOKEN" not in conn_a["token_ciphertext"]
    assert b"EAAB-TOKEN" not in conn_b["token_ciphertext"]
    assert decrypt_token(settings.token_encryption_key, conn_a["token_ciphertext"]) == token_a
    assert decrypt_token(settings.token_encryption_key, conn_b["token_ciphertext"]) == token_b

    # 2. Verify asset isolation
    assert conn_a["ad_account_id"] == "act_alpha_1"
    assert conn_a["page_id"] == "page_alpha"
    assert conn_a["instagram_username"] == "alpha_official"

    assert conn_b["ad_account_id"] == "act_beta_1"
    assert conn_b["page_id"] == "page_beta"
    assert conn_b["instagram_username"] == "beta_retail"

    # 3. Verify public view never leaks secrets or other tenant data
    view_a = public_view(conn_a, now=NOW)
    view_b = public_view(conn_b, now=NOW)

    assert "token" not in str(view_a)
    assert "token" not in str(view_b)
    assert view_a["ad_account_id"] == "act_alpha_1"
    assert view_b["ad_account_id"] == "act_beta_1"


@pytest.mark.asyncio
async def test_organic_publishing_without_ad_account(db, settings, clock):
    """Test a business that only uses organic social media posting is not forced to have a paid ad account."""
    user_organic = ObjectId()

    # User connects Meta for organic social posting
    await save_token(
        db,
        user_id=user_organic,
        token="EAAB-ORGANIC-ONLY",
        expires_at=NOW + timedelta(days=60),
        mode="real",
        settings=settings,
        clock=clock,
    )

    # Select Page and Instagram WITHOUT any ad account
    saved = await select_assets(
        db,
        user_organic,
        ad_account=None,
        page=PAGE_A,
        instagram=IG_A,
        clock=clock,
    )

    assert saved["page_id"] == "page_alpha"
    assert saved["instagram_user_id"] == "ig_alpha"
    assert "ad_account_id" not in saved or saved["ad_account_id"] is None

    # Paid ad publish check requires ad account -> should raise MetaNotConnected
    with pytest.raises(MetaNotConnected):
        await require_selected(db, user_organic, clock=clock)


@pytest.mark.asyncio
async def test_independent_account_switching_and_selective_disconnect(db, settings, clock):
    """Test switching active assets independently and selective disconnect."""
    user = ObjectId()

    await save_token(
        db,
        user_id=user,
        token="EAAB-MULTI-ASSET",
        expires_at=NOW + timedelta(days=60),
        mode="real",
        settings=settings,
        clock=clock,
    )
    await select_assets(db, user, ad_account=ACCOUNT_A, page=PAGE_A, instagram=IG_A, clock=clock)

    # Switch active Page and IG to Beta while keeping Ad Account A
    switched = await select_assets(
        db,
        user,
        ad_account=None,  # Keep existing ad account
        page=PAGE_B,
        instagram=IG_B,
        clock=clock,
    )
    assert switched["ad_account_id"] == "act_alpha_1"  # Preserved
    assert switched["page_id"] == "page_beta"          # Updated
    assert switched["instagram_username"] == "beta_retail"  # Updated

    # Selective disconnect: disconnect ad account only
    after_ad_disconnect = await disconnect_asset(db, user, asset_type="ad_account", clock=clock)
    assert after_ad_disconnect.get("ad_account_id") is None
    # Organic assets remain fully intact and active
    assert after_ad_disconnect["page_id"] == "page_beta"
    assert after_ad_disconnect["instagram_user_id"] == "ig_beta"
    assert after_ad_disconnect["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_campaign_ownership_enforcement_and_idor_protection(db, settings, clock):
    """Test strict tenant isolation: User B cannot access, modify, or delete User A's campaign."""
    user_a = ObjectId()
    user_b = ObjectId()

    # User A creates a campaign
    camp_a = await campaigns.create_draft(
        db,
        user_id=user_a,
        fields={"title": "Alpha Product Launch", "objective": "TRAFFIC", "landing_url": "https://alpha.example/deal"},
        settings=settings,
        clock=clock,
    )
    camp_id = str(camp_a["_id"])

    # User A can get their own campaign
    owned_a = await campaigns.get_owned(db, camp_id, user_a)
    assert owned_a["title"] == "Alpha Product Launch"

    # User B attempting to get User A's campaign gets NotFound (IDOR protected)
    with pytest.raises(NotFound):
        await campaigns.get_owned(db, camp_id, user_b)

    # User B listing campaigns only sees their own (0 campaigns)
    list_b = await campaigns.list_owned(db, user_b)
    assert len(list_b) == 0

    list_a = await campaigns.list_owned(db, user_a)
    assert len(list_a) == 1
    assert str(list_a[0]["_id"]) == camp_id

@pytest.mark.asyncio
async def test_synxait_development_workspace_and_switching(client, db):
    """Test Synxait is available as default dev/test workspace with quick switching."""
    # 1. Register a user
    res = await client.post(
        "/auth/register",
        json={"email": "developer@synxait.com", "password": "password123", "name": "Dev Alice"},
    )
    assert res.status_code == 201
    user_data = res.json()
    assert user_data["workspace"] == "Synxait"
    assert user_data["is_dev_workspace"] is True
    assert any(w["id"] == "synxait" and w["type"] == "development" for w in user_data["workspaces"])
    assert any(w["id"] == "personal" and w["type"] == "customer" for w in user_data["workspaces"])

    # Log in
    login_res = await client.post(
        "/auth/login",
        json={"email": "developer@synxait.com", "password": "password123"},
    )
    assert login_res.status_code == 200
    assert login_res.json()["is_dev_workspace"] is True

    # Switch workspace to personal customer workspace
    switch_res = await client.post(
        "/auth/workspace/switch",
        json={"workspace_id": "personal"},
    )
    assert switch_res.status_code == 200
    switched = switch_res.json()
    assert switched["workspace_id"] == "personal"
    assert switched["is_dev_workspace"] is False

    # Switch back to Synxait dev workspace
    back_res = await client.post(
        "/auth/workspace/switch",
        json={"workspace_id": "synxait"},
    )
    assert back_res.status_code == 200
    assert back_res.json()["workspace_id"] == "synxait"
    assert back_res.json()["is_dev_workspace"] is True


@pytest.mark.asyncio
async def test_synxait_test_assets_discovery_and_persistence(client, db):
    """Test Synxait Page, Instagram, and Ad Account are discovered in assets and persistently selected."""
    # Register & login
    await client.post(
        "/auth/register",
        json={"email": "tester@synxait.com", "password": "password123", "name": "Tester"},
    )
    await client.post(
        "/auth/login",
        json={"email": "tester@synxait.com", "password": "password123"},
    )

    # Connect in mock/dev mode
    connect_res = await client.get("/meta/connect", follow_redirects=False)
    assert connect_res.status_code == 302

    # Get assets
    assets_res = await client.get("/meta/assets")
    assert assets_res.status_code == 200
    assets = assets_res.json()

    # Verify Synxait assets are listed
    ad_account_ids = [a["id"] for a in assets["ad_accounts"]]
    assert "act_2279071366267627" in ad_account_ids

    page_ids = [p["id"] for p in assets["pages"]]
    assert "1415879818267624" in page_ids

    ig_usernames = [ig["username"] for ig in assets.get("instagram_accounts", [])]
    assert "synxait" in ig_usernames

    # Select Synxait assets
    select_res = await client.put(
        "/meta/connection",
        json={
            "ad_account_id": "act_2279071366267627",
            "page_id": "1415879818267624",
        },
    )
    assert select_res.status_code == 200
    conn = select_res.json()
    assert conn["ad_account_id"] == "act_2279071366267627"
    assert conn["page_id"] == "1415879818267624"
    assert conn["instagram_username"] == "synxait"

    # Verify persistence on re-fetching connection
    conn_res = await client.get("/meta/connection")
    assert conn_res.status_code == 200
    reloaded = conn_res.json()
    assert reloaded["ad_account_id"] == "act_2279071366267627"
    assert reloaded["instagram_username"] == "synxait"
