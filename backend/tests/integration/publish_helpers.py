from datetime import timedelta

from bson import ObjectId

from app.meta.connections import save_token, select_assets
from app.meta.fake import FAKE_ACCOUNT, FAKE_INSTAGRAM, FAKE_PAGES
from app.services.ad_campaigns import create_draft
from app.services.image_store import generate_campaign_image
from tests.api.campaign_bodies import MANUAL

FIELDS = {
    **{k: v for k, v in MANUAL.items() if k != "daily_budget"},
    "daily_budget_minor": 50_000,
}


async def connect(db, user_id, container) -> None:
    settings, clock = container.settings, container.clock
    await save_token(
        db,
        user_id=user_id,
        token="fake-token",
        expires_at=clock.now() + timedelta(days=60),
        mode="fake",
        settings=settings,
        clock=clock,
    )
    await select_assets(
        db,
        user_id,
        ad_account=FAKE_ACCOUNT,
        page=FAKE_PAGES[0],
        instagram=FAKE_INSTAGRAM["page_fake_1"],
        clock=clock,
    )


async def ready_draft(db, container, *, user_id=None, connected=True, **overrides) -> dict:
    """A complete DRAFT with a generated image; the owner is connected to the fake Meta."""
    user_id = user_id or ObjectId()
    if connected:
        await connect(db, user_id, container)
    settings, clock = container.settings, container.clock
    doc = await create_draft(
        db, user_id=user_id, fields={**FIELDS, **overrides}, settings=settings, clock=clock
    )
    return await generate_campaign_image(
        db, doc, container.image_generator, extra="", settings=settings, clock=clock
    )
