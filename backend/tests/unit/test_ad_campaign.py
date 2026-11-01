from datetime import date
from decimal import Decimal

import pytest

from app.domain.ad_campaign import (
    check_variants,
    field_errors,
    from_minor,
    missing_fields,
    special_category_reason,
    to_minor,
)

TODAY = date(2026, 10, 6)
LIMITS = {"today": TODAY, "max_daily_budget_inr": 1000, "max_days": 30}
VARIANT = {
    "headline": "Learn Python in 30 days",
    "primary_text": "Hands-on lessons, real projects, mentor support.",
    "description": "Live classes",
    "call_to_action": "SIGN_UP",
}
COMPLETE = {
    "title": "Python Course Launch",
    "objective": "TRAFFIC",
    "landing_url": "https://synxa.ai/python",
    "audience": {"countries": ["IN"], "cities": [], "age_min": 18, "age_max": 24},
    "daily_budget_minor": 50000,
    "start_date": "2026-10-07",
    "end_date": "2026-10-10",
    "variants": [VARIANT],
    "selected_variant": 0,
    "image_id": "abc",
}


@pytest.mark.parametrize(
    ("rupees", "minor"), [(500, 50000), (0.1 + 0.2, 30), (Decimal("99.995"), 10000), (19.99, 1999)]
)
def test_to_minor_uses_decimal(rupees, minor):
    assert to_minor(rupees) == minor


def test_from_minor_returns_rupees():
    assert from_minor(50050) == 500.5


@pytest.mark.parametrize(
    "text",
    ["Cheap home loan for everyone", "We are hiring engineers", "Vote for change", "Best credit card"],
)
def test_special_categories_are_detected(text):
    assert special_category_reason(text)


def test_ordinary_ad_is_not_a_special_category():
    assert special_category_reason("Learn Python with live projects") is None
    assert special_category_reason("Jobsite boots on sale") is None  # whole words only


def test_valid_variants_pass():
    assert check_variants([VARIANT]) == ([VARIANT], [])


def test_variant_problems_name_the_field_and_rule():
    bad = {**VARIANT, "headline": "H" * 41, "call_to_action": "BUY_NOW"}
    valid, problems = check_variants([VARIANT, bad])
    assert valid == [VARIANT]
    assert any(p.startswith("variants.1.headline") and "40" in p for p in problems)
    assert any(p.startswith("variants.1.call_to_action") for p in problems)


def test_banned_claims_and_variant_count_are_checked():
    _, problems = check_variants([{**VARIANT, "primary_text": "Guaranteed job"}])
    assert "banned claim 'guaranteed'" in problems[0]
    assert check_variants([])[1] == ["variants: expected 1-3, got 0"]
    assert check_variants([VARIANT] * 4)[1] == ["variants: expected 1-3, got 4"]


def test_complete_campaign_has_no_missing_fields():
    assert missing_fields(COMPLETE) == []


def test_missing_fields_lists_what_publish_needs():
    doc = {**COMPLETE, "landing_url": "", "audience": {"countries": [], "cities": []}, "image_id": None}
    assert missing_fields(doc) == ["landing_url", "audience", "image_id"]
    assert missing_fields({}) == [
        "title",
        "objective",
        "landing_url",
        "audience",
        "daily_budget",
        "start_date",
        "end_date",
        "variants",
        "image_id",
    ]


def test_invalid_variants_count_as_missing():
    assert missing_fields({**COMPLETE, "variants": [{**VARIANT, "headline": ""}]}) == ["variants"]


def test_field_errors_checks_only_changed_fields():
    doc = {**COMPLETE, "start_date": "2026-10-01"}  # already in the past
    assert field_errors(doc, {"title"}, **LIMITS) == []
    assert field_errors(doc, {"start_date"}, **LIMITS) == ["start_date: must be today or later"]


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"landing_url": "http://synxa.ai"}, "landing_url: must be an https:// URL"),
        ({"daily_budget_minor": 4999}, "daily_budget: must be at least ₹50"),
        ({"daily_budget_minor": 100001}, "daily_budget: must be at most ₹1000"),
        ({"end_date": "2026-10-07"}, "end_date: must be after start_date"),
        ({"end_date": "2026-11-07"}, "end_date: campaign can run at most 30 days"),
        ({"audience": {"countries": [], "cities": [], "age_min": 18, "age_max": 65}}, "audience: pick"),
        ({"audience": {"countries": ["IN"], "age_min": 40, "age_max": 30}}, "audience.age_max"),
        ({"selected_variant": 1}, "selected_variant: must point to one of the 1 variants"),
        ({"variants": [{**VARIANT, "description": "D" * 31}]}, "variants.0.description"),
    ],
)
def test_field_errors(changes, error):
    errors = field_errors({**COMPLETE, **changes}, set(changes), **LIMITS)
    assert len(errors) == 1 and errors[0].startswith(error), errors
