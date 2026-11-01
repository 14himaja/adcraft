"""Idea -> AI draft (+ image) and AI copy rewrite for DRAFT campaigns (spec 07 §6)."""

from app.agents.ad_drafter import CHAT_KEEP, chat_edit, draft_ad, improve_copy
from app.agents.hashtag_agent import generate_ad_hashtags
from app.container import Container
from app.media.images import ImageGenerationFailed
from app.meta.connections import MetaNotConnected, require_connection
from app.meta.errors import MetaAuthExpired
from app.meta.ports import AdsReader
from app.services.ad_campaigns import create_draft, require_editable, update_draft
from app.services.image_store import generate_campaign_image
from app.services.user_ai import settings_for_user


async def _reader(db, user_id, container: Container) -> AdsReader | None:
    try:
        connection = await require_connection(db, user_id, clock=container.clock)
    except (MetaNotConnected, MetaAuthExpired):
        return None  # the drafter adds a "connect Meta" warning
    return container.gateway_for(connection)[0]


async def draft_campaign(db, *, user_id, idea: str, container: Container) -> dict:
    settings, clock = await settings_for_user(db, user_id, container.settings), container.clock
    reader = await _reader(db, user_id, container)
    draft = await draft_ad(idea, settings=settings, clock=clock, reader=reader)
    v0 = (draft.fields.get("variants") or [{}])[0]
    ai_hashtags = await generate_ad_hashtags(
        {
            "idea": idea,
            "title": draft.fields.get("title", ""),
            "headline": v0.get("headline", ""),
            "primary_text": v0.get("primary_text", ""),
            "description": v0.get("description", ""),
            "image_prompt": draft.extra.get("image_prompt", ""),
            "audience": draft.fields.get("audience", {}),
            "objective": draft.fields.get("objective", ""),
        },
        settings=settings,
    )
    if not draft.fields.get("selected_hashtags"):
        draft.fields["selected_hashtags"] = ai_hashtags[:5]
    draft.extra["ai_recommended_hashtags"] = ai_hashtags[:5]
    campaign = await create_draft(
        db,
        user_id=user_id,
        fields=draft.fields,
        extra=draft.extra,
        settings=settings,
        clock=clock,
        actor="agent",
    )
    try:
        return await generate_campaign_image(
            db, campaign, container.image_generator, extra="", settings=settings, clock=clock
        )
    except ImageGenerationFailed as exc:
        warning = f"Image generation failed: {exc.message}. Use Regenerate image or upload your own."
        return await update_draft(
            db,
            campaign,
            {"warnings": [*campaign["warnings"], warning]},
            settings=settings,
            clock=clock,
            actor="system",
        )


async def chat_campaign(
    db, campaign: dict, message: str, *, container: Container
) -> tuple[dict, str, list[str]]:
    """One chat turn: the AI turns the message into field changes, saved like a manual edit."""
    require_editable(campaign)
    settings, clock = await settings_for_user(db, campaign["user_id"], container.settings), container.clock
    reader = await _reader(db, campaign["user_id"], container)
    edit = await chat_edit(campaign, message, settings=settings, clock=clock, reader=reader)
    turn = [{"role": "user", "text": message}, {"role": "assistant", "text": edit.reply}]
    chat = [*(campaign.get("chat") or []), *turn][-CHAT_KEEP:]
    doc = await update_draft(
        db, campaign, {**edit.changes, "chat": chat}, settings=settings, clock=clock, actor="agent"
    )
    if "image_prompt" in edit.changes or not doc.get("image_id"):  # retry when the draft still has none
        try:
            doc = await generate_campaign_image(
                db, doc, container.image_generator, extra="", settings=settings, clock=clock
            )
        except ImageGenerationFailed as exc:
            edit.warnings.append(f"Image generation failed: {exc.message}. Try again or upload your own.")
    return doc, edit.reply, edit.warnings


async def improve_campaign_copy(db, campaign: dict, instruction: str, *, container: Container) -> dict:
    require_editable(campaign)
    settings = await settings_for_user(db, campaign["user_id"], container.settings)
    variants = await improve_copy(campaign.get("variants") or [], instruction, settings=settings)
    return await update_draft(
        db,
        campaign,
        {"variants": variants},
        settings=settings,
        clock=container.clock,
        actor="agent",
    )
