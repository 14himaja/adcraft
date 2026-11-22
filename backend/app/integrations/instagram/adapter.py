import asyncio
from datetime import datetime

from app.config import Settings
from app.domain.hashtags import format_caption_with_hashtags, validate_hashtag_list
from app.integrations.base.adapter import SocialPlatformAdapter
from app.integrations.base.models import (
    DiscoveredAccount,
    OAuthTokenResult,
    PlatformCapabilities,
    PlatformDefinition,
    PublishContent,
    PublishResult,
)
from app.integrations.meta_shared import (
    META_PLATFORM_SCOPES,
    meta_auth_url,
    meta_exchange_code,
    meta_gateway,
    translate_meta_error,
)
from app.meta.errors import MetaError

INSTAGRAM_CAPTION_MAX = 2200


class InstagramAdapter(SocialPlatformAdapter):
    platform_id = "instagram"

    def definition(self, settings: Settings) -> PlatformDefinition:
        return PlatformDefinition(
            id="instagram",
            name="Instagram",
            description="Publish feed photos and manage Instagram Business & Creator accounts via Meta.",
            capabilities=PlatformCapabilities(
                supports_oauth=True,
                supports_refresh=False,
                supports_account_selection=True,
                supports_text_post=False,
                supports_image_post=True,
                supports_link_post=False,
                supports_title=False,
                requires_image=True,
                requires_target_selection=True,
                max_text_length=INSTAGRAM_CAPTION_MAX,
                target_label="Instagram Business Account",
            ),
            required_env_vars=("META_APP_ID", "META_APP_SECRET", "META_REDIRECT_URI"),
            required_scopes=META_PLATFORM_SCOPES,
            ads_supported=True,
            ads_status="ACTIVE" if (settings.meta_app_id or settings.meta_mode == "fake") else "REQUIRES_CREDENTIALS",
            ads_note="Instagram paid placements run through your connected Meta Ad Account.",
        )

    def is_configured(self, settings: Settings) -> bool:
        return bool(settings.meta_app_id and settings.meta_app_secret)

    def use_fake_mode(self, settings: Settings) -> bool:
        return settings.meta_mode == "fake" or settings.social_oauth_mode == "fake"

    def connect(self, settings: Settings, state: str, *, code_challenge: str | None = None) -> str:
        return meta_auth_url(settings, state, platform="instagram")

    async def handle_callback(
        self,
        settings: Settings,
        code: str,
        *,
        now: datetime,
        code_verifier: str | None = None,
    ) -> OAuthTokenResult:
        return await meta_exchange_code(settings, code, now=now)

    async def get_accounts(
        self,
        access_token: str,
        settings: Settings,
        *,
        connection: dict | None = None,
        container=None,
    ) -> list[DiscoveredAccount]:
        mode = (connection or {}).get("mode", "real")
        reader, _ = meta_gateway(access_token, settings, mode=mode, container=container)
        try:
            pages = await reader.list_pages()
            linked = await asyncio.gather(*(reader.instagram_account_for_page(p["id"]) for p in pages))
        except MetaError as exc:
            raise translate_meta_error(exc, platform="instagram") from exc

        accounts: list[DiscoveredAccount] = []
        for page, ig in zip(pages, linked, strict=True):
            if ig:
                accounts.append(
                    DiscoveredAccount(
                        account_id=ig["id"],
                        display_name=f"@{ig['username']}",
                        username=ig["username"],
                        account_type="business",
                        target_id=ig["id"],
                        target_name=f"@{ig['username']}",
                        target_type="instagram_account",
                        avatar_url=ig.get("profile_picture_url"),
                        can_publish=True,
                        extra={"page_id": page["id"], "page_name": page["name"]},
                    )
                )
        return accounts

    def validate_publish(self, content: PublishContent, connection: dict) -> list[str]:
        errors: list[str] = []
        target = content.target_id or connection.get("selected_target_id") or connection.get("platform_account_id")
        if not target:
            errors.append("Select an Instagram Business or Creator account before publishing.")
        if not (content.image_url or content.image_id):
            errors.append("Instagram organic posts require an image.")
        valid_tags, _ = validate_hashtag_list(content.hashtags or [])
        formatted = format_caption_with_hashtags(content.text or "", valid_tags)
        if len(formatted) > INSTAGRAM_CAPTION_MAX:
            errors.append(f"Instagram caption exceeds {INSTAGRAM_CAPTION_MAX} characters.")
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
        mode = connection.get("mode", "real")
        if mode == "real" and not settings.allow_organic_publish:
            return PublishResult(
                platform="instagram",
                status="FAILED",
                target_id=target,
                target_name=content.target_name or connection.get("selected_target_name"),
                error="Organic publishing is switched off on this server (ALLOW_ORGANIC_PUBLISH=false).",
                error_code="ORGANIC_PUBLISH_NOT_READY",
            )
        if not content.image_url:
            return PublishResult(
                platform="instagram",
                status="FAILED",
                target_id=target,
                error="Instagram requires a public image URL (set PUBLIC_BASE_URL).",
                error_code="ORGANIC_PUBLISH_NOT_READY",
            )
        valid_tags, _ = validate_hashtag_list(content.hashtags or [])
        caption = format_caption_with_hashtags(content.text or "", valid_tags)[:INSTAGRAM_CAPTION_MAX]
        _, writer = meta_gateway(access_token, settings, mode=mode, container=container)
        try:
            media_id = await writer.publish_photo(str(target), content.image_url, caption)
        except (MetaError, TimeoutError, ConnectionError) as exc:
            return PublishResult(
                platform="instagram",
                status="FAILED",
                target_id=target,
                target_name=content.target_name or connection.get("selected_target_name"),
                error=str(exc)[:300],
                error_code="INSTAGRAM_POST_FAILED",
            )
        return PublishResult(
            platform="instagram",
            status="PUBLISHED",
            platform_post_id=str(media_id),
            post_url=f"https://instagram.com/p/{media_id}",
            target_id=str(target),
            target_name=content.target_name or connection.get("selected_target_name"),
        )

