from io import BytesIO

from bson import ObjectId
from PIL import Image

from tests.api.campaign_bodies import MANUAL
from tests.api_helpers import login


def image_bytes(width: int, height: int, fmt: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "orange").save(buffer, format=fmt)
    return buffer.getvalue()


async def new_campaign(client, **overrides) -> dict:
    response = await client.post("/campaigns", json={**MANUAL, **overrides})
    assert response.status_code == 200, response.text
    return response.json()


def image_path(campaign: dict) -> str:
    return campaign["image_url"].removeprefix("/api/v1")


async def upload(client, campaign_id: str, data: bytes, name: str = "ad.png"):
    return await client.post(f"/campaigns/{campaign_id}/image", files={"file": (name, data, "image/png")})


async def test_generate_stores_a_square_jpeg_and_links_it(client, image_generator, db):
    await login(client)
    campaign = await new_campaign(client)
    await db.campaigns.update_one(
        {"_id": ObjectId(campaign["id"])}, {"$set": {"image_prompt": "A student coding"}}
    )
    response = await client.post(f"/campaigns/{campaign['id']}/image/generate", json={"prompt": "warm light"})
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["image_id"] and updated["missing_fields"] == [] and updated["can_publish"] is True
    assert image_generator.prompts == [
        "A student coding warm light "
        "Square 1:1 Instagram ad creative; quoted text exactly once, no other text or watermarks."
    ]
    image = await client.get(image_path(updated))
    assert (image.status_code, image.headers["content-type"]) == (200, "image/jpeg")
    with Image.open(BytesIO(image.content)) as img:
        assert img.size == (1080, 1080)


async def test_generate_failure_is_reported_and_campaign_unchanged(client, image_generator):
    await login(client)
    campaign = await new_campaign(client)
    image_generator.fail = True
    response = await client.post(f"/campaigns/{campaign['id']}/image/generate", json={})
    assert (response.status_code, response.json()["error"]["code"]) == (502, "IMAGE_GENERATION_FAILED")
    assert (await client.get(f"/campaigns/{campaign['id']}")).json()["image_id"] is None


async def test_images_can_only_change_on_a_draft(client, db, image_generator):
    await login(client)
    campaign = await new_campaign(client)
    await db.campaigns.update_one({"_id": ObjectId(campaign["id"])}, {"$set": {"status": "ACTIVE"}})
    response = await client.post(f"/campaigns/{campaign['id']}/image/generate", json={})
    assert (response.status_code, response.json()["error"]["code"]) == (409, "ILLEGAL_TRANSITION")
    assert image_generator.prompts == []  # no wasted model call


async def test_upload_converts_a_4_5_png_to_square_jpeg(client):
    await login(client)
    campaign = await new_campaign(client)
    response = await upload(client, campaign["id"], image_bytes(1080, 1350))
    assert response.status_code == 200, response.text
    image = await client.get(image_path(response.json()))
    assert image.headers["content-type"] == "image/jpeg"
    with Image.open(BytesIO(image.content)) as decoded:
        assert decoded.format == "JPEG" and decoded.size == (1080, 1080)


async def test_upload_converts_a_non_square_jpeg_and_rejects_a_small_image(client):
    await login(client)
    campaign = await new_campaign(client)
    uploaded = await upload(client, campaign["id"], image_bytes(1080, 1350, fmt="JPEG"), name="photo.jpeg")
    assert uploaded.status_code == 200
    image = await client.get(image_path(uploaded.json()))
    with Image.open(BytesIO(image.content)) as decoded:
        assert decoded.format == "JPEG" and decoded.size == (1080, 1080)
    small = await upload(client, campaign["id"], image_bytes(200, 200), name="small.png")
    assert small.status_code == 422
    assert "at least 600 px wide" in small.json()["error"]["message"]


async def test_story_shaped_upload_is_rejected_with_the_ratio_message(client):
    await login(client)
    campaign = await new_campaign(client)
    response = await upload(client, campaign["id"], image_bytes(1080, 1920))
    error = response.json()["error"]
    assert (response.status_code, error["code"]) == (422, "IMAGE_REJECTED")
    assert "1:1 or 4:5 is recommended" in error["message"]
    bad = await upload(client, campaign["id"], b"plain text", name="notes.txt")
    assert bad.json()["error"]["message"] == "File is not a valid image"


async def test_images_are_private_to_their_owner(client):
    await login(client)
    campaign = await new_campaign(client)
    uploaded = (await upload(client, campaign["id"], image_bytes(1080, 1080))).json()
    await login(client, "other@example.com")
    response = await client.get(image_path(uploaded))
    assert (response.status_code, response.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert (await client.get("/images/not-an-id")).status_code == 404
    assert (await client.get("/media")).json() == []


async def test_image_route_requires_a_session(client, make_client):
    await login(client)
    campaign = await new_campaign(client)
    image = (await upload(client, campaign["id"], image_bytes(1080, 1080))).json()
    async with make_client() as anonymous:
        response = await anonymous.get(image_path(image))
    assert response.status_code == 401


async def test_deleting_a_duplicate_does_not_delete_original_meta_or_image(client, db):
    await login(client)
    source = await new_campaign(client)
    generated = await client.post(f"/campaigns/{source['id']}/image/generate", json={})
    assert generated.status_code == 200
    await client.put(f"/campaigns/{source['id']}", json={"title": "Source with shared image"})
    await db.campaigns.update_one(
        {"_id": ObjectId(source["id"])},
        {"$set": {"status": "ACTIVE", "meta": {"campaign_id": "meta-original"}}},
    )
    copied = await client.post(f"/campaigns/{source['id']}/duplicate")
    assert copied.status_code == 200 and copied.json()["image_id"] == generated.json()["image_id"]
    copy_id = copied.json()["id"]
    await client.delete(f"/campaigns/{copy_id}")
    source_after_copy_delete = await db.campaigns.find_one({"_id": ObjectId(source["id"])})
    assert source_after_copy_delete["meta"]["campaign_id"] == "meta-original"
    assert (await client.get(image_path(generated.json()))).status_code == 200

    still_there = await client.get(f"/images/{generated.json()['image_id']}")
    assert still_there.status_code == 200


async def test_deleting_campaign_keeps_image_shared_with_another_campaign(client, db):
    await login(client)
    source = await new_campaign(client)
    generated = await client.post(f"/campaigns/{source['id']}/image/generate", json={})
    await db.campaigns.update_one({"_id": ObjectId(source["id"])}, {"$set": {"status": "ACTIVE"}})
    copied = await client.post(f"/campaigns/{source['id']}/duplicate")
    assert copied.status_code == 200
    await client.delete(f"/campaigns/{source['id']}")
    assert (await client.get(image_path(copied.json()))).status_code == 200
    copied_campaign = await client.get(f"/campaigns/{copied.json()['id']}")
    assert copied_campaign.json()["image_id"] == generated.json()["image_id"]


async def test_media_library_lists_my_images_and_can_reuse_one(client):
    await login(client)
    first = await new_campaign(client)
    generated = (await client.post(f"/campaigns/{first['id']}/image/generate", json={})).json()
    await upload(client, first["id"], image_bytes(1080, 1080), name="mine.png")
    media = (await client.get("/media")).json()
    assert [(m["source"], m["filename"]) for m in media] == [
        ("uploaded", "mine.jpg"),
        ("generated", f"generated-{first['id']}.jpg"),
    ]
    assert media[1]["prompt"].endswith("no other text or watermarks.") and media[1]["created_at"]
    assert media[1]["source_campaign"] == first["title"]
    second = await new_campaign(client)
    response = await client.put(f"/campaigns/{second['id']}/image", json={"image_id": generated["image_id"]})
    assert (response.status_code, response.json()["image_id"]) == (200, generated["image_id"])
    assert (await client.delete(f"/media/{generated['image_id']}")).status_code == 409


async def test_cannot_use_someone_elses_image(client):
    await login(client, "other@example.com")
    theirs = await new_campaign(client)
    their_image = (await upload(client, theirs["id"], image_bytes(1080, 1080))).json()["image_id"]
    await login(client)
    mine = await new_campaign(client)
    response = await client.put(f"/campaigns/{mine['id']}/image", json={"image_id": their_image})
    assert response.status_code == 404
