"""Pure validation for AI Ad Studio campaigns (spec 07 §4). No I/O."""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import ValidationError

from app.domain.models import AdVariant
from app.domain.rules import OBJECTIVES
from app.domain.validators import FIELD_VALIDATORS

VARIANT_KEYS = ("headline", "primary_text", "description", "call_to_action")
EDIT_VARIANTS_MIN, EDIT_VARIANTS_MAX = 1, 3
MIN_DAILY_BUDGET_INR = 50
_SPECIAL = re.compile(
    r"\b(housing|home loans?|mortgages?|credit cards?|loans?|insurance|jobs?|hiring|vacanc(?:y|ies)"
    r"|elections?|political|votes?|voting)\b",
    re.IGNORECASE,
)


def to_minor(rupees: float | int | Decimal) -> int:
    amount = rupees if isinstance(rupees, Decimal) else Decimal(str(rupees))
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_minor(minor: int) -> float:
    return float(Decimal(minor) / 100)


def special_category_reason(text: str) -> str | None:
    match = _SPECIAL.search(text or "")
    if match is None:
        return None
    return (
        f"mentions '{match.group(0)}': housing, credit, employment and political ads are a Meta "
        "special ad category, which this app cannot publish"
    )


def check_variants(raw: list[dict]) -> tuple[list[dict], list[str]]:
    """Returns (valid variants, problems). Same rules as finalize_assets, but 1-3 variants allowed."""
    count = len(raw)
    if not EDIT_VARIANTS_MIN <= count <= EDIT_VARIANTS_MAX:
        return [], [f"variants: expected {EDIT_VARIANTS_MIN}-{EDIT_VARIANTS_MAX}, got {count}"]
    valid, problems = [], []
    for i, variant in enumerate(raw):
        try:
            checked = AdVariant.model_validate({"image_concept": "", **variant})
        except ValidationError as exc:
            problems += [f"variants.{i}.{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
            continue
        valid.append({key: getattr(checked, key) for key in VARIANT_KEYS})
    return valid, problems


def _date(value) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _audience_errors(audience: dict) -> list[str]:
    errors = []
    if not (audience.get("countries") or audience.get("cities")):
        errors.append("audience: pick at least one country or city")
    if audience.get("age_min", 18) > audience.get("age_max", 65):
        errors.append("audience.age_max: must be greater than or equal to age_min")
    return errors


def _date_errors(doc: dict, changed: set[str], today: date, max_days: int) -> list[str]:
    errors = []
    start, end = _date(doc.get("start_date")), _date(doc.get("end_date"))
    if "start_date" in changed and start and start < today:
        errors.append("start_date: must be today or later")
    if changed & {"start_date", "end_date"} and start and end:
        if end <= start:
            errors.append("end_date: must be after start_date")
        elif (end - start).days > max_days:
            errors.append(f"end_date: campaign can run at most {max_days} days")
    return errors


def field_errors(
    doc: dict, changed: set[str], *, today: date, max_daily_budget_inr: int, max_days: int
) -> list[str]:
    """Problems with the fields in `changed` (and the cross-field rules they take part in)."""
    errors: list[str] = []
    if "landing_url" in changed and doc.get("landing_url"):
        if problem := FIELD_VALIDATORS["landing_url"](doc["landing_url"]):
            errors.append(f"landing_url: {problem}")
    budget = doc.get("daily_budget_minor")
    if "daily_budget_minor" in changed and budget is not None:
        if budget < MIN_DAILY_BUDGET_INR * 100:
            errors.append(f"daily_budget: must be at least ₹{MIN_DAILY_BUDGET_INR}")
        elif budget > max_daily_budget_inr * 100:
            errors.append(f"daily_budget: must be at most ₹{max_daily_budget_inr}")
    errors += _date_errors(doc, changed, today, max_days)
    if "audience" in changed:
        errors += _audience_errors(doc.get("audience") or {})
    variants = doc.get("variants") or []
    if "variants" in changed:
        errors += check_variants(variants)[1]
    if changed & {"variants", "selected_variant"} and variants:
        if not 0 <= doc.get("selected_variant", 0) < len(variants):
            errors.append(f"selected_variant: must point to one of the {len(variants)} variants")
    if "selected_hashtags" in changed:
        from app.domain.hashtags import validate_hashtag_list
        tags = doc.get("selected_hashtags")
        if tags is not None:
            if not isinstance(tags, list):
                errors.append("selected_hashtags: must be a list of strings")
            else:
                _, tag_errors = validate_hashtag_list(tags)
                errors += [f"selected_hashtags: {e}" for e in tag_errors]
    return errors


def missing_fields(doc: dict) -> list[str]:
    audience = doc.get("audience") or {}
    present = {
        "title": bool(doc.get("title")),
        "objective": doc.get("objective") in OBJECTIVES,
        "landing_url": bool(doc.get("landing_url")),
        "audience": bool(audience.get("countries") or audience.get("cities")),
        "daily_budget": bool(doc.get("daily_budget_minor")),
        "start_date": bool(doc.get("start_date")),
        "end_date": bool(doc.get("end_date")),
        "variants": bool(check_variants(doc.get("variants") or [])[0]),
        "image_id": bool(doc.get("image_id")),
    }
    return [name for name, ok in present.items() if not ok]
