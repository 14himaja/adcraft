from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.integrations.base.models import (
    DiscoveredAccount,
    OAuthTokenResult,
    PlatformDefinition,
    PlatformId,
    PublishContent,
    PublishResult,
)

EXPIRY_WARNING = timedelta(days=7)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class SocialPlatformAdapter(ABC):
    """Common interface implemented by each social media platform adapter."""

    platform_id: PlatformId

    @abstractmethod
    def definition(self, settings: Settings) -> PlatformDefinition: ...

    @abstractmethod
    def is_configured(self, settings: Settings) -> bool: ...

    def use_fake_mode(self, settings: Settings) -> bool:
        return settings.social_oauth_mode == "fake"

    @abstractmethod
    def connect(self, settings: Settings, state: str, *, code_challenge: str | None = None) -> str:
        """Build the official OAuth authorization URL."""

    @abstractmethod
    async def handle_callback(
        self,
        settings: Settings,
        code: str,
        *,
        now: datetime,
        code_verifier: str | None = None,
    ) -> OAuthTokenResult:
        """Exchange the OAuth authorization code for tokens."""

    async def refresh_token(
        self, settings: Settings, refresh_token: str, *, now: datetime
    ) -> OAuthTokenResult | None:
        return None

    async def revoke_token(self, settings: Settings, access_token: str) -> bool:
        return False

    @abstractmethod
    async def get_accounts(
        self,
        access_token: str,
        settings: Settings,
        *,
        connection: dict | None = None,
        container=None,
    ) -> list[DiscoveredAccount]:
        """Retrieve authorized profile, pages, organizations, boards, or subreddits."""

    @abstractmethod
    def validate_publish(self, content: PublishContent, connection: dict) -> list[str]:
        """Validate platform-specific payload and target requirements before publishing."""

    @abstractmethod
    async def publish(
        self,
        access_token: str,
        content: PublishContent,
        connection: dict,
        settings: Settings,
        *,
        container=None,
    ) -> PublishResult:
        """Publish organic content to the selected platform."""

    def get_connection_status(self, connection: dict | None, *, now: datetime, settings: Settings) -> dict:
        defn = self.definition(settings)
        configured = self.is_configured(settings) or self.use_fake_mode(settings)
        base = {
            "platform": defn.id,
            "name": defn.name,
            "description": defn.description,
            "configured": configured,
            "required_env_vars": list(defn.required_env_vars),
            "required_scopes": list(defn.required_scopes),
            "capabilities": {
                "supports_oauth": defn.capabilities.supports_oauth,
                "supports_refresh": defn.capabilities.supports_refresh,
                "supports_account_selection": defn.capabilities.supports_account_selection,
                "supports_text_post": defn.capabilities.supports_text_post,
                "supports_image_post": defn.capabilities.supports_image_post,
                "supports_video_post": defn.capabilities.supports_video_post,
                "supports_link_post": defn.capabilities.supports_link_post,
                "supports_title": defn.capabilities.supports_title,
                "supports_scheduling": defn.capabilities.supports_scheduling,
                "requires_image": defn.capabilities.requires_image,
                "requires_target_selection": defn.capabilities.requires_target_selection,
                "max_text_length": defn.capabilities.max_text_length,
                "supported_media_types": list(defn.capabilities.supported_media_types),
                "max_image_size_mb": defn.capabilities.max_image_size_mb,
                "max_video_size_mb": defn.capabilities.max_video_size_mb,
                "target_label": defn.capabilities.target_label,
            },
            "advertising": {
                "supported": defn.ads_supported,
                "status": defn.ads_status,
                "note": defn.ads_note,
            },
        }
        if connection is None:
            return {
                **base,
                "status": "NOT_CONNECTED",
                "connected": False,
            }

        expires_at = connection.get("token_expires_at")
        now_utc = ensure_utc(now)
        status = connection.get("status", "ACTIVE")
        expiring_soon = False
        expires_iso = None
        if expires_at is not None:
            exp_utc = ensure_utc(expires_at)
            expires_iso = exp_utc.isoformat()
            if status == "ACTIVE" and exp_utc <= now_utc:
                status = "EXPIRED"
            elif status == "ACTIVE" and exp_utc - now_utc <= EXPIRY_WARNING:
                expiring_soon = True

        return {
            **base,
            "status": status,
            "connected": status == "ACTIVE",
            "mode": connection.get("mode", "real"),
            "expires_at": expires_iso,
            "expiring_soon": expiring_soon,
            "has_refresh_token": bool(connection.get("refresh_token_ciphertext")),
            "platform_account_id": connection.get("platform_account_id"),
            "account_display_name": connection.get("account_display_name"),
            "account_username": connection.get("account_username"),
            "account_type": connection.get("account_type"),
            "selected_target_id": connection.get("selected_target_id"),
            "selected_target_name": connection.get("selected_target_name"),
            "selected_target_type": connection.get("selected_target_type"),
            "granted_scopes": list(connection.get("scopes") or []),
            "metadata": connection.get("metadata") or {},
            "last_error": connection.get("last_error"),
            "connected_at": (
                ensure_utc(connection["created_at"]).isoformat() if connection.get("created_at") else None
            ),
            "updated_at": (
                ensure_utc(connection["updated_at"]).isoformat() if connection.get("updated_at") else None
            ),
        }

