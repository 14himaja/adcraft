from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    mongodb_uri: str
    mongodb_db: str = "acm"
    jwt_secret: str = Field(min_length=32)
    token_encryption_key: str
    meta_mode: Literal["real", "fake"] = "real"
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_api_version: str = "v26.0"
    meta_redirect_uri: str = "http://localhost:3000/api/meta/callback"
    meta_login_config_id: str = ""
    instagram_positions: str = "stream"
    llm_provider: Literal["litellm", "gemini", "openrouter", "scripted"] = "litellm"
    openai_api_key: str = ""
    gemini_api_key: str = ""
    llm_primary_model: str = "gpt-5"
    llm_utility_model: str = "gpt-5"
    gemini_primary_model: str = "gemini-3.5-flash-lite"  # used when llm_provider is "gemini"
    gemini_utility_model: str = "gemini-3.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_model: str = "text-embedding-3-small"
    # OpenRouter: one key, models from several vendors. OPENROUTER_MODEL_FAMILY picks which pair is used.
    openrouter_api_key: str = ""
    openrouter_model_family: Literal["gemini", "openai"] = "gemini"
    # Cap on one reply. Without it OpenRouter reserves credit for the model maximum (e.g. 65k tokens) and
    # answers 402 on small balances; an ad draft needs about 1.5k.
    openrouter_max_tokens: int = 4096
    openrouter_gemini_primary_model: str = "google/gemini-3.5-flash-lite"
    openrouter_gemini_utility_model: str = "google/gemini-3.5-flash-lite"
    openrouter_openai_primary_model: str = "openai/gpt-5"
    openrouter_openai_utility_model: str = "openai/gpt-5"
    scripted_scenario: str = "ad_studio"  # app/agents/scenarios/<name>.json
    image_provider: Literal["gemini", "ai", "openai", "fake"] = "fake"
    image_model: str = "gemini-2.5-flash-image"
    openai_image_model: str = "gpt-image-1"
    openai_image_quality: str = "medium"  # low | medium | high | auto (high costs ~4x medium)
    meta_webhook_verify_token: str = ""  # the string typed into Meta's webhook setup page
    public_base_url: str = ""  # https origin Meta can fetch images from, e.g. https://api.example.com
    allow_organic_publish: bool = False  # real Instagram feed posts need this switch, like ad spend
    max_daily_budget_inr: int = 1000
    max_campaign_days: int = 30
    mock_metrics: bool = True
    fake_meta_fail_at: str = ""
    insights_interval_hours: int = 6
    allow_real_ad_spend: bool = False
    safe_mode_no_spend: bool = True

    @property
    def spend_allowed(self) -> bool:
        """Real delivery needs BOTH switches: ALLOW_REAL_AD_SPEND=true and SAFE_MODE_NO_SPEND=false."""
        return self.allow_real_ad_spend and not self.safe_mode_no_spend

    @property
    def instagram_position_list(self) -> list[str]:
        # Meta's Marketing API (v26) rejects the IG Explore placement, so an older .env value is ignored.
        return [p.strip() for p in self.instagram_positions.split(",") if p.strip() not in ("", "explore")]

    @model_validator(mode="after")
    def _production_safety(self) -> "Settings":
        if self.app_env == "production":
            if self.meta_mode == "fake":
                raise ValueError("META_MODE=fake is not allowed in production")
            if self.llm_provider == "scripted":
                raise ValueError("LLM_PROVIDER=scripted is not allowed in production")
            if self.fake_meta_fail_at:
                raise ValueError("FAKE_META_FAIL_AT is not allowed in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
