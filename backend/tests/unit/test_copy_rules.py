import pytest
from pydantic import ValidationError

from app.domain.models import AdVariant, AssetDraft, finalize_assets
from app.domain.validators import policy_violation

GOOD = {
    "headline": "Ship reviews 2x faster",
    "primary_text": "AI code review that catches bugs before your teammates do.",
    "description": "Free 14-day trial",
    "call_to_action": "LEARN_MORE",
    "image_concept": "Developer smiling at a green CI check, square",
}


def variant(**overrides):
    return {**GOOD, **overrides}


def test_valid_variant_is_accepted():
    assert AdVariant.model_validate(GOOD).headline == GOOD["headline"]


def test_headline_of_exactly_40_is_accepted():
    AdVariant.model_validate(variant(headline="H" * 40))


def test_headline_over_40_is_rejected():
    with pytest.raises(ValidationError, match="headline"):
        AdVariant.model_validate(variant(headline="H" * 41))


def test_caption_over_125_is_rejected():
    with pytest.raises(ValidationError, match="primary_text"):
        AdVariant.model_validate(variant(primary_text="P" * 126))


def test_description_over_30_is_rejected():
    with pytest.raises(ValidationError, match="description"):
        AdVariant.model_validate(variant(description="D" * 31))


def test_empty_headline_is_rejected():
    with pytest.raises(ValidationError):
        AdVariant.model_validate(variant(headline=""))


def test_unknown_cta_is_rejected():
    with pytest.raises(ValidationError, match="call_to_action"):
        AdVariant.model_validate(variant(call_to_action="BUY_NOW"))


def test_banned_claim_is_rejected():
    with pytest.raises(ValidationError, match="banned claim"):
        AdVariant.model_validate(variant(headline="Guaranteed results"))


def test_personal_attribute_is_rejected():
    with pytest.raises(ValidationError, match="personal attribute"):
        AdVariant.model_validate(variant(primary_text="Are you a Python developer? Try it."))


def test_clean_text_has_no_policy_violation():
    assert policy_violation("Review code faster with AI") is None


def test_finalize_accepts_two_or_three_variants():
    assert len(finalize_assets(AssetDraft(variants=[GOOD, GOOD]))) == 2
    assert len(finalize_assets(AssetDraft(variants=[GOOD, GOOD, GOOD]))) == 3


@pytest.mark.parametrize("count", [1, 4])
def test_finalize_rejects_wrong_number_of_variants(count):
    with pytest.raises(ValueError, match="expected 2-3"):
        finalize_assets(AssetDraft(variants=[GOOD] * count))


def test_finalize_lists_every_problem():
    with pytest.raises(ValueError) as exc:
        finalize_assets(AssetDraft(variants=[variant(headline="H" * 41), variant(description="D" * 31)]))
    message = str(exc.value)
    assert "variants.0.headline" in message
    assert "variants.1.description" in message
