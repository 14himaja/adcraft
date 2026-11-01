from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.hashtag_agent import (
    HashtagRecommendationAgent,
    HashtagRecommendationResult,
    generate_ad_hashtags,
)
from app.api.deps import ContainerDep, DbDep, UserDep
from app.domain.hashtags import (
    MAX_HASHTAGS,
    PREDEFINED_HASHTAGS,
    normalize_hashtag,
    validate_hashtag_list,
)
from app.errors import AppError
from app.services.user_ai import settings_for_user

router = APIRouter(prefix="/hashtags", tags=["hashtags"])


class InvalidHashtag(AppError):
    status, code = 422, "INVALID_HASHTAG"


class CustomHashtagBody(BaseModel):
    hashtag: str = Field(min_length=1, max_length=60)


class ValidateHashtagsBody(BaseModel):
    hashtags: list[str] = Field(default_factory=list)


class RecommendHashtagsBody(BaseModel):
    title: str | None = None
    caption: str | None = None
    text: str | None = None
    headline: str | None = None
    primary_text: str | None = None
    description: str | None = None
    business_category: str | None = None
    product_service: str | None = None
    image_prompt: str | None = None
    objective: str | None = None
    audience: dict | list | str | None = None
    platform: str | None = None


@router.get("")
async def get_hashtags(
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
    query: str | None = None,
    context: str | None = None,
) -> dict:
    """Get predefined hashtags library, AI recommended hashtags, and the user's custom hashtags."""
    user_doc = await db.users.find_one({"_id": user["_id"]}) or {}
    custom_hashtags = user_doc.get("custom_hashtags") or []

    settings = await settings_for_user(db, user["_id"], container.settings)
    context_text = context or query or ""
    agent = HashtagRecommendationAgent()
    result = await agent.recommend(caption=context_text, settings=settings)

    return {
        "categories": PREDEFINED_HASHTAGS,
        "recommended_hashtags": [item.model_dump() for item in result.recommended_hashtags],
        "alternative_hashtags": result.alternative_hashtags,
        "ai_recommended": [item.tag for item in result.recommended_hashtags],
        "custom": custom_hashtags,
        "max_limit": MAX_HASHTAGS,
    }


@router.post("/recommend")
async def recommend_hashtags_endpoint(
    body: RecommendHashtagsBody, user: UserDep, db: DbDep, container: ContainerDep
) -> dict:
    """Dynamically generate AI-recommended hashtags based on ad context."""
    settings = await settings_for_user(db, user["_id"], container.settings)
    agent = HashtagRecommendationAgent()
    ad_title = body.title or body.headline or ""
    ad_caption = body.caption or body.primary_text or body.text or body.description or ""
    result = await agent.recommend(
        title=ad_title,
        caption=ad_caption,
        business_category=body.business_category or "",
        product_service=body.product_service or "",
        campaign_objective=body.objective or "",
        target_audience=body.audience,
        ad_image=body.image_prompt,
        platform=body.platform,
        settings=settings,
    )
    return {
        "advertisement_title": result.advertisement_title,
        "business_category": result.business_category,
        "recommended_hashtags": [item.model_dump() for item in result.recommended_hashtags],
        "alternative_hashtags": result.alternative_hashtags,
        "ai_recommended": [item.tag for item in result.recommended_hashtags],
        "max_limit": MAX_HASHTAGS,
    }


@router.post("/custom")
async def add_custom_hashtag(body: CustomHashtagBody, user: UserDep, db: DbDep) -> dict:
    """Validate and persist a custom hashtag for the authenticated user."""
    normalized, err = normalize_hashtag(body.hashtag)
    if err:
        raise InvalidHashtag(err)

    user_doc = await db.users.find_one({"_id": user["_id"]}) or {}
    existing: list[str] = user_doc.get("custom_hashtags") or []

    # Case-insensitive duplicate check
    if any(h.lower() == normalized.lower() for h in existing):
        return {"hashtag": normalized, "custom": existing, "message": "Hashtag already in your custom collection"}

    updated = [*existing, normalized]
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"custom_hashtags": updated}})
    return {"hashtag": normalized, "custom": updated}


@router.delete("/custom/{tag}")
async def delete_custom_hashtag(tag: str, user: UserDep, db: DbDep) -> dict:
    """Remove a custom hashtag from the user's saved collection."""
    clean_tag = tag if tag.startswith("#") else f"#{tag}"
    user_doc = await db.users.find_one({"_id": user["_id"]}) or {}
    existing: list[str] = user_doc.get("custom_hashtags") or []
    updated = [h for h in existing if h.lower() != clean_tag.lower()]
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"custom_hashtags": updated}})
    return {"deleted": clean_tag, "custom": updated}


@router.post("/validate")
async def validate_hashtags_endpoint(body: ValidateHashtagsBody) -> dict:
    """Validate, normalize and deduplicate a list of hashtags."""
    valid, errors = validate_hashtag_list(body.hashtags)
    return {"valid": valid, "errors": errors, "is_valid": len(errors) == 0}
