from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

AdPlatformId = Literal["meta_ads", "linkedin_ads"]
AdReadinessStatus = Literal[
    "READY",
    "CONNECTED_REQUIRES_SETUP",
    "REQUIRES_API_APPROVAL",
    "REQUIRES_BILLING_SETUP",
    "NOT_CONNECTED",
]


@dataclass(frozen=True)
class AdAccountInfo:
    ad_account_id: str
    name: str
    currency: str
    status: str
    billing_configured: bool = False


@dataclass(frozen=True)
class AdCampaignSpec:
    ad_account_id: str
    name: str
    objective: str
    daily_budget_minor: int
    currency: str
    targeting: dict[str, Any] = field(default_factory=dict)
    creative: dict[str, Any] = field(default_factory=dict)
    status: Literal["PAUSED", "ACTIVE"] = "PAUSED"


@dataclass(frozen=True)
class AdPlatformReadiness:
    id: AdPlatformId
    social_platform: str
    name: str
    status: AdReadinessStatus
    organic_connected: bool
    api_approved: bool
    billing_supported_india: str
    min_daily_budget: str
    available_features: tuple[str, ...]
    gated_features: tuple[str, ...]
    requirements_note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "social_platform": self.social_platform,
            "name": self.name,
            "status": self.status,
            "organic_connected": self.organic_connected,
            "api_approved": self.api_approved,
            "billing_supported_india": self.billing_supported_india,
            "min_daily_budget": self.min_daily_budget,
            "available_features": list(self.available_features),
            "gated_features": list(self.gated_features),
            "requirements_note": self.requirements_note,
        }


class AdPlatformAdapter(ABC):
    """Future-phase interface for paid advertising platforms (kept separate from organic publishing)."""

    ad_platform_id: AdPlatformId

    @abstractmethod
    async def list_ad_accounts(self, access_token: str) -> list[AdAccountInfo]: ...

    @abstractmethod
    async def create_campaign(self, access_token: str, spec: AdCampaignSpec) -> str: ...

    @abstractmethod
    async def set_campaign_status(
        self, access_token: str, campaign_id: str, status: Literal["ACTIVE", "PAUSED"]
    ) -> None: ...

    @abstractmethod
    async def get_performance(self, access_token: str, campaign_id: str) -> dict[str, Any]: ...

