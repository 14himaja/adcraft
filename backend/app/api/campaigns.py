from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import ContainerDep, DbDep, SettingsDep, UserDep
from app.domain.ad_campaign import to_minor
from app.meta import publisher
from app.services import ad_campaigns as campaigns
from app.services import ad_fix, ad_lifecycle, ad_studio, organic
from app.services import insights as insights_service

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

CountryCode = Annotated[str, Field(pattern=r"^[A-Za-z]{2}$")]


class City(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    name: str = Field(max_length=100)


class Interest(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    name: str = Field(max_length=200)


class Audience(BaseModel):
    countries: list[CountryCode] = Field(default_factory=list, max_length=25)
    cities: list[City] = Field(default_factory=list, max_length=25)
    age_min: int = Field(18, ge=18, le=65)
    age_max: int = Field(65, ge=18, le=65)
    genders: Literal["ALL", "MEN", "WOMEN"] = "ALL"
    interests: list[Interest] = Field(default_factory=list, max_length=10)


class Variant(BaseModel):
    headline: str = Field(max_length=500)
    primary_text: str = Field(max_length=2000)
    description: str = Field("", max_length=500)
    call_to_action: str = Field(max_length=40)


class CampaignFields(BaseModel):
    """Partial campaign fields; rules that depend on settings or today's date are checked by the service."""

    title: str | None = Field(None, max_length=120)
    objective: str | None = Field(None, max_length=40)
    landing_url: str | None = Field(None, max_length=2048)
    audience: Audience | None = None
    daily_budget: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    start_date: date | None = None
    end_date: date | None = None
    variants: list[Variant] | None = Field(None, max_length=10)
    selected_variant: int | None = Field(None, ge=0)
    # The advertiser confirms the ad is not a job, housing, credit or political ad (Meta asks the same).
    not_special_category: bool | None = None
    publishing_destinations: dict[str, bool] | None = None
    selected_hashtags: list[str] | None = Field(None, max_length=5)
    custom_hashtags: list[str] | None = None
    ai_recommended_hashtags: list[str] | None = None

    def to_fields(self) -> dict:
        fields = {k: v for k, v in self.model_dump(exclude_unset=True).items() if v is not None}
        if "daily_budget" in fields:
            fields["daily_budget_minor"] = to_minor(fields.pop("daily_budget"))
        for key in ("start_date", "end_date"):
            if key in fields:
                fields[key] = fields[key].isoformat()
        if "audience" in fields:
            fields["audience"]["countries"] = [c.upper() for c in fields["audience"]["countries"]]
        return fields


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3)]


class DraftBody(BaseModel):
    idea: Annotated[Text, StringConstraints(max_length=2000)]


class ImproveBody(BaseModel):
    instruction: Annotated[Text, StringConstraints(max_length=500)]


class ChatBody(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class ConfirmBody(BaseModel):
    confirm: Literal[True]


@router.get("")
async def list_campaigns(user: UserDep, db: DbDep, settings: SettingsDep) -> list[dict]:
    return [campaigns.serialize(doc, settings) for doc in await campaigns.list_owned(db, user["_id"])]


@router.post("")
async def create_campaign(
    body: CampaignFields, user: UserDep, db: DbDep, settings: SettingsDep, container: ContainerDep
) -> dict:
    doc = await campaigns.create_draft(
        db, user_id=user["_id"], fields=body.to_fields(), settings=settings, clock=container.clock
    )
    return campaigns.serialize(doc, settings)


@router.post("/draft")
async def draft_campaign(body: DraftBody, user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    doc = await ad_studio.draft_campaign(db, user_id=user["_id"], idea=body.idea, container=container)
    return campaigns.serialize(doc, container.settings)


@router.post("/{campaign_id}/copy/improve")
async def improve_copy(
    campaign_id: str, body: ImproveBody, user: UserDep, db: DbDep, container: ContainerDep
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    doc = await ad_studio.improve_campaign_copy(db, campaign, body.instruction, container=container)
    return campaigns.serialize(doc, container.settings)


@router.post("/{campaign_id}/chat")
async def chat(campaign_id: str, body: ChatBody, user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    doc, reply, warnings = await ad_studio.chat_campaign(db, campaign, body.message, container=container)
    return {"campaign": campaigns.serialize(doc, container.settings), "reply": reply, "warnings": warnings}


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str, user: UserDep, db: DbDep, settings: SettingsDep) -> dict:
    return campaigns.serialize(await campaigns.get_owned(db, campaign_id, user["_id"]), settings)


@router.put("/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    body: CampaignFields,
    user: UserDep,
    db: DbDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    doc = await campaigns.update_draft(
        db, campaign, body.to_fields(), settings=settings, clock=container.clock
    )
    return campaigns.serialize(doc, settings)


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    await campaigns.delete_owned(db, campaign, container=container)
    return {"status": "DELETED", "id": campaign_id}


@router.post("/{campaign_id}/publish")
async def publish_campaign(
    campaign_id: str,
    body: ConfirmBody,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    await publisher.start_publish(db, campaign, container=container)
    await container.spawn(publisher.run_publish(db, campaign["_id"], container=container))
    return {"status": "PUBLISHING"}


@router.get("/{campaign_id}/publish")
async def get_publish_progress(
    campaign_id: str,
    user: UserDep,
    db: DbDep,
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    return campaign.get("publish") or {}


@router.post("/{campaign_id}/publish/resume")
async def resume_publish(
    campaign_id: str,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    await publisher.resume_publish(db, campaign, container=container)
    await container.spawn(publisher.run_publish(db, campaign["_id"], container=container))
    return {"status": "PUBLISHING"}


@router.post("/{campaign_id}/publish/discard")
async def discard_publish(
    campaign_id: str,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    doc = await publisher.discard_publish(db, campaign, container=container)
    return {"status": doc["status"]}


@router.post("/{campaign_id}/activate")
async def activate_campaign(
    campaign_id: str,
    body: ConfirmBody,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
    settings: SettingsDep,
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    doc = await ad_lifecycle.activate(db, campaign, container=container)
    return campaigns.serialize(doc, settings)


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
    settings: SettingsDep,
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    doc = await ad_lifecycle.pause(db, campaign, container=container)
    return campaigns.serialize(doc, settings)


@router.post("/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: str,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
    settings: SettingsDep,
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    doc = await ad_lifecycle.resume(db, campaign, container=container)
    return campaigns.serialize(doc, settings)


@router.get("/{campaign_id}/insights")
async def get_campaign_insights(
    campaign_id: str,
    user: UserDep,
    db: DbDep,
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    return campaign.get("insights") or {}


@router.post("/{campaign_id}/fix")
async def fix_campaign_issues(
    campaign_id: str,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    """Repair what Meta reported when the fix is inside the ad; the rest comes back as instructions."""
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    return await ad_fix.fix_issues(db, campaign, container=container)


class PostBody(BaseModel):
    targets: list[Literal["facebook_feed", "facebook_story", "instagram_feed", "instagram_story"]] = Field(
        min_length=1, max_length=4
    )


@router.post("/{campaign_id}/post")
async def post_campaign(
    campaign_id: str, body: PostBody, user: UserDep, db: DbDep, container: ContainerDep
) -> dict:
    """Post the ad's picture and text as normal free posts on the chosen targets (separate from the ad)."""
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    return await organic.post_campaign(db, container, user["_id"], campaign, list(body.targets))


@router.post("/{campaign_id}/insights/refresh")
async def refresh_campaign_insights(
    campaign_id: str,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    insights_service.check_refresh_rate_limit(campaign, container.clock)
    return await insights_service.collect(db, campaign, container=container)


@router.post("/{campaign_id}/duplicate")
async def duplicate_campaign(
    campaign_id: str,
    user: UserDep,
    db: DbDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> dict:
    campaign = await campaigns.get_owned(db, campaign_id, user["_id"])
    copy_doc = await campaigns.duplicate_campaign(
        db, campaign, settings=settings, clock=container.clock, actor="user"
    )
    return campaigns.serialize(copy_doc, settings)

