"""Instagram DM auto-reply: owner-written knowledge block, inbound webhook events, per-customer threads.

Meta lets an app answer a DM for 24 hours after the customer's last message; we never send outside it.
"""

import asyncio
from asyncio import Lock
from datetime import UTC, datetime, timedelta

import structlog
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app import audit
from app.agents.dm_agent import answer_dm
from app.clock import utcnow
from app.container import Container
from app.errors import AppError, NotFound
from app.meta.connections import MetaNotConnected, require_selected
from app.services.user_ai import settings_for_user

log = structlog.get_logger()
WINDOW = timedelta(hours=24)
THREAD_KEEP = 100  # messages stored per thread
DEFAULT_HANDOFF = "Thanks for your message! A team member will reply to you here soon."
DEFAULT_CONFIG = {
    "enabled": False,
    "business_name": "",
    "tone": "Friendly and concise",
    "knowledge": "",
    "handoff_message": DEFAULT_HANDOFF,
}
UNSUPPORTED = "[unsupported message, e.g. a photo or voice note]"
_DM_LOCKS: dict[tuple[str, str], dict] = {}


class OutsideWindow(AppError):
    status, code = 409, "OUTSIDE_MESSAGING_WINDOW"


class DmNotReady(AppError):
    status, code = 409, "DM_AGENT_NOT_READY"


# --- owner config (the "context block" the AI reads) -------------------------------------------


async def get_config(db, user_id) -> dict:
    record = await db.dm_settings.find_one({"user_id": user_id}) or {}
    return {key: record.get(key, default) for key, default in DEFAULT_CONFIG.items()}


async def save_config(db, container: Container, user_id, values: dict) -> dict:
    """Saves the block; turning the agent on also subscribes the Page to DM webhooks if connected."""
    merged = await get_config(db, user_id) | {k: v for k, v in values.items() if k in DEFAULT_CONFIG}
    if len(merged["knowledge"]) > 6000:
        raise DmNotReady("Knowledge block must be 6,000 characters or fewer")
    if merged["enabled"]:
        user = await db.users.find_one({"_id": user_id}) or {}
        ws_id = user.get("active_workspace_id") or "synxait"

        # Check knowledge requirement: manual knowledge or automatic post knowledge chunks
        has_manual = bool(merged["knowledge"] and merged["knowledge"].strip())
        if not has_manual:
            chunks_count = await db.knowledge_chunks.count_documents({
                "$or": [{"workspace_id": ws_id}, {"business_id": ws_id}, {"user_id": user_id}]
            })
            if chunks_count == 0:
                raise DmNotReady("Add business knowledge before enabling the DM agent.")

        conn = await db.meta_connections.find_one({"user_id": user_id, "status": "ACTIVE"})
        if not conn:
            conn = await db.meta_connections.find_one({"workspace_id": ws_id, "status": "ACTIVE"}) or await db.meta_connections.find_one({"status": "ACTIVE"})
        if not conn or not (conn.get("instagram_user_id") or conn.get("page_id")):
            raise MetaNotConnected("Connect your Instagram ads account in Settings first")
        if conn and conn.get("page_id"):
            try:
                _, writer = container.gateway_for(conn)
                await writer.subscribe_messages(conn["page_id"])
            except Exception as sub_exc:
                log.warning("subscribe_messages_skipped", error=str(sub_exc), page_id=conn.get("page_id"))
    now = container.clock.now()
    await db.dm_settings.update_one(
        {"user_id": user_id},
        {"$set": merged | {"updated_at": now}, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return merged


# --- threads -----------------------------------------------------------------------------------


def _view(thread: dict, now: datetime | None = None) -> dict:
    now = now or utcnow()
    elapsed = max(0, (now - thread["last_inbound_at"]).total_seconds())
    return {
        "id": str(thread["_id"]),
        "customer_id": thread["customer_id"],
        "customer_name": thread.get("customer_name", ""),
        "status": thread["status"],
        "context_post_id": thread.get("context_post_id"),
        "context_post_title": thread.get("context_post_title"),
        "escalation": thread.get("escalation"),
        "last_inbound_at": thread["last_inbound_at"].isoformat(),
        "minutes_since_inbound": int(elapsed // 60),
        "reply_window_warning": timedelta(hours=22).total_seconds() <= elapsed < WINDOW.total_seconds(),
        "updated_at": thread["updated_at"].isoformat(),
        "messages": [{**m, "at": m["at"].isoformat()} for m in thread["messages"]],
    }


async def list_threads(db, user_id, *, limit: int = 50, now: datetime | None = None) -> list[dict]:
    cursor = db.dm_threads.find({"user_id": user_id}).sort("updated_at", -1).limit(limit)
    threads = [_view(t, now) async for t in cursor]
    priority = {"NEEDS_HUMAN": 0, "HUMAN": 1, "BOT": 2}
    return sorted(threads, key=lambda t: priority.get(t["status"], 3))


async def summary(db, user_id) -> dict:
    config = await get_config(db, user_id)
    count = await db.dm_threads.count_documents({"user_id": user_id, "status": "NEEDS_HUMAN"})
    latest = await db.dm_threads.find_one({"user_id": user_id}, sort=[("last_inbound_at", -1)])
    return {"enabled": config["enabled"], "needs_human": count,
            "last_inbound_at": latest["last_inbound_at"].isoformat() if latest else None}


async def _owned_thread(db, user_id, thread_id: str) -> dict:
    try:
        oid = ObjectId(thread_id)
    except (InvalidId, TypeError):
        raise NotFound("Conversation not found") from None
    thread = await db.dm_threads.find_one({"_id": oid, "user_id": user_id})
    if thread is None:
        raise NotFound("Conversation not found")
    return thread


async def get_thread(db, user_id, thread_id: str) -> dict:
    return _view(await _owned_thread(db, user_id, thread_id))


async def delete_thread(db, user_id, thread_id: str) -> None:
    thread = await _owned_thread(db, user_id, thread_id)
    await db.dm_threads.delete_one({"_id": thread["_id"], "user_id": user_id})


async def _send(db, container: Container, connection: dict, thread: dict, text: str, *, role: str) -> bool:
    """Sends through Meta; on failure hands the thread to a human instead of losing the reply."""
    _, writer = container.gateway_for(connection)
    now = container.clock.now()
    try:
        mid = await writer.send_dm(connection["page_id"], thread["customer_id"], text)
    except Exception as exc:
        log.exception(
            "dm_send_failed", thread_id=str(thread.get("_id")), customer_id=thread.get("customer_id")
        )
        await audit.record(
            db,
            actor="system",
            event_type="DM_SEND_FAILED",
            payload={"thread_id": str(thread["_id"]), "error": str(exc)[:200]},
            user_id=thread["user_id"],
        )
        await db.dm_threads.update_one(
            {"_id": thread["_id"]}, {"$set": {"status": "NEEDS_HUMAN", "updated_at": now}}
        )
        return False
    message = {"role": role, "text": text, "at": now, "mid": mid}
    await db.dm_threads.update_one(
        {"_id": thread["_id"]},
        {
            "$push": {"messages": {"$each": [message], "$slice": -THREAD_KEEP}},
            "$set": {"updated_at": now},
        },
    )
    return True


async def reply_as_human(db, container: Container, user_id, thread_id: str, text: str) -> dict:
    thread = await _owned_thread(db, user_id, thread_id)
    if container.clock.now() - thread["last_inbound_at"] > WINDOW:
        raise OutsideWindow("Instagram only allows replies within 24 hours of the customer's last message")
    connection = await require_selected(db, user_id, clock=container.clock)
    if not await _send(db, container, connection, thread, text, role="admin"):
        raise AppError("Instagram did not accept the message; try again")
    await db.dm_threads.update_one({"_id": thread["_id"]}, {"$set": {"status": "HUMAN"}})
    return await get_thread(db, user_id, thread_id)


async def resume_bot(db, user_id, thread_id: str) -> dict:
    thread = await _owned_thread(db, user_id, thread_id)
    await db.dm_threads.update_one({"_id": thread["_id"]}, {"$set": {"status": "BOT"}})
    return await get_thread(db, user_id, thread_id)


# --- the AI ------------------------------------------------------------------------------------


async def preview(db, container: Container, user_id, message: str, post_id: str | None = None) -> dict:
    """Lets the owner try the AI against the saved block and Hybrid RAG without any Meta traffic."""
    config = await get_config(db, user_id)
    user_settings = await settings_for_user(db, user_id, container.settings)
    user = await db.users.find_one({"_id": user_id}) or {}
    ws_id = user.get("active_workspace_id") or "synxait"

    from app.services.hybrid_rag import HybridRAG
    from app.services.shared_post_resolver import SharedPostContextResolver

    resolver = SharedPostContextResolver(db, user_settings)
    resolved = await resolver.resolve(workspace_id=ws_id, message_text=message)
    active_post_id = resolved.post_id if resolved else post_id

    rag = HybridRAG(db, user_settings)
    h_context = await rag.retrieve(workspace_id=ws_id, query=message, resolved_post_id=active_post_id)

    knowledge_payload = dict(config)
    knowledge_payload["prompt_context"] = h_context.prompt_context

    answer = await answer_dm(
        knowledge=knowledge_payload,
        history=[],
        message=message,
        settings=user_settings,
    )
    reply = config["handoff_message"] if answer.needs_human else answer.text
    return {
        "reply": reply,
        "needs_human": answer.needs_human,
        "escalation_reason": answer.escalation_reason,
        "resolved_post_id": active_post_id,
        "resolved_post_title": resolved.title if resolved else None,
    }


async def handle_messaging(db, container: Container, event: dict) -> None:
    """Serialize a customer's events so replies remain ordered and rate limits cannot race."""
    message = event.get("message") or {}
    customer = (event.get("sender") or {}).get("id")
    recipient_id = (event.get("recipient") or {}).get("id")
    entry_id = event.get("entry_id")
    account_id = recipient_id or entry_id
    mid = (
        message.get("mid")
        or (event.get("reaction") or {}).get("mid")
        or (event.get("story_mention") or {}).get("mid")
        or (event.get("story_reply") or {}).get("mid")
        or (f"evt_{event.get('timestamp')}_{customer}" if event.get("timestamp") and customer else None)
    )
    if (
        not (mid and account_id and customer)
        or message.get("is_echo")
        or customer in (recipient_id, entry_id)
    ):
        return
    key = (str(account_id), str(customer))
    entry = _DM_LOCKS.get(key)
    if entry is None:
        entry = {"lock": Lock(), "users": 0}
        _DM_LOCKS[key] = entry
    entry["users"] += 1
    try:
        async with entry["lock"]:
            await _handle_messaging_locked(db, container, event)
    finally:
        entry["users"] -= 1
        if entry["users"] == 0 and _DM_LOCKS.get(key) is entry:
            del _DM_LOCKS[key]


async def _handle_messaging_locked(db, container: Container, event: dict) -> None:
    """One `messaging` item of an Instagram webhook delivery."""
    message = event.get("message") or {}
    customer = (event.get("sender") or {}).get("id")
    recipient_id = (event.get("recipient") or {}).get("id")
    entry_id = event.get("entry_id")
    account_id = recipient_id or entry_id
    mid = (
        message.get("mid")
        or (event.get("reaction") or {}).get("mid")
        or (event.get("story_mention") or {}).get("mid")
        or (event.get("story_reply") or {}).get("mid")
        or (f"evt_{event.get('timestamp')}_{customer}" if event.get("timestamp") and customer else None)
    )
    if (
        not (mid and account_id and customer)
        or message.get("is_echo")
        or customer in (recipient_id, entry_id)
    ):
        return
    candidate_ids = [str(recipient_id)] if recipient_id else ([str(entry_id)] if entry_id else [])
    connection = await db.meta_connections.find_one(
        {
            "$or": [
                {"instagram_user_id": {"$in": candidate_ids}},
                {"page_id": {"$in": candidate_ids}},
            ],
            "status": "ACTIVE",
        }
    )
    if connection is None or not connection.get("page_id"):
        return
    now = container.clock.now()
    try:
        await db.dm_seen.insert_one(
            {"_id": mid, "at": now, "user_id": connection["user_id"], "customer_id": customer}
        )  # Meta redelivers; answer each message once
    except DuplicateKeyError:
        return
    sent_at = datetime.fromtimestamp(event["timestamp"] / 1000, UTC) if event.get("timestamp") else now
    user_id = connection["user_id"]
    ig_id = str(connection.get("instagram_user_id") or account_id)

    raw_text = (message.get("text") or "").strip()
    if raw_text:
        text = raw_text
    elif "reaction" in event:
        emoji = event["reaction"].get("emoji") or event["reaction"].get("reaction") or "reaction"
        text = f"[reaction: {emoji}]"
    elif "story_mention" in event:
        text = "[story mention]"
    elif "story_reply" in event:
        text = "[story reply]"
    elif message.get("attachments"):
        types = [a.get("type", "attachment") for a in message.get("attachments", [])]
        text = f"[unsupported message: {', '.join(types)}]"
    else:
        text = UNSUPPORTED

    thread = await db.dm_threads.find_one_and_update(
        {"user_id": user_id, "customer_id": customer},
        {
            "$push": {
                "messages": {
                    "$each": [{"role": "customer", "text": text, "at": sent_at, "mid": mid}],
                    "$slice": -THREAD_KEEP,
                }
            },
            "$set": {"last_inbound_at": sent_at, "updated_at": now, "ig_user_id": ig_id},
            "$setOnInsert": {"status": "BOT", "created_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    name_task = None
    if "customer_name" not in thread:  # asked once; run in background so reply isn't delayed
        async def _fetch_customer_name() -> None:
            try:
                gateway = container.gateway_for(connection)[1]
                name = await gateway.customer_name(connection["page_id"], customer)
            except Exception:
                name = None
            await db.dm_threads.update_one({"_id": thread["_id"]}, {"$set": {"customer_name": name or ""}})

        name_task = asyncio.create_task(_fetch_customer_name())
    config = await get_config(db, user_id)
    if not config["enabled"] or thread["status"] != "BOT" or now - sent_at > WINDOW:
        if name_task is not None:
            try:
                await name_task
            except Exception:
                pass
        return
    reply_to = message.get("reply_to")
    # Story mentions, story replies, reactions, and postbacks are stored without automated text reply
    if any(key in event for key in ("story_mention", "story_reply", "reaction", "postback")):
        return
    await db.dm_seen.update_one({"_id": mid}, {"$set": {"bot_eligible": True}})
    recent = await db.dm_seen.count_documents(
        {"user_id": user_id, "customer_id": customer, "bot_eligible": True,
         "at": {"$gte": now - timedelta(hours=1)}}
    )
    rapid = await db.dm_seen.count_documents(
        {"user_id": user_id, "customer_id": customer, "bot_eligible": True,
         "at": {"$gte": now - timedelta(seconds=3)}}
    )
    if recent > 30 or rapid > 1:
        await db.dm_threads.update_one(
            {"_id": thread["_id"]}, {"$set": {"status": "NEEDS_HUMAN"}}
        )
        await audit.record(
            db, actor="system", event_type="DM_RATE_LIMITED",
            payload={"thread_id": str(thread["_id"])}, user_id=user_id,
        )
        return
    user = await db.users.find_one({"_id": user_id}) or {}
    ws_id = user.get("active_workspace_id") or "synxait"
    user_settings = await settings_for_user(db, user_id, container.settings)

    from app.services.shared_post_resolver import SharedPostContextResolver
    from app.services.hybrid_rag import HybridRAG

    resolver = SharedPostContextResolver(db, user_settings)
    attachments_list = list(message.get("attachments") or [])
    if isinstance(reply_to, dict) and reply_to.get("story"):
        story_info = reply_to["story"]
        attachments_list.append({
            "type": "story_share",
            "id": str(story_info.get("id") or ""),
            "payload": {
                "id": str(story_info.get("id") or ""),
                "url": story_info.get("url") or "",
                "media_id": str(story_info.get("id") or ""),
            }
        })
    if "story_reply" in event and isinstance(event["story_reply"], dict):
        sr = event["story_reply"]
        attachments_list.append({
            "type": "story_reply",
            "id": str(sr.get("story_id") or ""),
            "payload": {
                "id": str(sr.get("story_id") or ""),
                "url": sr.get("link") or "",
                "media_id": str(sr.get("story_id") or ""),
            }
        })
    resolved = await resolver.resolve(workspace_id=ws_id, message_text=raw_text, attachments=attachments_list)

    context_post_id = thread.get("context_post_id")
    context_post_title = thread.get("context_post_title")
    if resolved:
        context_post_id = resolved.post_id
        context_post_title = resolved.title
        await db.dm_threads.update_one(
            {"_id": thread["_id"]},
            {"$set": {"context_post_id": context_post_id, "context_post_title": context_post_title}},
        )

    if resolved and resolved.is_ambiguous and resolved.candidate_titles and len(resolved.candidate_titles) >= 2:
        c1, c2 = resolved.candidate_titles[0], resolved.candidate_titles[1]
        clarification = f"Are you asking about our '{c1}' or '{c2}'? Please let us know so we can help!"
        if name_task is not None:
            try:
                await name_task
            except Exception:
                pass
        await _send(db, container, connection, thread, clarification, role="agent")
        return

    if not raw_text:
        if name_task is not None:
            try:
                await name_task
            except Exception:
                pass
        if resolved:
            greeting = f"Thanks for sharing! How can we help you with our {resolved.title or 'post'}?"
            await _send(db, container, connection, thread, greeting, role="agent")
            return
        await _send(
            db, container, connection, thread,
            "I can read text only. Please type your question.", role="agent",
        )
        await db.dm_threads.update_one({"_id": thread["_id"]}, {"$set": {"status": "NEEDS_HUMAN"}})
        return

    try:
        input_tokens = output_tokens = 0
        rag = HybridRAG(db, user_settings)
        h_context = await rag.retrieve(
            workspace_id=ws_id,
            query=text,
            resolved_post_id=context_post_id,
        )
        knowledge_payload = dict(config)
        knowledge_payload["prompt_context"] = h_context.prompt_context

        answer = await answer_dm(
            knowledge=knowledge_payload,
            history=thread["messages"][:-1],
            message=text,
            settings=user_settings,
        )
        needs_human = answer.needs_human
        input_tokens, output_tokens = answer.input_tokens, answer.output_tokens
        reply = config["handoff_message"] if needs_human else answer.text
    except Exception as exc:
        log.exception("dm_ai_failed")
        await audit.record(
            db,
            actor="system",
            event_type="DM_AI_FAILED",
            payload={"thread_id": str(thread["_id"]), "error": type(exc).__name__},
            user_id=user_id,
        )
        needs_human, reply = True, config["handoff_message"]
        answer = None

    if name_task is not None:
        try:
            await name_task
        except Exception:
            pass

    if await _send(db, container, connection, thread, reply, role="agent") and needs_human:
        escalation_doc = {
            "reason": (answer.escalation_reason if answer else None) or "REQUIRES_HUMAN",
            "customer_message": text,
            "post_id": context_post_id,
            "post_title": context_post_title,
            "escalated_at": now.isoformat(),
            "suggested_response": reply,
        }
        await db.dm_threads.update_one(
            {"_id": thread["_id"]},
            {"$set": {"status": "NEEDS_HUMAN", "escalation": escalation_doc}},
        )
    await audit.record(
        db,
        actor="agent",
        event_type="DM_REPLIED",
        payload={
            "thread_id": str(thread["_id"]), "needs_human": needs_human,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
        },
        user_id=user_id,
    )
