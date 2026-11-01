from bson import ObjectId

from app.domain.requirements import (
    ExtractedField,
    Extraction,
    Requirements,
    apply_extraction,
    set_system_field,
)

COMPLETE_BRIEF = {
    "product_name": "ReviewBot",
    "product_description": "AI code review for engineering teams",
    "landing_url": "https://reviewbot.example.com",
    "objective": "TRAFFIC",
    "geo_countries": ["IN"],
    "audience_description": "Software developers",
    "budget_total_minor": 5_000_000,
    "currency": "INR",
    "start_date": "2026-10-10",
    "end_date": "2026-11-09",
}
SYSTEM_VALUES = {
    "ad_account_id": "act_1",
    "page_id": "page_1",
    "instagram_user_id": "ig_1",
    "image_id": "img_1",
}


def extraction(values: dict, stated: bool = True) -> Extraction:
    return Extraction(
        fields=[ExtractedField(name=k, value=v, stated_by_user=stated) for k, v in values.items()]
    )


def complete_requirements() -> Requirements:
    req = apply_extraction(Requirements.empty(), extraction(COMPLETE_BRIEF))
    for name, value in SYSTEM_VALUES.items():
        req = set_system_field(req, name, value)
    return req


async def insert_campaign(db, *, status="COLLECTING", rev=0, current_version=0, user_id=None) -> ObjectId:
    doc = {
        "user_id": user_id or ObjectId(),
        "status": status,
        "rev": rev,
        "current_version": current_version,
        "approved_version": None,
        "meta": {},
    }
    return (await db.campaigns.insert_one(doc)).inserted_id


SAMPLE_VARIANTS = [
    {
        "headline": "Ship reviews 2x faster",
        "primary_text": "AI code review that catches bugs before your teammates do.",
        "description": "Free 14-day trial",
        "call_to_action": "LEARN_MORE",
        "image_concept": "Green CI check, square",
    },
    {
        "headline": "Fewer bugs in review",
        "primary_text": "Let AI handle the first pass so humans review what matters.",
        "description": "Start free today",
        "call_to_action": "SIGN_UP",
        "image_concept": "Pull request with AI notes",
    },
]
