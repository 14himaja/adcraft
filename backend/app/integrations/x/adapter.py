from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.config import Settings
from app.domain.hashtags import format_caption_with_hashtags, validate_hashtag_list
from app.integrations.base.adapter import SocialPlatformAdapter
from app.integrations.base.http import platform_request
from app.integrations.base.models import (
    DiscoveredAccount,
    OAuthTokenResult,
    PlatformCapabilities,
    PlatformDefinition,
    PublishContent,
    PublishResult,
)

X_AUTH_URL = "https://x.com/i/oauth2/authorize"
X_TOKEN_URL = "https://api.x.com/2/oauth2/token"
X_REVOKE_URL = "https://api.x.com/2/oauth2/revoke"
X_ME_URL = "https://api.x.com/2/users/me"
X_TWEETS_URL = "https://api.x.com/2/tweets"
X_CHAR_MAX = 280


class XAdapter(SocialPlatformAdapter):
    platform_id = "x"

    def definition(self, settings: Settings) -> PlatformDefinition:
        scopes = tuple(s.strip() for s in settings.x_scopes.split(",") if s.strip())
        return PlatformDefinition(
            id="x",
            name="X",
            description="Connect X (Twitter) via OAuth 2.0 PKCE for posts, links, and media publishing.",
            capabilities=PlatformCapabilities(
                supports_oauth=True,
                supports_refresh=True,
                supports_account_selection=True,
                supports_text_post=True,
                supports_image_post=True,
                supports_link_post=True,
                supports_title=False,
                requires_image=False,
                requires_target_selection=False,
                max_text_length=X_CHAR_MAX,
                target_label="X Account",
            ),
            required_env_vars=("X_CLIENT_ID", "X_CLIENT_SECRET", "X_REDIRECT_URI"),
            required_scopes=scopes,
            ads_supported=False,
            ads_status="REQUIRES_API_APPROVAL",
            ads_note="X Ads requires separate manual X Ads API v12 approval, OAuth 1.0a, and a USD funding instrument.",
        )

    def is_configured(self, settings: Settings) -> bool:
        return bool(settings.x_client_id)

    def connect(self, settings: Settings, state: str, *, code_challenge: str | None = None) -> str:
        scopes = [s.strip() for s in settings.x_scopes.split(",") if s.strip()]
        params = {
            "response_type": "code",
            "client_id": settings.x_client_id,
            "redirect_uri": settings.x_redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": code_challenge or "",
            "code_challenge_method": "S256",
        }
        return f"{X_AUTH_URL}?{urlencode(params)}"

    async def handle_callback(
        self,
        settings: Settings,
        code: str,
        *,
        now: datetime,
        code_verifier: str | None = None,
    ) -> OAuthTokenResult:
        auth = (settings.x_client_id, settings.x_client_secret) if settings.x_client_secret else None
        data = {
            "code": code,
            "grant_type": "authorization_code",
            "client_id": settings.x_client_id,
            "redirect_uri": settings.x_redirect_uri,
            "code_verifier": code_verifier or "",
        }
        body = await platform_request(
            "x",
            "POST",
            X_TOKEN_URL,
            data=data,
            auth=auth,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        expires_in = int(body.get("expires_in") or 7200)
        scope_str = body.get("scope") or ""
        return OAuthTokenResult(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_at=now + timedelta(seconds=expires_in),
            scopes=tuple(s for s in scope_str.split() if s),
            mode="real",
        )

    async def refresh_token(
        self, settings: Settings, refresh_token: str, *, now: datetime
    ) -> OAuthTokenResult | None:
        if not self.is_configured(settings):
            return None
        auth = (settings.x_client_id, settings.x_client_secret) if settings.x_client_secret else None
        body = await platform_request(
            "x",
            "POST",
            X_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.x_client_id,
            },
            auth=auth,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        expires_in = int(body.get("expires_in") or 7200)
        scope_str = body.get("scope") or ""
        return OAuthTokenResult(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token") or refresh_token,
            expires_at=now + timedelta(seconds=expires_in),
            scopes=tuple(s for s in scope_str.split() if s),
            mode="real",
        )

    async def revoke_token(self, settings: Settings, access_token: str) -> bool:
        if not self.is_configured(settings):
            return False
        auth = (settings.x_client_id, settings.x_client_secret) if settings.x_client_secret else None
        try:
            await platform_request(
                "x",
                "POST",
                X_REVOKE_URL,
                data={
                    "token": access_token,
                    "client_id": settings.x_client_id,
                    "token_type_hint": "access_token",
                },
                auth=auth,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                retry_transient=False,
            )
            return True
        except Exception:
            return False

    async def get_accounts(
        self,
        access_token: str,
        settings: Settings,
        *,
        connection: dict | None = None,
        container=None,
    ) -> list[DiscoveredAccount]:
        if (connection or {}).get("mode") == "fake":
            return [
                DiscoveredAccount(
                    account_id="x_user_fake_1",
                    display_name="AdCraft Demo (@adcraft_demo)",
                    username="adcraft_demo",
                    account_type="profile",
                    target_id="x_user_fake_1",
                    target_name="@adcraft_demo",
                    target_type="x_profile",
                    can_publish=True,
                )
            ]

        body = await platform_request(
            "x",
            "GET",
            X_ME_URL,
            params={"user.fields": "profile_image_url,username,name"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user = body.get("data") or {}
        username = user.get("username") or ""
        display = user.get("name") or (f"@{username}" if username else "X Account")
        return [
            DiscoveredAccount(
                account_id=str(user.get("id", "")),
                display_name=f"{display} (@{username})" if username else display,
                username=username,
                account_type="profile",
                target_id=str(user.get("id", "")),
                target_name=f"@{username}" if username else display,
                target_type="x_profile",
                avatar_url=user.get("profile_image_url"),
                can_publish=True,
            )
        ]

    def _compose_text(self, content: PublishContent) -> str:
        valid_tags, _ = validate_hashtag_list(content.hashtags or [])
        base = format_caption_with_hashtags(content.text or "", valid_tags)
        if content.link_url and content.link_url not in base:
            base = f"{base}\n{content.link_url}".strip()
        return base

    def validate_publish(self, content: PublishContent, connection: dict) -> list[str]:
        errors: list[str] = []
        text = self._compose_text(content)
        if not text.strip():
            errors.append("X post requires text or a link.")
        if len(text) > X_CHAR_MAX:
            errors.append(f"X post exceeds {X_CHAR_MAX} characters ({len(text)}/{X_CHAR_MAX}).")
        return errors

    async def publish(
        self,
        access_token: str,
        content: PublishContent,
        connection: dict,
        settings: Settings,
        *,
        container=None,
    ) -> PublishResult:
        target = content.target_id or connection.get("selected_target_id") or connection.get("platform_account_id")
        target_name = content.target_name or connection.get("selected_target_name") or connection.get("account_username")
        text = self._compose_text(content)[:X_CHAR_MAX]

        if connection.get("mode") == "fake":
            return PublishResult(
                platform="x",
                status="PUBLISHED",
                platform_post_id=f"x_post_{abs(hash(text)) % 1000000}",
                post_url="https://x.com/adcraft_demo/status/fake",
                target_id=target,
                target_name=target_name,
            )

        try:
            body = await platform_request(
                "x",
                "POST",
                X_TWEETS_URL,
                json={"text": text},
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                retry_transient=False,
            )
            data = body.get("data") or {}
            tweet_id = str(data.get("id") or "")
            return PublishResult(
                platform="x",
                status="PUBLISHED",
                platform_post_id=tweet_id,
                post_url=f"https://x.com/i/web/status/{tweet_id}" if tweet_id else None,
                target_id=target,
                target_name=target_name,
            )
        except Exception as exc:
            return PublishResult(
                platform="x",
                status="FAILED",
                target_id=target,
                target_name=target_name,
                error=str(exc)[:300],
                error_code="X_POST_FAILED",
            )

