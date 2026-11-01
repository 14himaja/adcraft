import re
from collections.abc import Callable
from datetime import date
from urllib.parse import urlparse

from app.domain.rules import AGE_MAX, AGE_MIN, BANNED_PHRASES, OBJECTIVES

_PERSONAL_ATTRIBUTE = re.compile(r"\bare you\b", re.IGNORECASE)


def policy_violation(text: str) -> str | None:
    lowered = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            return f"contains banned claim '{phrase}'"
    if _PERSONAL_ATTRIBUTE.search(text):
        return "asserts a personal attribute ('are you ...'), which Meta ad policy does not allow"
    return None


def _text(low: int, high: int) -> Callable[[object], str | None]:
    def check(value: object) -> str | None:
        ok = isinstance(value, str) and low <= len(value.strip()) <= high
        return None if ok else f"must be {low}-{high} characters"

    return check


def _https_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return "must be a URL of at most 2048 characters"
    parsed = urlparse(value)
    return None if parsed.scheme == "https" and parsed.netloc else "must be an https:// URL"


def _objective(value: object) -> str | None:
    return None if value in OBJECTIVES else f"must be one of {sorted(OBJECTIVES)}"


def _countries(value: object) -> str | None:
    ok = (
        isinstance(value, list)
        and value
        and all(isinstance(c, str) and len(c) == 2 and c.isalpha() and c.isupper() for c in value)
    )
    return None if ok else "must be a list of 2-letter country codes, e.g. ['IN']"


def _positive_int(value: object) -> str | None:
    ok = isinstance(value, int) and not isinstance(value, bool) and value > 0
    return None if ok else "must be a positive whole number in minor units (e.g. paise)"


def _currency(value: object) -> str | None:
    ok = isinstance(value, str) and len(value) == 3 and value.isalpha() and value.isupper()
    return None if ok else "must be a 3-letter currency code, e.g. INR"


def _iso_date(value: object) -> str | None:
    try:
        date.fromisoformat(value)  # type: ignore[arg-type]
        return None
    except (TypeError, ValueError):
        return "must be a date in YYYY-MM-DD format"


def _age(value: object) -> str | None:
    ok = isinstance(value, int) and not isinstance(value, bool) and AGE_MIN <= value <= AGE_MAX
    return None if ok else f"must be between {AGE_MIN} and {AGE_MAX}"


def _identifier(value: object) -> str | None:
    return None if isinstance(value, str) and value.strip() else "must be a non-empty id"


FIELD_VALIDATORS: dict[str, Callable[[object], str | None]] = {
    "product_name": _text(1, 100),
    "product_description": _text(1, 1000),
    "landing_url": _https_url,
    "objective": _objective,
    "geo_countries": _countries,
    "audience_description": _text(1, 500),
    "budget_total_minor": _positive_int,
    "currency": _currency,
    "start_date": _iso_date,
    "end_date": _iso_date,
    "age_min": _age,
    "age_max": _age,
    "tone": _text(1, 100),
    "ad_account_id": _identifier,
    "page_id": _identifier,
    "instagram_user_id": _identifier,
    "image_id": _identifier,
}


def _as_date(value: object) -> date | None:
    return None if _iso_date(value) else date.fromisoformat(value)  # type: ignore[arg-type]


def cross_field_errors(values: dict, *, today: date, min_daily_budget_minor: int | None) -> dict[str, str]:
    errors: dict[str, str] = {}
    start, end = _as_date(values.get("start_date")), _as_date(values.get("end_date"))
    if start and start < today:
        errors["start_date"] = "must be today or later"
    if start and end and end <= start:
        errors["end_date"] = "must be after start_date"
    if values.get("age_min", AGE_MIN) > values.get("age_max", AGE_MAX):
        errors["age_max"] = "must be greater than or equal to age_min"
    budget = values.get("budget_total_minor")
    if start and end and end > start and min_daily_budget_minor and isinstance(budget, int):
        days = (end - start).days
        if budget < min_daily_budget_minor * days:
            errors["budget_total_minor"] = (
                f"is below Meta's minimum ({min_daily_budget_minor} per day x {days} days)"
            )
    return errors
