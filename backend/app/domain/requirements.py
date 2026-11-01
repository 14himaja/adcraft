from datetime import date
from enum import StrEnum

from pydantic import BaseModel

from app.domain.validators import FIELD_VALIDATORS, cross_field_errors

REQUIRED_FIELDS = (
    "product_name",
    "product_description",
    "landing_url",
    "objective",
    "geo_countries",
    "audience_description",
    "budget_total_minor",
    "currency",
    "start_date",
    "end_date",
    "ad_account_id",
    "page_id",
    "instagram_user_id",
    "image_id",
)
SYSTEM_FIELDS = frozenset({"ad_account_id", "page_id", "instagram_user_id", "image_id"})
OPTIONAL_DEFAULTS = {"age_min": 18, "age_max": 65}


class FieldStatus(StrEnum):
    MISSING = "missing"
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    INVALID = "invalid"


class FieldState(BaseModel):
    value: object = None
    status: FieldStatus = FieldStatus.MISSING
    error: str | None = None


class ExtractedField(BaseModel):
    name: str
    value: str | int | list[str] | None
    stated_by_user: bool


class Extraction(BaseModel):
    fields: list[ExtractedField]


class Requirements(BaseModel):
    fields: dict[str, FieldState]

    @classmethod
    def empty(cls) -> "Requirements":
        fields = {name: FieldState() for name in REQUIRED_FIELDS}
        fields |= {
            name: FieldState(value=v, status=FieldStatus.CONFIRMED) for name, v in OPTIONAL_DEFAULTS.items()
        }
        return cls(fields=fields)

    def values(self) -> dict:
        return {k: f.value for k, f in self.fields.items() if f.status == FieldStatus.CONFIRMED}


def apply_extraction(req: Requirements, extraction: Extraction) -> Requirements:
    fields = dict(req.fields)
    for item in extraction.fields:
        if item.name not in FIELD_VALIDATORS or item.name in SYSTEM_FIELDS:
            continue
        current = fields.get(item.name, FieldState())
        if current.status == FieldStatus.CONFIRMED and not item.stated_by_user:
            continue
        if error := FIELD_VALIDATORS[item.name](item.value):
            fields[item.name] = FieldState(value=item.value, status=FieldStatus.INVALID, error=error)
        else:
            status = FieldStatus.CONFIRMED if item.stated_by_user else FieldStatus.PROPOSED
            fields[item.name] = FieldState(value=item.value, status=status)
    return Requirements(fields=fields)


def confirm_fields(req: Requirements, names: list[str]) -> Requirements:
    fields = dict(req.fields)
    for name in names:
        if name in fields and fields[name].status == FieldStatus.PROPOSED:
            fields[name] = fields[name].model_copy(update={"status": FieldStatus.CONFIRMED})
    return Requirements(fields=fields)


def set_system_field(req: Requirements, name: str, value: str) -> Requirements:
    if name not in SYSTEM_FIELDS:
        raise ValueError(f"{name} is not a system field")
    if error := FIELD_VALIDATORS[name](value):
        raise ValueError(f"{name} {error}")
    return Requirements(fields={**req.fields, name: FieldState(value=value, status=FieldStatus.CONFIRMED)})


def missing_fields(req: Requirements) -> list[str]:
    return [name for name in REQUIRED_FIELDS if req.fields[name].status != FieldStatus.CONFIRMED]


def ready_for_planning(req: Requirements, *, today: date, min_daily_budget_minor: int | None) -> bool:
    return not missing_fields(req) and not cross_field_errors(
        req.values(), today=today, min_daily_budget_minor=min_daily_budget_minor
    )
