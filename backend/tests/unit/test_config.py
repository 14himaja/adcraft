import pytest
from pydantic import ValidationError

from app.config import Settings

BASE = {
    "mongodb_uri": "mongodb://localhost:27017",
    "jwt_secret": "s" * 32,
    "token_encryption_key": "k",
}


def test_missing_mongodb_uri_is_rejected(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret="s" * 32, token_encryption_key="k")


def test_short_jwt_secret_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**BASE, "jwt_secret": "short"})


def test_defaults():
    s = Settings(_env_file=None, **BASE)
    assert s.meta_api_version == "v26.0"
    assert s.mongodb_db == "acm"
    assert s.instagram_position_list == ["stream"]
    assert s.mock_metrics is True


def test_production_refuses_fake_meta():
    with pytest.raises(ValidationError, match="fake"):
        Settings(_env_file=None, **BASE, app_env="production", meta_mode="fake")


def test_production_refuses_scripted_llm():
    with pytest.raises(ValidationError, match="scripted"):
        Settings(_env_file=None, **BASE, app_env="production", meta_mode="real", llm_provider="scripted")


def test_production_refuses_fault_injection():
    with pytest.raises(ValidationError, match="fail"):
        Settings(
            _env_file=None,
            **BASE,
            app_env="production",
            meta_mode="real",
            llm_provider="litellm",
            fake_meta_fail_at="ADSET",
        )


def test_ad_studio_defaults():
    s = Settings(_env_file=None, **BASE)
    assert (s.image_provider, s.image_model) == ("fake", "gemini-2.5-flash-image")
    assert (s.max_daily_budget_inr, s.max_campaign_days) == (1000, 30)
    assert s.scripted_scenario == "ad_studio"


def test_image_provider_accepts_gemini_and_rejects_unknown():
    assert Settings(_env_file=None, **BASE, image_provider="gemini").image_provider == "gemini"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **BASE, image_provider="dalle")


@pytest.mark.parametrize(
    ("allow", "safe", "expected"),
    [(False, True, False), (True, True, False), (False, False, False), (True, False, True)],
)
def test_spend_needs_allow_real_spend_and_safe_mode_off(allow, safe, expected):
    s = Settings(_env_file=None, **BASE, allow_real_ad_spend=allow, safe_mode_no_spend=safe)
    assert s.spend_allowed is expected


def test_deprecated_explore_placement_is_ignored():
    # Meta v26 rejects IG Explore ("IG Explore placement is deprecated"); old .env files still list it.
    s = Settings(_env_file=None, **BASE, instagram_positions="stream,explore")
    assert s.instagram_position_list == ["stream"]
