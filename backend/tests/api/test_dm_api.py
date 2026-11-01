import asyncio
import hashlib
import hmac
import json

import pytest

from app.agents.dm_agent import DmAnswer
from app.agents.errors import ModelUnavailable, TurnFailed
from app.meta.fake import parse_fail_at
from app.services import dm
from tests.api_helpers import connect_fake_meta, login

SECRET = "app-secret-for-tests"
VERIFY = "verify-me"
BLOCK = {
    "enabled": True,
    "business_name": "Priya Bakery",
    "tone": "Warm and short",
    "knowledge": "Open 9am-6pm Mon-Sat. Birthday cakes from Rs 800.",
    "handoff_message": "Thanks! Priya will reply here soon.",
}


@pytest.fixture
def make_dm_client(make_client):
    return lambda **kw: make_client(meta_app_secret=SECRET, meta_webhook_verify_token=VERIFY, **kw)


def messaging(clock, text="What are your hours?", mid="m1", sender="cust_1", ig="ig_fake_1", **extra):
    event = {
        "sender": {"id": sender},
        "recipient": {"id": ig},
        "timestamp": int(clock.now().timestamp() * 1000),
        "message": {"mid": mid, "text": text},
    }
    return event | extra


async def deliver(client, *events, secret=SECRET, obj="instagram", entry_id="ig_fake_1"):
    raw = json.dumps({"object": obj, "entry": [{"id": entry_id, "messaging": list(events)}]}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return await client.post("/webhooks/instagram", content=raw, headers={"x-hub-signature-256": sig})


async def setup(client, **block):
    await login(client)
    await connect_fake_meta(client)
    response = await client.put("/dm/config", json=BLOCK | block)
    assert response.status_code == 200, response.text


async def threads(client) -> list[dict]:
    return (await client.get("/dm/threads")).json()


async def test_webhook_handshake_returns_the_challenge(make_dm_client):
    async with make_dm_client() as c:
        params = {"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "12345"}
        ok = await c.get("/webhooks/instagram", params=params)
        bad = await c.get("/webhooks/instagram", params=params | {"hub.verify_token": "nope"})
    assert (ok.status_code, ok.text) == (200, "12345") and bad.status_code == 403


async def test_handshake_is_refused_while_no_verify_token_is_configured(make_client):
    async with make_client() as c:
        response = await c.get(
            "/webhooks/instagram",
            params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"},
        )
    assert response.status_code == 403


async def test_enabling_needs_a_knowledge_block_and_subscribes_the_page(make_dm_client, fake_gateway):
    async with make_dm_client() as c:
        await login(c)
        await connect_fake_meta(c)
        empty = await c.put("/dm/config", json=BLOCK | {"knowledge": " "})
        assert (empty.status_code, empty.json()["error"]["code"]) == (409, "DM_AGENT_NOT_READY")
        saved = await c.put("/dm/config", json=BLOCK)
        assert saved.status_code == 200 and (await c.get("/dm/config")).json() == saved.json()
    assert fake_gateway.subscribed_pages == ["page_fake_1"]


async def test_knowledge_block_over_6000_characters_is_rejected(make_dm_client):
    async with make_dm_client() as c:
        await login(c)
        oversized = await c.put("/dm/config", json=BLOCK | {"knowledge": "x" * 6001})
    assert oversized.status_code == 422


async def test_dm_status_reports_agent_and_webhook_state(make_dm_client, fake_gateway):
    async with make_dm_client() as c:
        await setup(c)
        good = {"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1"}
        assert (await c.get("/webhooks/instagram", params=good)).status_code == 200
        verified = await c.get("/dm/status")
        assert verified.json()["agent_enabled"] is True
        assert verified.json()["webhook_verified"] is True
        assert verified.json()["webhook_subscribed"] is True
        bad = await c.get("/webhooks/instagram", params=good | {"hub.verify_token": "wrong"})
        status = await c.get("/dm/status")
        assert bad.status_code == 403 and status.json()["webhook_verified"] is False
        await c.put("/dm/config", json=BLOCK | {"enabled": False})
        off = await c.get("/dm/status")
        assert off.json()["agent_enabled"] is False


async def test_thread_list_puts_needs_human_first(make_dm_client, db, clock):
    async with make_dm_client() as c:
        await login(c)
        user = await db.users.find_one({"email": "dev@example.com"})
        now = clock.now()
        await db.dm_threads.insert_many([
            {"user_id": user["_id"], "customer_id": "customer-bot", "status": "BOT",
             "last_inbound_at": now, "updated_at": now, "messages": []},
            {"user_id": user["_id"], "customer_id": "customer-needs-human", "status": "NEEDS_HUMAN",
             "last_inbound_at": now, "updated_at": now, "messages": []},
        ])
        result = await c.get("/dm/threads")
    assert result.json()[0]["status"] == "NEEDS_HUMAN"


async def test_enabling_needs_a_connected_instagram_account(make_dm_client):
    async with make_dm_client() as c:
        await login(c)
        response = await c.put("/dm/config", json=BLOCK)
    assert (response.status_code, response.json()["error"]["code"]) == (409, "META_NOT_CONNECTED")


async def test_messenger_dm_to_the_page_is_answered_the_same_way(make_dm_client, fake_gateway, clock):
    """A message to the Facebook Page (webhook object "page", the Page id as recipient) gets the bot reply."""
    page_event = messaging(clock, ig="page_fake_1", mid="fb-1")
    async with make_dm_client() as c:
        await setup(c)
        response = await deliver(c, page_event, obj="page", entry_id="page_fake_1")
        [thread] = await threads(c)
    assert response.status_code == 200
    assert [d["recipient_id"] for d in fake_gateway.sent_dms] == ["cust_1"]
    assert fake_gateway.sent_dms[0]["page_id"] == "page_fake_1"
    assert [m["role"] for m in thread["messages"]] == ["customer", "agent"]


async def test_inbound_dm_gets_an_answer_from_the_knowledge_block(make_dm_client, fake_gateway, clock, db):
    async with make_dm_client() as c:
        await setup(c)
        assert (await deliver(c, messaging(clock))).status_code == 200
        [thread] = await threads(c)
    assert fake_gateway.sent_dms == [
        {
            "page_id": "page_fake_1",
            "recipient_id": "cust_1",
            "text": "Hi! We are open 9am to 6pm, Monday to Saturday.",
        }
    ]
    assert thread["status"] == "BOT"
    assert [m["role"] for m in thread["messages"]] == ["customer", "agent"]
    event = await db.audit_log.find_one({"event_type": "DM_REPLIED"})
    assert event["payload"]["input_tokens"] > 0 and event["payload"]["output_tokens"] > 0


async def test_unsigned_or_wrongly_signed_delivery_is_rejected(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c)
        forged = await deliver(c, messaging(clock), secret="not-the-secret")
        unsigned = await c.post("/webhooks/instagram", json={"entry": []})
        assert (forged.status_code, unsigned.status_code) == (403, 403)
        assert await threads(c) == []
    assert fake_gateway.sent_dms == []


async def test_delivery_is_refused_when_app_secret_is_empty(make_client, clock):
    async with make_client(meta_app_secret="", meta_webhook_verify_token=VERIFY) as c:
        raw = json.dumps({"object": "instagram", "entry": [{"messaging": [messaging(clock)]}]}).encode()
        sig = "sha256=" + hmac.new(b"anything", raw, hashlib.sha256).hexdigest()
        response = await c.post("/webhooks/instagram", content=raw, headers={"x-hub-signature-256": sig})
    assert response.status_code == 403


async def test_redelivered_message_is_answered_once(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c)
        await deliver(c, messaging(clock))
        await deliver(c, messaging(clock))
        [thread] = await threads(c)
    assert len(fake_gateway.sent_dms) == 1 and len(thread["messages"]) == 2


async def test_fast_repeated_messages_handoff_to_owner(make_dm_client, fake_gateway, clock, db):
    async with make_dm_client() as c:
        await setup(c)
        await deliver(c, messaging(clock, mid="fast-1"))
        await deliver(c, messaging(clock, mid="fast-2"))
        [thread] = await threads(c)
    assert thread["status"] == "NEEDS_HUMAN"
    assert len(fake_gateway.sent_dms) == 1
    assert [m["role"] for m in thread["messages"]] == ["customer", "agent", "customer"]
    assert await db.audit_log.count_documents({"event_type": "DM_RATE_LIMITED"}) == 1


async def test_concurrent_customer_events_are_answered_in_arrival_order(
    make_dm_client, fake_gateway, clock, db, container, monkeypatch
):
    async with make_dm_client() as c:
        await setup(c)
        first = messaging(clock, mid="ordered-1")
        second = messaging(clock, mid="ordered-2")

        original_answer = dm.answer_dm

        async def answer_then_advance(**kwargs):
            answer = await original_answer(**kwargs)
            clock.advance(seconds=4)
            return answer

        monkeypatch.setattr(dm, "answer_dm", answer_then_advance)
        await asyncio.gather(
            dm.handle_messaging(db, container, first),
            dm.handle_messaging(db, container, second),
        )
        [thread] = await threads(c)
    assert [m["mid"] for m in thread["messages"]] == [
        "ordered-1", "fake_mid_1", "ordered-2", "fake_mid_2"
    ]
    assert len(fake_gateway.sent_dms) == 2


async def test_more_than_30_bot_eligible_messages_in_an_hour_hands_off(
    make_dm_client, fake_gateway, clock
):
    async with make_dm_client() as c:
        await setup(c)
        for index in range(31):
            await deliver(c, messaging(clock, mid=f"hour-{index}"))
            clock.advance(seconds=3.1)
        [thread] = await threads(c)
    assert thread["status"] == "NEEDS_HUMAN"
    assert len(fake_gateway.sent_dms) == 30


async def test_when_the_ai_needs_a_human_the_handoff_goes_out_and_the_bot_stops(
    make_dm_client, fake_gateway, clock, monkeypatch
):
    async def unsure(**_):
        return DmAnswer(text="made up refund policy", needs_human=True)

    monkeypatch.setattr(dm, "answer_dm", unsure)
    async with make_dm_client() as c:
        await setup(c)
        await deliver(c, messaging(clock, text="I want a refund", mid="m1"))
        await deliver(c, messaging(clock, text="hello??", mid="m2"))
        [thread] = await threads(c)
    assert [d["text"] for d in fake_gateway.sent_dms] == [BLOCK["handoff_message"]]
    assert thread["status"] == "NEEDS_HUMAN" and thread["messages"][-1]["text"] == "hello??"


async def test_customer_angry_or_asks_for_a_human_hands_over(
    make_dm_client, fake_gateway, clock, monkeypatch
):
    async def angry_handoff(**_):
        return DmAnswer(text="", needs_human=True)

    monkeypatch.setattr(dm, "answer_dm", angry_handoff)
    async with make_dm_client() as c:
        await setup(c)
        await deliver(c, messaging(clock, text="I want to speak with a human right now!"))
        [thread] = await threads(c)
    assert thread["status"] == "NEEDS_HUMAN"
    assert [d["text"] for d in fake_gateway.sent_dms] == [BLOCK["handoff_message"]]



@pytest.mark.parametrize(
    "failure", [ModelUnavailable("busy"), TurnFailed("bad output"), RuntimeError("404 model gone")]
)
async def test_any_ai_failure_hands_over_instead_of_going_silent(
    make_dm_client, fake_gateway, db, clock, monkeypatch, failure
):
    async def down(**_):
        raise failure

    monkeypatch.setattr(dm, "answer_dm", down)
    async with make_dm_client() as c:
        await setup(c)
        await deliver(c, messaging(clock))
        [thread] = await threads(c)
    assert [d["text"] for d in fake_gateway.sent_dms] == [BLOCK["handoff_message"]]
    assert thread["status"] == "NEEDS_HUMAN"
    assert await db.audit_log.count_documents({"event_type": "DM_AI_FAILED"}) == 1


async def test_disabled_agent_records_the_message_but_does_not_answer(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c, enabled=False)
        await deliver(c, messaging(clock))
        [thread] = await threads(c)
    assert fake_gateway.sent_dms == [] and [m["role"] for m in thread["messages"]] == ["customer"]


async def test_nothing_is_sent_outside_the_24_hour_window(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c)
        old = messaging(clock) | {"timestamp": int((clock.now().timestamp() - 25 * 3600) * 1000)}
        await deliver(c, old)
    assert fake_gateway.sent_dms == []


async def test_echoes_and_unknown_accounts_are_ignored(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c)
        echo = messaging(clock, mid="e1")
        echo["message"]["is_echo"] = True
        await deliver(c, echo, messaging(clock, mid="m9", ig="ig_somebody_else"))
        assert await threads(c) == []
    assert fake_gateway.sent_dms == []


async def test_photo_only_message_gets_polite_text_reply(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c)
        photo = messaging(clock)
        photo["message"] = {"mid": "p1", "attachments": [{"type": "image"}]}
        await deliver(c, photo)
        [thread] = await threads(c)
    assert len(fake_gateway.sent_dms) == 1
    assert fake_gateway.sent_dms[0]["text"] == "I can read text only. Please type your question."
    assert thread["status"] == "NEEDS_HUMAN"


async def test_story_reply_is_stored_without_auto_reply(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c)
        story = messaging(clock, mid="story-1") | {"story_reply": {"id": "story"}}
        await deliver(c, story)
        [thread] = await threads(c)
    assert thread["status"] == "BOT"
    assert thread["messages"][0]["role"] == "customer"
    assert fake_gateway.sent_dms == []


async def test_meta_send_failure_flags_the_thread_for_a_human(make_dm_client, fake_gateway, db, clock):
    fake_gateway.fail_at.update(parse_fail_at("DM:100"))
    async with make_dm_client() as c:
        await setup(c)
        await deliver(c, messaging(clock))
        [thread] = await threads(c)
    assert thread["status"] == "NEEDS_HUMAN" and [m["role"] for m in thread["messages"]] == ["customer"]
    assert await db.audit_log.count_documents({"event_type": "DM_SEND_FAILED"}) == 1


async def test_owner_can_reply_by_hand_then_hand_the_thread_back(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c, enabled=False)
        await deliver(c, messaging(clock))
        [thread] = await threads(c)
        reply = await c.post(f"/dm/threads/{thread['id']}/reply", json={"message": "Hi, Priya here!"})
        assert reply.status_code == 200 and reply.json()["status"] == "HUMAN"
        assert reply.json()["messages"][-1]["role"] == "admin"
        back = await c.post(f"/dm/threads/{thread['id']}/resume")
    assert back.json()["status"] == "BOT" and fake_gateway.sent_dms[0]["text"] == "Hi, Priya here!"


async def test_manual_reply_is_refused_after_24_hours(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c, enabled=False)
        await deliver(c, messaging(clock))
        [thread] = await threads(c)
        clock.advance(hours=25)
        response = await c.post(f"/dm/threads/{thread['id']}/reply", json={"message": "late"})
    assert (response.status_code, response.json()["error"]["code"]) == (409, "OUTSIDE_MESSAGING_WINDOW")
    assert fake_gateway.sent_dms == []


async def test_preview_answers_without_touching_meta(make_dm_client, fake_gateway):
    async with make_dm_client() as c:
        await setup(c)
        response = await c.post("/dm/preview", json={"message": "When are you open?"})
    assert response.status_code == 200 and response.json()["needs_human"] is False
    assert fake_gateway.sent_dms == []


async def test_threads_belong_to_their_owner(make_dm_client, clock):
    async with make_dm_client() as c:
        await setup(c)
        await deliver(c, messaging(clock))
        [thread] = await threads(c)
        await c.post("/auth/logout")
        await login(c, email="other@example.com")
        assert await threads(c) == []
        assert (await c.get(f"/dm/threads/{thread['id']}")).status_code == 404
        assert (await c.post(f"/dm/threads/{thread['id']}/resume")).status_code == 404


async def test_two_users_same_customer_id_threads_do_not_mix(make_dm_client, clock, db):
    async with make_dm_client() as c:
        # First user with ig_fake_1
        await setup(c)
        await deliver(c, messaging(clock, sender="cust_shared", mid="m_user1"))
        [t1] = await threads(c)
        assert [m["mid"] for m in t1["messages"]] == ["m_user1", "fake_mid_1"]

        # Second user with different IG account
        await c.post("/auth/logout")
        await login(c, email="user2@example.com")
        await connect_fake_meta(c)
        await db.meta_connections.update_one(
            {"user_id": (await db.users.find_one({"email": "user2@example.com"}))["_id"]},
            {"$set": {"instagram_user_id": "ig_fake_2", "page_id": "page_fake_2"}},
        )
        await c.put("/dm/config", json=BLOCK)
        await deliver(c, messaging(clock, sender="cust_shared", mid="m_user2", ig="ig_fake_2"))
        [t2] = await threads(c)
        assert t2["id"] != t1["id"]
        assert [m["mid"] for m in t2["messages"]] == ["m_user2", "fake_mid_2"]


async def test_inbound_dm_via_changes_field_gets_an_answer(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c)
        raw = json.dumps({
            "object": "instagram",
            "entry": [{
                "id": "ig_fake_1",
                "changes": [{
                    "field": "messages",
                    "value": messaging(clock, text="What are your hours?", mid="m_change_1")
                }]
            }]
        }).encode()
        sig = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        response = await c.post("/webhooks/instagram", content=raw, headers={"x-hub-signature-256": sig})
        assert response.status_code == 200
        [thread] = await threads(c)
    assert len(fake_gateway.sent_dms) == 1
    assert [m["role"] for m in thread["messages"]] == ["customer", "agent"]


async def test_inbound_dm_where_recipient_is_page_id(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c)
        event = messaging(clock, ig="page_fake_1", mid="m_page_id_1")
        assert (await deliver(c, event)).status_code == 200
        [thread] = await threads(c)
    assert len(fake_gateway.sent_dms) == 1
    assert thread["status"] == "BOT"


async def test_reaction_is_stored_without_reply_and_no_error(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c)
        event = {
            "sender": {"id": "cust_1"},
            "recipient": {"id": "ig_fake_1"},
            "timestamp": int(clock.now().timestamp() * 1000),
            "reaction": {"mid": "react_mid_1", "action": "react", "emoji": "❤️", "reaction": "love"},
        }
        await deliver(c, event)
        [thread] = await threads(c)
    assert fake_gateway.sent_dms == []
    assert thread["status"] == "BOT"
    assert thread["messages"][0]["role"] == "customer"
    assert "❤️" in thread["messages"][0]["text"]


async def test_story_mention_is_stored_without_reply_and_no_error(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c)
        event = {
            "sender": {"id": "cust_1"},
            "recipient": {"id": "ig_fake_1"},
            "timestamp": int(clock.now().timestamp() * 1000),
            "story_mention": {"id": "story_mention_1"},
        }
        await deliver(c, event)
        [thread] = await threads(c)
    assert fake_gateway.sent_dms == []
    assert thread["status"] == "BOT"
    assert thread["messages"][0]["role"] == "customer"
    assert "[story mention]" in thread["messages"][0]["text"]


async def test_delete_conversation_endpoint(make_dm_client, clock):
    async with make_dm_client() as c:
        await setup(c)
        await deliver(c, messaging(clock))
        [thread] = await threads(c)
        thread_id = thread["id"]

        # Different user cannot delete it
        await c.post("/auth/logout")
        await login(c, email="other@example.com")
        assert (await c.delete(f"/dm/threads/{thread_id}")).status_code == 404

        # Owner can delete it
        await c.post("/auth/logout")
        await login(c)
        deleted = await c.delete(f"/dm/threads/{thread_id}")
        assert deleted.status_code == 200
        assert await threads(c) == []


async def test_dm_seen_ttl_index_is_configured(db):
    from app.db import ensure_indexes
    await ensure_indexes(db)
    cursor = await db.dm_seen.list_indexes()
    indexes = [idx async for idx in cursor]
    ttl_index = next((idx for idx in indexes if idx.get("expireAfterSeconds") is not None), None)
    assert ttl_index is not None
    assert ttl_index["expireAfterSeconds"] == 7 * 86400


async def test_webhook_raw_audit_only_in_non_production(make_dm_client, clock, db):
    async with make_dm_client() as c:
        await setup(c)
        await deliver(c, messaging(clock))
        assert await db.audit_log.count_documents({"event_type": "WEBHOOK_RAW"}) >= 1



async def test_conversation_shows_the_customer_name_not_an_id(make_dm_client, fake_gateway, clock):
    fake_gateway.customer_names["cust_1"] = "Ravi Kumar"
    async with make_dm_client() as c:
        await setup(c)
        await deliver(c, messaging(clock))
        await deliver(c, messaging(clock, mid="m2", text="And delivery?"))
        [thread] = await threads(c)
    assert thread["customer_name"] == "Ravi Kumar"
    assert fake_gateway.name_lookups == ["cust_1"]  # asked once, not on every message


async def test_unknown_customer_name_never_blocks_the_reply(make_dm_client, fake_gateway, clock):
    async with make_dm_client() as c:
        await setup(c)
        await deliver(c, messaging(clock))
        [thread] = await threads(c)
    assert thread["customer_name"] == ""
    assert len(fake_gateway.sent_dms) == 1
