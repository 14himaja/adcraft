from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.domain.rules import (
    CTA_ALLOWED,
    DESCRIPTION_MAX,
    HEADLINE_MAX,
    PRIMARY_TEXT_MAX,
    VARIANTS_MAX,
    VARIANTS_MIN,
)
from app.domain.validators import policy_violation

CTA = Literal[CTA_ALLOWED]


class AdVariantDraft(BaseModel):
    headline: str = Field(description=f"At most {HEADLINE_MAX} characters")
    primary_text: str = Field(description=f"Instagram caption, at most {PRIMARY_TEXT_MAX} characters")
    description: str = Field(description=f"At most {DESCRIPTION_MAX} characters")
    call_to_action: CTA
    image_concept: str = Field("", description="Idea for a 1:1 or 4:5 Instagram feed image")


class AssetDraft(BaseModel):
    variants: list[AdVariantDraft]


class AdVariant(AdVariantDraft):
    headline: str = Field(min_length=1, max_length=HEADLINE_MAX)
    primary_text: str = Field(min_length=1, max_length=PRIMARY_TEXT_MAX)
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX)

    @field_validator("headline", "primary_text", "description")
    @classmethod
    def _no_policy_violation(cls, value: str) -> str:
        if problem := policy_violation(value):
            raise ValueError(problem)
        return value


def finalize_assets(draft: AssetDraft) -> list[AdVariant]:
    count = len(draft.variants)
    if not VARIANTS_MIN <= count <= VARIANTS_MAX:
        raise ValueError(f"variants: expected {VARIANTS_MIN}-{VARIANTS_MAX}, got {count}")
    variants, problems = [], []
    for i, draft_variant in enumerate(draft.variants):
        try:
            variants.append(AdVariant.model_validate(draft_variant.model_dump()))
        except ValidationError as exc:
            problems += [f"variants.{i}.{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
    if problems:
        raise ValueError("\n".join(problems))
    return variants
