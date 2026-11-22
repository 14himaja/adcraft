from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

PlatformId = Literal["facebook", "instagram", "linkedin"]
ConnectionStatus = Literal["NOT_CONNECTED", "ACTIVE", "EXPIRED", "REVOKED", "ERROR"]

PLATFORMS_ORDER: tuple[PlatformId, ...] = (
    "facebook",
    "instagram",
    "linkedin",
)


@dataclass(frozen=True)
class PlatformCapabilities:
    supports_oauth: bool = True
    supports_refresh: bool = False
    supports_account_selection: bool = False
    supports_text_post: bool = True
    supports_image_post: bool = False
    supports_link_post: bool = False
    supports_title: bool = False
    requires_image: bool = False
    requires_target_selection: bool = False
    max_text_length: int = 2000
    target_label: str = "Account"


@dataclass(frozen=True)
class PlatformDefinition:
    id: PlatformId
    name: str
    description: str
    capabilities: PlatformCapabilities
    required_env_vars: tuple[str, ...]
    required_scopes: tuple[str, ...]
    ads_supported: bool = False
    ads_status: str = "FUTURE_PHASE"
    ads_note: str = ""


@dataclass(frozen=True)
class OAuthTokenResult:
    access_token: str
    expires_at: datetime | None = None
    refresh_token: str | None = None
    scopes: tuple[str, ...] = ()
    token_type: str = "bearer"
    mode: Literal["real", "fake"] = "real"
    raw_account_hint: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiscoveredAccount:
    account_id: str
    display_name: str
    account_type: str
    username: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    target_type: str | None = None
    avatar_url: str | None = None
    can_publish: bool = True
    permission_note: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "display_name": self.display_name,
            "account_type": self.account_type,
            "username": self.username,
            "target_id": self.target_id or self.account_id,
            "target_name": self.target_name or self.display_name,
            "target_type": self.target_type or self.account_type,
            "avatar_url": self.avatar_url,
            "can_publish": self.can_publish,
            "permission_note": self.permission_note,
            "extra": self.extra,
        }


@dataclass
class PublishContent:
    text: str = ""
    title: str | None = None
    link_url: str | None = None
    image_id: str | None = None
    image_url: str | None = None
    image_bytes: bytes | None = None
    image_content_type: str | None = None
    hashtags: list[str] = field(default_factory=list)
    target_id: str | None = None
    target_name: str | None = None
    media_type: str = "TEXT"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PublishResult:
    platform: PlatformId
    status: Literal["PUBLISHED", "FAILED"]
    platform_post_id: str | None = None
    post_url: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    error: str | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "status": self.status,
            "platform_post_id": self.platform_post_id,
            "post_url": self.post_url,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "error": self.error,
            "error_code": self.error_code,
        }

