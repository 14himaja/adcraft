from app.domain.workspaces import resolve_workspace_id
"""Instagram DM auto-reply: owner-written knowledge block, inbound webhook events, per-customer threads.

Meta lets an app answer a DM for 24 hours after the customer's last message; we never send outside it.
"""

import asyncio
from asyncio import Lock
from datetime import UTC, datetime, timedelta
import time

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
from app.services.embeddings import generate_embedding
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
DEBOUNCE_DELAY: float = 0.6


class OutsideWindow(AppError):
    status, code = 409, "OUTSIDE_MESSAGING_WINDOW"


class DmNotReady(AppError):
    status, code = 409, "DM_AGENT_NOT_READY"


# --- owner config (the "context block" the AI reads) -------------------------------------------


async def get_config(db, user_id) -> dict:
    record = await db.dm_settings.find_one({"user_id": user_id}) or {}
    config = {key: record.get(key, default) for key, default in DEFAULT_CONFIG.items()}
    if "enabled" not in record:
        conn = await db.meta_connections.find_one({"user_id": user_id, "status": "ACTIVE"})
        if not conn:
            user = await db.users.find_one({"_id": user_id}) or {}
            ws_id = resolve_workspace_id(user=user)
            conn = await db.meta_connections.find_one({"workspace_id": ws_id, "status": "ACTIVE"})
        if conn and (conn.get("instagram_user_id") or conn.get("page_id")):
            config["enabled"] = True
    return config


async def save_config(db, container: Container, user_id, values: dict) -> dict:
    """Saves the block; turning the agent on also subscribes the Page to DM webhooks if connected."""
    merged = await get_config(db, user_id) | {k: v for k, v in values.items() if k in DEFAULT_CONFIG}
    if len(merged["knowledge"]) > 6000:
        raise DmNotReady("Knowledge block must be 6,000 characters or fewer")
    if merged["enabled"]:
        user = await db.users.find_one({"_id": user_id}) or {}
        ws_id = resolve_workspace_id(user=user)

        conn = await db.meta_connections.find_one({"user_id": user_id, "status": "ACTIVE"})
        if not conn and ws_id:
            conn = await db.meta_connections.find_one({"workspace_id": ws_id, "status": "ACTIVE"})
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
        "escalation_history": thread.get("escalation_history", []),
        "needs_attention": bool(thread.get("needs_attention", False)),
        "attention_reason": thread.get("attention_reason"),
        "last_inbound_at": thread["last_inbound_at"].isoformat(),
        "minutes_since_inbound": int(elapsed // 60),
        "reply_window_warning": timedelta(hours=22).total_seconds() <= elapsed < WINDOW.total_seconds(),
        "updated_at": thread["updated_at"].isoformat(),
        "messages": [{**m, "at": m["at"].isoformat()} for m in thread["messages"]],
    }


async def list_threads(db, user_id, *, limit: int = 50, now: datetime | None = None) -> list[dict]:
    cursor = db.dm_threads.find({"user_id": user_id}).sort("updated_at", -1).limit(limit)
    threads = [_view(t, now) async for t in cursor]
    def _sort_key(t):
        if t["status"] == "NEEDS_HUMAN":
            return 0
        if t.get("needs_attention"):
            return 1
        if t["status"] == "HUMAN":
            return 2
        return 3
    return sorted(threads, key=_sort_key)


async def summary(db, user_id) -> dict:
    config = await get_config(db, user_id)
    count = await db.dm_threads.count_documents({"user_id": user_id, "status": "NEEDS_HUMAN"})
    attention_count = await db.dm_threads.count_documents({"user_id": user_id, "needs_attention": True})
    latest = await db.dm_threads.find_one({"user_id": user_id}, sort=[("last_inbound_at", -1)])
    return {
        "enabled": config["enabled"],
        "needs_human": count,
        "needs_attention": attention_count,
        "last_inbound_at": latest["last_inbound_at"].isoformat() if latest else None,
    }


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
            {"_id": thread["_id"]},
            {
                "$set": {
                    "status": "NEEDS_HUMAN",
                    "escalation": {"reason": "SEND_FAILED", "error": str(exc)[:200], "escalated_at": now.isoformat()},
                    "updated_at": now,
                }
            },
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


def _log_latency(t_start: float, thread_id: str | ObjectId | None = None) -> None:
    elapsed_ms = round((time.monotonic() - t_start) * 1000, 2)
    log.info("dm_webhook_to_send_latency", elapsed_ms=elapsed_ms, thread_id=str(thread_id or ""))


async def reply_as_human(db, container: Container, user_id, thread_id: str, text: str) -> dict:
    thread = await _owned_thread(db, user_id, thread_id)
    if container.clock.now() - thread["last_inbound_at"] > WINDOW:
        raise OutsideWindow("Instagram only allows replies within 24 hours of the customer's last message")
    connection = await require_selected(db, user_id, clock=container.clock)
    if not await _send(db, container, connection, thread, text, role="admin"):
        raise AppError("Instagram did not accept the message; try again")
    await db.dm_threads.update_one(
        {"_id": thread["_id"]},
        {"$set": {"status": "HUMAN", "needs_attention": False, "attention_reason": None}}
    )
    return await get_thread(db, user_id, thread_id)


async def resume_bot(db, user_id, thread_id: str) -> dict:
    thread = await _owned_thread(db, user_id, thread_id)
    await db.dm_threads.update_one(
        {"_id": thread["_id"]},
        {"$set": {"status": "BOT", "needs_attention": False, "attention_reason": None}}
    )
    return await get_thread(db, user_id, thread_id)


# --- the AI ------------------------------------------------------------------------------------


async def preview(db, container: Container, user_id, message: str, post_id: str | None = None) -> dict:
    """Lets the owner try the AI against the saved block and Hybrid RAG without any Meta traffic."""
    config = await get_config(db, user_id)
    user_settings = await settings_for_user(db, user_id, container.settings)
    user = await db.users.find_one({"_id": user_id}) or {}
    ws_id = resolve_workspace_id(user=user)

    from app.services.hybrid_rag import HybridRAG
    from app.services.shared_post_resolver import SharedPostContextResolver

    query_emb = await generate_embedding(message, user_settings) if message else None

    resolver = SharedPostContextResolver(db, user_settings, container=container)
    resolved = await resolver.resolve(workspace_id=ws_id, message_text=message, query_embedding=query_emb)
    active_post_id = resolved.post_id if resolved else post_id

    rag = HybridRAG(db, user_settings)
    h_context = await rag.retrieve(
        workspace_id=ws_id,
        user_id=user_id,
        query=message,
        resolved_post_id=active_post_id,
        query_embedding=query_emb,
    )

    knowledge_payload = dict(config)
    knowledge_payload["prompt_context"] = h_context.prompt_context

    answer = await answer_dm(
        knowledge=knowledge_payload,
        history=[],
        message=message,
        settings=user_settings,
    )
    reply = config["handoff_message"] if answer.needs_human else answer.text
    resolved_title = resolved.title if resolved else (h_context.resolved_post.get("title") or h_context.resolved_post.get("subject") if h_context.resolved_post else None)
    return {
        "reply": reply,
        "needs_human": answer.needs_human,
        "escalation_reason": answer.escalation_reason,
        "resolved_post_id": active_post_id or (str(h_context.resolved_post["_id"]) if h_context.resolved_post else None),
        "resolved_post_title": resolved_title,
    }


def _extract_mid(event: dict) -> str | None:
    message = event.get("message") or {}
    customer = (event.get("sender") or {}).get("id")
    return (
        message.get("mid")
        or (event.get("reaction") or {}).get("mid")
        or (event.get("story_mention") or {}).get("mid")
        or (event.get("story_reply") or {}).get("mid")
        or (f"evt_{event.get('timestamp')}_{customer}" if event.get("timestamp") and customer else None)
    )


async def handle_messaging(db, container: Container, event: dict) -> None:
    """Serialize a customer's events with ~1.5s debounce so bursts merge into one reply."""
    t_arrival = time.monotonic()
    message = event.get("message") or {}
    customer = (event.get("sender") or {}).get("id")
    recipient_id = (event.get("recipient") or {}).get("id")
    entry_id = event.get("entry_id")
    account_id = recipient_id or entry_id
    mid = _extract_mid(event)
    if (
        not (mid and account_id and customer)
        or message.get("is_echo")
        or customer in (recipient_id, entry_id)
    ):
        return

    key = (str(account_id), str(customer))
    entry = _DM_LOCKS.get(key)
    if entry is None:
        entry = {
            "lock": Lock(),
            "users": 0,
            "pending_events": [],
            "processed_mids": set(),
        }
        _DM_LOCKS[key] = entry
    entry["users"] += 1
    entry["pending_events"].append((event, t_arrival))

    try:
        async with entry["lock"]:
            if mid in entry["processed_mids"]:
                # Merged and replied to in an earlier task during debounce
                return

            if DEBOUNCE_DELAY > 0:
                await asyncio.sleep(DEBOUNCE_DELAY)

            events_batch = list(entry["pending_events"])
            entry["pending_events"].clear()

            for ev, _ in events_batch:
                emid = _extract_mid(ev)
                if emid:
                    entry["processed_mids"].add(emid)

            await _handle_messaging_batch_locked(db, container, key, events_batch)
    finally:
        entry["users"] -= 1
        if entry["users"] == 0 and _DM_LOCKS.get(key) is entry:
            del _DM_LOCKS[key]


async def _handle_messaging_locked(db, container: Container, event: dict) -> None:
    """Legacy entry point: process one event directly."""
    message = event.get("message") or {}
    customer = (event.get("sender") or {}).get("id")
    recipient_id = (event.get("recipient") or {}).get("id")
    entry_id = event.get("entry_id")
    account_id = recipient_id or entry_id
    if account_id and customer:
        key = (str(account_id), str(customer))
        await _handle_messaging_batch_locked(db, container, key, [(event, time.monotonic())])


async def _handle_messaging_batch_locked(
    db, container: Container, key: tuple[str, str], events_batch: list[tuple[dict, float]]
) -> None:
    """Processes a debounced batch of customer webhook events."""
    if not events_batch:
        return

    account_id, customer = key
    candidate_ids = set()
    for ev, _ in events_batch:
        rec = (ev.get("recipient") or {}).get("id")
        if rec:
            candidate_ids.add(str(rec))
        ent = ev.get("entry_id")
        if ent:
            candidate_ids.add(str(ent))
    if not candidate_ids:
        candidate_ids.add(str(account_id))

    connection = await db.meta_connections.find_one(
        {
            "$or": [
                {"instagram_user_id": {"$in": list(candidate_ids)}},
                {"page_id": {"$in": list(candidate_ids)}},
            ],
            "status": "ACTIVE",
        }
    )
    if connection is None or not connection.get("page_id"):
        return

    now = container.clock.now()
    user_id = connection["user_id"]
    valid_events: list[tuple[dict, float]] = []
    for ev, t_arr in events_batch:
        emid = _extract_mid(ev)
        if not emid:
            continue
        try:
            await db.dm_seen.insert_one(
                {"_id": emid, "at": now, "user_id": user_id, "customer_id": customer}
            )
            valid_events.append((ev, t_arr))
        except DuplicateKeyError:
            continue

    if not valid_events:
        return

    t_webhook_start = min(t_arr for _, t_arr in valid_events)
    ig_id = str(connection.get("instagram_user_id") or account_id)

    customer_messages_to_push = []
    extracted_texts = []
    attachments_list = []
    all_story_mention = True
    all_reaction = True
    all_postback = True

    for ev, _ in valid_events:
        msg = ev.get("message") or {}
        emid = _extract_mid(ev)
        sent_at = datetime.fromtimestamp(ev["timestamp"] / 1000, UTC) if ev.get("timestamp") else now
        raw = (msg.get("text") or "").strip()

        is_story_mention = "story_mention" in ev
        is_reaction = "reaction" in ev
        is_postback = "postback" in ev
        is_story_reply = "story_reply" in ev

        if not is_story_mention:
            all_story_mention = False
        if not is_reaction:
            all_reaction = False
        if not is_postback:
            all_postback = False

        if raw:
            msg_text = raw
            extracted_texts.append(raw)
        elif is_reaction:
            emoji = ev["reaction"].get("emoji") or ev["reaction"].get("reaction") or "reaction"
            msg_text = f"[reaction: {emoji}]"
        elif is_story_mention:
            msg_text = "[story mention]"
        elif is_story_reply:
            msg_text = "[story reply]"
        elif msg.get("attachments"):
            types = [a.get("type", "attachment") for a in msg.get("attachments", [])]
            msg_text = f"[unsupported message: {', '.join(types)}]"
        else:
            msg_text = UNSUPPORTED

        customer_messages_to_push.append({
            "role": "customer", "text": msg_text, "at": sent_at, "mid": emid
        })

        if msg.get("attachments"):
            attachments_list.extend(msg.get("attachments"))

        reply_to = msg.get("reply_to")
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

        if is_story_reply and isinstance(ev["story_reply"], dict):
            sr = ev["story_reply"]
            attachments_list.append({
                "type": "story_reply",
                "id": str(sr.get("story_id") or ""),
                "payload": {
                    "id": str(sr.get("story_id") or ""),
                    "url": sr.get("link") or "",
                    "media_id": str(sr.get("story_id") or ""),
                }
            })

    last_sent_at = max(m["at"] for m in customer_messages_to_push)
    thread = await db.dm_threads.find_one_and_update(
        {"user_id": user_id, "customer_id": customer},
        {
            "$push": {
                "messages": {
                    "$each": customer_messages_to_push,
                    "$slice": -THREAD_KEEP,
                }
            },
            "$set": {"last_inbound_at": last_sent_at, "updated_at": now, "ig_user_id": ig_id},
            "$setOnInsert": {"status": "BOT", "created_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    # 4 & 6. Auto-resume bot on customer next message unless escalation reason is RATE_LIMITED or SEND_FAILED, or human replied
    if thread.get("status") == "NEEDS_HUMAN":
        esc = thread.get("escalation") or {}
        esc_reason = (esc.get("reason") if isinstance(esc, dict) else str(esc)) or ""
        if esc_reason not in ("RATE_LIMITED", "SEND_FAILED"):
            update_op = {
                "$set": {"status": "BOT", "escalation": None, "updated_at": now},
            }
            if esc:
                update_op["$push"] = {"escalation_history": esc}
            await db.dm_threads.update_one({"_id": thread["_id"]}, update_op)
            thread["status"] = "BOT"
            if esc:
                thread.setdefault("escalation_history", []).append(esc)
            thread["escalation"] = None

    # Fetch customer name in background without awaiting before _send
    name_task = None
    if "customer_name" not in thread:
        async def _fetch_customer_name() -> None:
            try:
                gateway = container.gateway_for(connection)[1]
                name = await gateway.customer_name(connection["page_id"], customer)
            except Exception:
                name = None
            await db.dm_threads.update_one({"_id": thread["_id"]}, {"$set": {"customer_name": name or ""}})

        name_task = asyncio.create_task(_fetch_customer_name())

    config = await get_config(db, user_id)
    if not config["enabled"] or thread["status"] != "BOT" or now - last_sent_at > WINDOW:
        if name_task is not None:
            try:
                await name_task
            except Exception:
                pass
        return

    # Reactions, story mentions, and postbacks without customer text are stored without automated reply
    # Note: story replies ARE replied to!
    if not extracted_texts and (all_reaction or all_story_mention or all_postback):
        if name_task is not None:
            try:
                await name_task
            except Exception:
                pass
        return

    for ev, _ in valid_events:
        emid = _extract_mid(ev)
        if emid:
            await db.dm_seen.update_one({"_id": emid}, {"$set": {"bot_eligible": True}})

    # Hourly rate limit (rapid check removed; hourly rate limit still replies)
    recent = await db.dm_seen.count_documents(
        {"user_id": user_id, "customer_id": customer, "bot_eligible": True,
         "at": {"$gte": now - timedelta(hours=1)}}
    )
    if recent > 30:
        await _send(db, container, connection, thread, config["handoff_message"], role="agent")
        _log_latency(t_webhook_start, thread["_id"])
        await db.dm_threads.update_one(
            {"_id": thread["_id"]},
            {
                "$set": {
                    "status": "NEEDS_HUMAN",
                    "escalation": {
                        "reason": "RATE_LIMITED",
                        "error": "Hourly message cap exceeded (30/hr)",
                        "escalated_at": now.isoformat(),
                    },
                    "updated_at": now,
                }
            },
        )
        await audit.record(
            db, actor="system", event_type="DM_RATE_LIMITED",
            payload={"thread_id": str(thread["_id"])}, user_id=user_id,
        )
        if name_task is not None:
            try:
                await name_task
            except Exception:
                pass
        return

    combined_text = "\n".join(extracted_texts).strip()
    user = await db.users.find_one({"_id": user_id}) or {}
    ws_id = resolve_workspace_id(user=user)
    user_settings = await settings_for_user(db, user_id, container.settings)

    from app.services.shared_post_resolver import SharedPostContextResolver
    from app.services.hybrid_rag import HybridRAG

    query_emb = None
    if combined_text:
        query_emb = await generate_embedding(combined_text, user_settings)

    resolver = SharedPostContextResolver(db, user_settings, container=container)
    resolved = await resolver.resolve(
        workspace_id=ws_id,
        message_text=combined_text,
        attachments=attachments_list,
        query_embedding=query_emb,
    )

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
        await _send(db, container, connection, thread, clarification, role="agent")
        _log_latency(t_webhook_start, thread["_id"])
        if name_task is not None:
            try:
                await name_task
            except Exception:
                pass
        return

    if not combined_text:
        if resolved:
            rag = HybridRAG(db, user_settings)
            h_context = await rag.retrieve(
                workspace_id=ws_id,
                user_id=user_id,
                query="Tell me about this product and offer",
                resolved_post_id=resolved.post_id,
            )
            offer = h_context.offer
            prod = h_context.products[0] if h_context.products else None

            post_title = resolved.title or (prod.get("product_name") if prod else "post")
            price_val = (offer.get("price") if offer else None) or (prod.get("price") if prod else None)
            discount_val = offer.get("discount") if offer else None
            valid_until = offer.get("valid_until") if offer else None

            reply_text = f"Thanks for sharing our post about '{post_title}'!"
            if price_val:
                reply_text += f" It is priced at ₹{price_val}."
            if discount_val:
                reply_text += f" Special offer: {discount_val} off"
                if valid_until:
                    reply_text += f" (valid until {valid_until})"
                reply_text += "!"
            reply_text += " How can we help you with it?"

            await _send(db, container, connection, thread, reply_text, role="agent")
            _log_latency(t_webhook_start, thread["_id"])
            if name_task is not None:
                try:
                    await name_task
                except Exception:
                    pass
            return

        has_share_attachment = any(
            str(a.get("type", "")).lower() in ("share", "story_share", "story_reply")
            or "permalink" in (a.get("payload") or {})
            for a in attachments_list
        )
        if has_share_attachment:
            ask_which = "Thanks for reaching out! Which product or offer can we help you with?"
            await _send(db, container, connection, thread, ask_which, role="agent")
        else:
            # Unreadable or unknown photo with no accompanying text
            await _send(
                db,
                container,
                connection,
                thread,
                "I can read text only. Please type your question.",
                role="agent",
            )
            await db.dm_threads.update_one({"_id": thread["_id"]}, {"$set": {"status": "NEEDS_HUMAN"}})
        _log_latency(t_webhook_start, thread["_id"])
        if name_task is not None:
            try:
                await name_task
            except Exception:
                pass
        return

    rag = HybridRAG(db, user_settings)
    h_context = await rag.retrieve(
        workspace_id=ws_id,
        user_id=user_id,
        query=combined_text,
        resolved_post_id=context_post_id,
        query_embedding=query_emb,
    )
    knowledge_payload = dict(config)
    knowledge_payload["prompt_context"] = h_context.prompt_context

    has_knowledge = bool(
        (config.get("knowledge") or "").strip()
        or h_context.resolved_post
        or h_context.semantic_chunks
    )

    if not has_knowledge:
        needs_human = False
        reply = config["handoff_message"]
        answer = None
        input_tokens = output_tokens = 0
        await db.dm_threads.update_one(
            {"_id": thread["_id"]},
            {
                "$set": {
                    "needs_attention": True,
                    "attention_reason": "NO_KNOWLEDGE",
                    "updated_at": now,
                }
            },
        )
        await audit.record(
            db,
            actor="agent",
            event_type="DM_NO_KNOWLEDGE",
            payload={"thread_id": str(thread["_id"])},
            user_id=user_id,
        )
    else:
        try:
            answer = await answer_dm(
                knowledge=knowledge_payload,
                history=thread["messages"][:-len(customer_messages_to_push)],
                message=combined_text,
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

    sent_ok = await _send(db, container, connection, thread, reply, role="agent")
    _log_latency(t_webhook_start, thread["_id"])

    if sent_ok and needs_human:
        escalation_doc = {
            "reason": (answer.escalation_reason if answer else None) or "REQUIRES_HUMAN",
            "customer_message": combined_text,
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

    if name_task is not None:
        try:
            await name_task
        except Exception:
            pass
