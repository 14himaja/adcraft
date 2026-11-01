from datetime import date
from io import BytesIO

from bson import ObjectId
from PIL import Image

from tests.api_helpers import connect_fake_meta, login

IDEA = "Promote my Python course for college students in Bangalore, https://synxa.ai/python"


def png(width: int, height: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "purple").save(buffer, format="PNG")
    return buffer.getvalue()


async def draft(client, idea: str = IDEA) -> dict:
    response = await client.post("/campaigns/draft", json={"idea": idea})
    assert response.status_code == 200, response.text
    return response.json()


async def test_idea_becomes_a_complete_draft_with_an_image(client, image_generator, fake_gateway):
    await login(client)
    await connect_fake_meta(client)
    campaign = await draft(client)
    assert (campaign["status"], campaign["idea"], campaign["title"]) == (
        "DRAFT",
        IDEA,
        "Python Course Launch",
    )
    assert len(campaign["variants"]) == 3 and campaign["image_id"]
    assert campaign["audience"]["interests"][0] == {
        "id": "6003682002118",
        "name": "Python (programming language)",
    }
    assert (campaign["missing_fields"], campaign["warnings"], campaign["can_publish"]) == ([], [], True)
    assert image_generator.prompts[0].startswith("Bright square photo of a smiling college student")
    assert fake_gateway.objects == {}  # drafting never writes to Meta


async def test_image_failure_still_saves_the_draft_with_a_warning(client, image_generator):
    await login(client)
    image_generator.fail = True
    campaign = await draft(client)
    assert campaign["image_id"] is None and "image_id" in campaign["missing_fields"]
    assert any(w.startswith("Image generation failed") for w in campaign["warnings"])
    assert any("Connect your Meta account" in w for w in campaign["warnings"])


async def test_idea_must_not_be_empty(client):
    await login(client)
    response = await client.post("/campaigns/draft", json={"idea": "  "})
    assert (response.status_code, response.json()["error"]["code"]) == (422, "VALIDATION_FAILED")


async def test_improve_copy_rewrites_variants_of_a_draft_only(client, db):
    await login(client)
    campaign = await draft(client)
    response = await client.post(
        f"/campaigns/{campaign['id']}/copy/improve", json={"instruction": "mention a free first week"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["variants"][0]["description"] == "First week free"
    await db.campaigns.update_one({"_id": ObjectId(campaign["id"])}, {"$set": {"status": "ACTIVE"}})
    blocked = await client.post(f"/campaigns/{campaign['id']}/copy/improve", json={"instruction": "x y z"})
    assert blocked.status_code == 409


async def test_offline_flow_idea_draft_edit_improve_regenerate_upload(client, image_generator):
    await login(client)
    await connect_fake_meta(client)
    campaign = await draft(client)
    cid = campaign["id"]

    edited = await client.put(
        f"/campaigns/{cid}", json={"daily_budget": 300, "selected_variant": 2, "end_date": "2026-10-20"}
    )
    assert edited.status_code == 200, edited.text
    assert (edited.json()["daily_budget"], edited.json()["selected_variant"]) == (300.0, 2)
    too_long = {**campaign["variants"][0], "headline": "H" * 41}
    rejected = await client.put(f"/campaigns/{cid}", json={"variants": [too_long]})
    assert rejected.status_code == 422 and "variants.0.headline" in rejected.json()["error"]["message"]

    improved = await client.post(f"/campaigns/{cid}/copy/improve", json={"instruction": "free first week"})
    assert improved.json()["variants"][0]["headline"] == "Python in 30 days"

    first_image = improved.json()["image_id"]
    regenerated = await client.post(f"/campaigns/{cid}/image/generate", json={"prompt": "evening light"})
    assert regenerated.json()["image_id"] not in (None, first_image)
    assert "evening light" in image_generator.prompts[-1]

    uploaded = await client.post(f"/campaigns/{cid}/image", files={"file": ("own.png", png(1080, 1080))})
    final = uploaded.json()
    assert uploaded.status_code == 200 and final["image_id"] != regenerated.json()["image_id"]
    assert (final["can_publish"], final["rev"]) == (True, 5)
    assert len((await client.get("/media")).json()) == 3
    image = await client.get(final["image_url"].removeprefix("/api/v1"))
    assert image.headers["content-type"] == "image/jpeg"


async def test_chat_message_edits_budget_dates_audience_copy_and_image(client, db, image_generator):
    await login(client)
    await connect_fake_meta(client)
    campaign = await draft(client)
    response = await client.post(
        f"/campaigns/{campaign['id']}/chat",
        json={"message": "₹200 a day for 2 weeks, drop Bangalore, night photo"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    edited = body["campaign"]
    assert body["warnings"] == []
    for part in ("budget ₹200/day", "runs 14 days", "removed Bangalore", "ad text", "new image", "version 2"):
        assert part in body["reply"]
    assert (edited["daily_budget"], edited["selected_variant"]) == (200.0, 1)
    assert (date.fromisoformat(edited["end_date"]) - date.fromisoformat(edited["start_date"])).days == 14
    assert edited["audience"]["cities"] == [] and edited["audience"]["countries"] == ["IN"]
    assert edited["variants"][0]["headline"] == "Python live classes from home"
    assert edited["image_id"] != campaign["image_id"] and "at night" in image_generator.prompts[-1]
    assert [m["role"] for m in edited["chat"]] == ["user", "user", "assistant"]
    assert edited["chat"][0]["text"] == IDEA and edited["chat"][2]["text"] == body["reply"]

    await db.campaigns.update_one({"_id": ObjectId(campaign["id"])}, {"$set": {"status": "ACTIVE"}})
    blocked = await client.post(f"/campaigns/{campaign['id']}/chat", json={"message": "cheaper"})
    assert blocked.status_code == 409
