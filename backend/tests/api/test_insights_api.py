from tests.api.campaign_bodies import MANUAL
from tests.api_helpers import connect_fake_meta, login


async def ready_and_published(client, make_client):
    async with make_client(allow_real_ad_spend=True, safe_mode_no_spend=False) as c:
        await login(c)
        await connect_fake_meta(c)
        res = await c.post("/campaigns", json=MANUAL)
        campaign = res.json()
        await c.post(f"/campaigns/{campaign['id']}/image/generate", json={})
        await c.post(f"/campaigns/{campaign['id']}/publish", json={"confirm": True})
        await c.post(f"/campaigns/{campaign['id']}/activate", json={"confirm": True})
        return campaign["id"]


async def test_get_and_refresh_campaign_insights(make_client):
    async with make_client(allow_real_ad_spend=True, safe_mode_no_spend=False) as c:
        await login(c)
        await connect_fake_meta(c)
        res = await c.post("/campaigns", json=MANUAL)
        campaign_id = res.json()["id"]
        await c.post(f"/campaigns/{campaign_id}/image/generate", json={})
        await c.post(f"/campaigns/{campaign_id}/publish", json={"confirm": True})
        await c.post(f"/campaigns/{campaign_id}/activate", json={"confirm": True})

        # Initially before refresh, GET /campaigns/{id}/insights returns empty or null
        init_res = await c.get(f"/campaigns/{campaign_id}/insights")
        assert init_res.status_code == 200

        # Refresh
        ref_res = await c.post(f"/campaigns/{campaign_id}/insights/refresh")
        assert ref_res.status_code == 200, ref_res.text
        insights = ref_res.json()
        assert insights["impressions"] > 0
        assert insights["reach"] > 0
        assert insights["spend_minor"] > 0

        # Subsequent immediate refresh -> 429 RATE_LIMITED
        again_res = await c.post(f"/campaigns/{campaign_id}/insights/refresh")
        assert again_res.status_code == 429
        assert again_res.json()["error"]["code"] == "RATE_LIMITED"


async def test_get_meta_insights_sums_stored_insights(make_client, db):
    async with make_client(allow_real_ad_spend=True, safe_mode_no_spend=False) as c:
        await login(c)
        await connect_fake_meta(c)

        # Before any active campaign
        res_empty = await c.get("/meta/insights")
        assert res_empty.status_code == 200
        assert res_empty.json()["status"] == "NO_ACTIVE_SPEND"

        res = await c.post("/campaigns", json=MANUAL)
        campaign_id = res.json()["id"]
        await c.post(f"/campaigns/{campaign_id}/image/generate", json={})
        await c.post(f"/campaigns/{campaign_id}/publish", json={"confirm": True})
        await c.post(f"/campaigns/{campaign_id}/activate", json={"confirm": True})
        await c.post(f"/campaigns/{campaign_id}/insights/refresh")

        res_active = await c.get("/meta/insights")
        assert res_active.status_code == 200
        data = res_active.json()
        assert data["status"] == "ACTIVE"
        assert data["impressions"] > 0
        assert data["spend"] > 0.0


async def test_locations_search_requires_connection(client):
    await login(client)
    res = await client.get("/meta/locations?q=bangalore&country=IN")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "META_NOT_CONNECTED"


async def test_locations_search_returns_matches(client):
    await login(client)
    await connect_fake_meta(client)

    res = await client.get("/meta/locations?q=bangalore&country=IN")
    assert res.status_code == 200
    locations = res.json()
    assert len(locations) > 0
    assert any(loc["name"] == "Bangalore" for loc in locations)
    assert locations[0]["key"] == "1017930"
