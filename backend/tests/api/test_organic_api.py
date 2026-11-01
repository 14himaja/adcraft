import pytest
from bson import ObjectId

from app.meta.fake import parse_fail_at
from app.services import organic
from tests.api.test_ad_studio_api import png
from tests.api_helpers import connect_fake_meta, login

PUBLIC = "https://api.example.com"


@pytest.fixture
def make_post_client(make_client):
    return lambda **kw: make_client(public_base_url=PUBLIC, **kw)


async def new_image(client) -> str:
    response = await client.post("/organic/images/generate", json={"prompt": "A cake on a table"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def test_generated_image_is_posted_to_the_connected_account(
    make_post_client, fake_gateway, image_generator
):
    async with make_post_client() as c:
        await login(c)
        await connect_fake_meta(c)
        image_id = await new_image(c)
        response = await c.post("/organic/posts", json={"image_id": image_id, "caption": "Fresh bake!"})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "PUBLISHED" and response.json()["media_id"] == "fake_media_1"
        assert [p["status"] for p in (await c.get("/organic/posts")).json()] == ["PUBLISHED"]
    [post] = fake_gateway.published_posts
    assert post["ig_user_id"] == "ig_fake_1" and post["caption"] == "Fresh bake!"
    assert post["image_url"].startswith(f"{PUBLIC}/public/images/{image_id}?sig=")
    assert "A cake on a table" in image_generator.prompts[0] and fake_gateway.objects == {}  # no ads touched


async def test_instagram_can_fetch_the_image_only_with_the_signature(make_post_client, fake_gateway):
    async with make_post_client() as c:
        await login(c)
        await connect_fake_meta(c)
        await c.post("/organic/posts", json={"image_id": await new_image(c), "caption": ""})
        url = fake_gateway.published_posts[0]["image_url"].removeprefix(PUBLIC)
        await c.post("/auth/logout")  # Instagram has no session
        fetched = await c.get(url)
        fetched_ext = await c.get(url.replace("?", ".jpg?"))
        forged = await c.get(url.split("sig=")[0] + "sig=" + "0" * 32)
        missing = await c.get(f"/public/images/{ObjectId()}?sig={'0' * 32}")
    assert (fetched.status_code, fetched.headers["content-type"]) == (200, "image/jpeg")
    assert (fetched_ext.status_code, fetched_ext.headers["content-type"]) == (200, "image/jpeg")
    assert fetched.content[:2] == b"\xff\xd8"
    assert (forged.status_code, missing.status_code) == (404, 404)


async def test_uploaded_png_is_converted_to_jpeg_and_bad_files_are_rejected(make_post_client):
    async with make_post_client() as c:
        await login(c)
        ok = await c.post("/organic/images", files={"file": ("a.png", png(1080, 1350), "image/png")})
        assert ok.status_code == 200, ok.text
        tiny = await c.post("/organic/images", files={"file": ("a.png", png(100, 100), "image/png")})
        junk = await c.post("/organic/images", files={"file": ("a.png", b"not an image", "image/png")})
    assert (tiny.status_code, junk.status_code) == (422, 422)


async def test_posting_needs_public_base_url_and_a_connected_account(make_client, make_post_client):
    async with make_post_client() as c:
        await login(c)
        no_meta = await c.post("/organic/posts", json={"image_id": "x", "caption": ""})
        assert (no_meta.status_code, no_meta.json()["error"]["code"]) == (409, "META_NOT_CONNECTED")
    async with make_client() as c:  # no PUBLIC_BASE_URL
        await login(c)
        await connect_fake_meta(c)
        response = await c.post("/organic/posts", json={"image_id": await new_image(c), "caption": ""})
    assert (response.status_code, response.json()["error"]["code"]) == (409, "ORGANIC_PUBLISH_NOT_READY")


async def test_real_instagram_posting_needs_the_server_switch(make_post_client, fake_gateway, db):
    async with make_post_client() as c:
        await login(c)
        await connect_fake_meta(c)
        image_id = await new_image(c)
        await db.meta_connections.update_many({}, {"$set": {"mode": "real"}})
        blocked = await c.post("/organic/posts", json={"image_id": image_id, "caption": ""})
    assert (blocked.status_code, blocked.json()["error"]["code"]) == (409, "ORGANIC_PUBLISH_NOT_READY")
    assert fake_gateway.published_posts == []
    async with make_post_client(allow_organic_publish=True) as c:
        await login(c)
        allowed = await c.post("/organic/posts", json={"image_id": image_id, "caption": ""})
    assert allowed.status_code == 200 and len(fake_gateway.published_posts) == 1


async def test_cannot_post_somebody_elses_image(make_post_client, fake_gateway):
    async with make_post_client() as c:
        await login(c, email="a@example.com")
        image_id = await new_image(c)
        await c.post("/auth/logout")
        await login(c, email="b@example.com")
        await connect_fake_meta(c)
        response = await c.post("/organic/posts", json={"image_id": image_id, "caption": ""})
    assert response.status_code == 404 and fake_gateway.published_posts == []


async def test_instagram_rejection_is_recorded_and_reported(make_post_client, fake_gateway):
    fake_gateway.fail_at.update(parse_fail_at("POST:100"))
    async with make_post_client() as c:
        await login(c)
        await connect_fake_meta(c)
        response = await c.post("/organic/posts", json={"image_id": await new_image(c), "caption": "hi"})
        listed = (await c.get("/organic/posts")).json()
    assert (response.status_code, response.json()["error"]["code"]) == (502, "INSTAGRAM_POST_FAILED")
    assert [p["status"] for p in listed] == ["FAILED"]


@pytest.fixture
def second_account(monkeypatch):
    """The fake login also manages a second Page that has its own Instagram account."""
    from app.meta import fake

    monkeypatch.setitem(fake.FAKE_INSTAGRAM, "page_fake_2", {"id": "ig_fake_2", "username": "second_brand"})


async def test_account_list_shows_usable_accounts_and_why_a_page_is_missing(make_post_client):
    async with make_post_client() as c:
        await login(c)
        await connect_fake_meta(c)
        listed = (await c.get("/organic/accounts")).json()
    assert listed["default"] == "ig_fake_1"
    accounts = [(a["instagram_user_id"], a["username"]) for a in listed["accounts"]]
    assert ("ig_fake_1", "fake_brand") in accounts
    assert listed["unavailable"] == [
        {"page_id": "page_fake_2", "page_name": "Page Without Instagram", "reason": organic.NO_INSTAGRAM}
    ]


async def test_post_to_another_account_the_login_manages(make_post_client, fake_gateway, second_account):
    async with make_post_client() as c:
        await login(c)
        await connect_fake_meta(c)
        image_id = await new_image(c)
        body = {"image_id": image_id, "caption": "Hi", "instagram_user_id": "ig_fake_2"}
        response = await c.post("/organic/posts", json=body)
        assert response.status_code == 200, response.text
    assert [p["ig_user_id"] for p in fake_gateway.published_posts] == ["ig_fake_2"]


async def test_cannot_post_to_an_account_the_login_does_not_manage(make_post_client, fake_gateway):
    async with make_post_client() as c:
        await login(c)
        await connect_fake_meta(c)
        body = {"image_id": await new_image(c), "caption": "", "instagram_user_id": "ig_not_mine"}
        response = await c.post("/organic/posts", json=body)
    assert (response.status_code, response.json()["error"]["code"]) == (422, "INSTAGRAM_ACCOUNT_UNAVAILABLE")
    assert fake_gateway.published_posts == []


async def test_posting_needs_no_ad_account_but_a_chosen_instagram_account(make_post_client, fake_gateway):
    async with make_post_client() as c:
        await login(c)
        assert (await c.get("/meta/connect")).status_code == 302  # connected, nothing selected
        image_id = await new_image(c)
        none_chosen = await c.post("/organic/posts", json={"image_id": image_id, "caption": ""})
        chosen = await c.post(
            "/organic/posts", json={"image_id": image_id, "caption": "", "instagram_user_id": "ig_fake_1"}
        )
    code = none_chosen.json()["error"]["code"]
    assert (none_chosen.status_code, code) == (409, "ORGANIC_PUBLISH_NOT_READY")
    assert chosen.status_code == 200 and len(fake_gateway.published_posts) == 1


async def campaign_with_image(client) -> str:
    from tests.api.campaign_bodies import MANUAL

    campaign = (await client.post("/campaigns", json=MANUAL)).json()
    image_id = await new_image(client)
    attached = await client.put(f"/campaigns/{campaign['id']}/image", json={"image_id": image_id})
    assert attached.status_code == 200, attached.text
    return campaign["id"]


async def test_ad_is_posted_to_exactly_the_chosen_targets(make_post_client, fake_gateway):
    async with make_post_client() as c:
        await login(c)
        await connect_fake_meta(c)
        campaign_id = await campaign_with_image(c)
        only_one = await c.post(f"/campaigns/{campaign_id}/post", json={"targets": ["instagram_story"]})
        assert only_one.status_code == 200, only_one.text
        assert fake_gateway.facebook_posts == []
        assert [p.get("story") for p in fake_gateway.published_posts] == [True]
        all_four = ["facebook_feed", "facebook_story", "instagram_feed", "instagram_story"]
        done = await c.post(f"/campaigns/{campaign_id}/post", json={"targets": all_four})
        campaign = (await c.get(f"/campaigns/{campaign_id}")).json()
    assert {t: r["status"] for t, r in done.json()["results"].items()} == dict.fromkeys(all_four, "PUBLISHED")
    # a feed post carries the ad text; a story has no caption
    assert [(p["story"], "Learn Python" in p["caption"]) for p in fake_gateway.facebook_posts] == [
        (False, True), (True, False)
    ]
    assert set(campaign["posted"]) == set(all_four)


async def test_one_failing_target_does_not_stop_the_others_and_is_not_marked_posted(
    make_post_client, fake_gateway
):
    from app.meta.errors import MetaError

    async def refused(*_a, **_k):
        raise MetaError(meta_code=200, message="(#200) requires pages_manage_posts")

    fake_gateway.publish_facebook_photo = refused
    async with make_post_client() as c:
        await login(c)
        await connect_fake_meta(c)
        campaign_id = await campaign_with_image(c)
        response = await c.post(
            f"/campaigns/{campaign_id}/post", json={"targets": ["facebook_feed", "instagram_feed"]}
        )
        campaign = (await c.get(f"/campaigns/{campaign_id}")).json()
    results = response.json()["results"]
    assert results["instagram_feed"]["status"] == "PUBLISHED"
    assert results["facebook_feed"]["status"] == "FAILED"
    assert "pages_manage_posts" in results["facebook_feed"]["error"]
    assert set(campaign["posted"]) == {"instagram_feed"}


async def test_posting_an_ad_needs_an_image_and_known_targets(make_post_client):
    from tests.api.campaign_bodies import MANUAL

    async with make_post_client() as c:
        await login(c)
        await connect_fake_meta(c)
        bare = (await c.post("/campaigns", json=MANUAL)).json()["id"]
        no_image = await c.post(f"/campaigns/{bare}/post", json={"targets": ["instagram_feed"]})
        with_image = await campaign_with_image(c)
        unknown = await c.post(f"/campaigns/{with_image}/post", json={"targets": ["tiktok_feed"]})
    assert (no_image.status_code, no_image.json()["error"]["code"]) == (409, "ORGANIC_PUBLISH_NOT_READY")
    assert unknown.status_code == 422


async def test_delete_organic_post(make_post_client):
    async with make_post_client() as c:
        await login(c)
        await connect_fake_meta(c)
        image_id = await new_image(c)
        created = (await c.post("/organic/posts", json={"image_id": image_id, "caption": "To delete"})).json()
        assert len((await c.get("/organic/posts")).json()) == 1

        deleted = await c.delete(f"/organic/posts/{created['id']}")
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["status"] == "DELETED"
        assert len((await c.get("/organic/posts")).json()) == 0

        # deleting again returns 404
        not_found = await c.delete(f"/organic/posts/{created['id']}")
        assert not_found.status_code == 404


async def test_organic_and_campaign_publishing_with_hashtags(make_post_client, fake_gateway):
    async with make_post_client() as c:
        await login(c)
        await connect_fake_meta(c)
        image_id = await new_image(c)

        # 1. Standalone organic post with selected hashtags
        post_res = await c.post(
            "/organic/posts",
            json={
                "image_id": image_id,
                "caption": "Check out our organic post!",
                "selected_hashtags": ["#SmallBusiness", "#Trending", "#Growth"],
            },
        )
        assert post_res.status_code == 200, post_res.text
        published = fake_gateway.published_posts[-1]
        assert "Check out our organic post!" in published["caption"]
        assert "#SmallBusiness #Trending #Growth" in published["caption"]

        # 2. Campaign post with selected hashtags
        campaign_id = await campaign_with_image(c)
        await c.put(
            f"/campaigns/{campaign_id}",
            json={"selected_hashtags": ["#TechInnovation", "#StartupLife"]},
        )
        await c.post(
            f"/campaigns/{campaign_id}/post",
            json={"targets": ["facebook_feed", "facebook_story", "instagram_feed", "instagram_story"]},
        )

        fb_feed = [p for p in fake_gateway.facebook_posts if not p["story"]][-1]
        fb_story = [p for p in fake_gateway.facebook_posts if p["story"]][-1]
        ig_feed = [p for p in fake_gateway.published_posts if not p.get("story")][-1]
        ig_story = [p for p in fake_gateway.published_posts if p.get("story")][-1]

        # Feeds receive the hashtags appended
        assert "#TechInnovation #StartupLife" in fb_feed["caption"]
        assert "#TechInnovation #StartupLife" in ig_feed["caption"]
        # Stories do not have feed captions or hashtags attached
        assert fb_story["caption"] == ""


