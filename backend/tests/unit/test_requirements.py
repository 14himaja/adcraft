from datetime import date

import pytest

from app.domain.requirements import (
    REQUIRED_FIELDS,
    FieldStatus,
    Requirements,
    apply_extraction,
    confirm_fields,
    missing_fields,
    ready_for_planning,
    set_system_field,
)
from app.domain.validators import FIELD_VALIDATORS, cross_field_errors
from tests.factories import COMPLETE_BRIEF, complete_requirements, extraction

TODAY = date(2026, 10, 6)


def test_empty_requirements_report_every_required_field_missing():
    assert missing_fields(Requirements.empty()) == list(REQUIRED_FIELDS)


def test_optional_defaults_start_confirmed():
    field = Requirements.empty().fields["age_min"]
    assert (field.value, field.status) == (18, FieldStatus.CONFIRMED)


def test_stated_valid_value_is_confirmed():
    req = apply_extraction(Requirements.empty(), extraction({"currency": "INR"}))
    assert req.fields["currency"].status == FieldStatus.CONFIRMED


def test_inferred_value_is_only_proposed():
    req = apply_extraction(Requirements.empty(), extraction({"geo_countries": ["IN"]}, stated=False))
    assert req.fields["geo_countries"].status == FieldStatus.PROPOSED


def test_invalid_value_is_marked_with_a_reason():
    req = apply_extraction(Requirements.empty(), extraction({"landing_url": "http://insecure.example.com"}))
    field = req.fields["landing_url"]
    assert field.status == FieldStatus.INVALID
    assert "https" in field.error


def test_unknown_field_is_ignored():
    req = apply_extraction(Requirements.empty(), extraction({"favourite_colour": "blue"}))
    assert "favourite_colour" not in req.fields


def test_model_cannot_set_system_fields():
    req = apply_extraction(Requirements.empty(), extraction({"page_id": "attacker_page"}))
    assert req.fields["page_id"].status == FieldStatus.MISSING


def test_guess_does_not_overwrite_confirmed_value():
    req = apply_extraction(Requirements.empty(), extraction({"currency": "INR"}))
    req = apply_extraction(req, extraction({"currency": "USD"}, stated=False))
    assert req.fields["currency"].value == "INR"


def test_confirm_promotes_only_proposed_fields():
    req = apply_extraction(Requirements.empty(), extraction({"geo_countries": ["IN"]}, stated=False))
    req = apply_extraction(req, extraction({"landing_url": "http://bad.example.com"}))
    req = confirm_fields(req, ["geo_countries", "landing_url"])
    assert req.fields["geo_countries"].status == FieldStatus.CONFIRMED
    assert req.fields["landing_url"].status == FieldStatus.INVALID


def test_set_system_field_rejects_non_system_fields():
    with pytest.raises(ValueError):
        set_system_field(Requirements.empty(), "budget_total_minor", "1")


def test_complete_and_consistent_requirements_are_ready():
    assert ready_for_planning(complete_requirements(), today=TODAY, min_daily_budget_minor=8_000)


def test_end_before_start_is_not_ready():
    req = apply_extraction(complete_requirements(), extraction({"end_date": "2026-10-09"}))
    assert not ready_for_planning(req, today=TODAY, min_daily_budget_minor=None)
    assert "end_date" in cross_field_errors(req.values(), today=TODAY, min_daily_budget_minor=None)


def test_start_in_the_past_is_not_ready():
    req = apply_extraction(complete_requirements(), extraction({"start_date": "2026-10-01"}))
    assert not ready_for_planning(req, today=TODAY, min_daily_budget_minor=None)


def test_budget_below_meta_minimum_is_not_ready():
    # 30 days x 200,000 paise minimum = 6,000,000 > 5,000,000
    assert not ready_for_planning(complete_requirements(), today=TODAY, min_daily_budget_minor=200_000)


def test_bool_is_not_a_budget():
    assert FIELD_VALIDATORS["budget_total_minor"](True) is not None


def test_complete_brief_values_all_pass_their_validators():
    assert all(FIELD_VALIDATORS[k](v) is None for k, v in COMPLETE_BRIEF.items())
