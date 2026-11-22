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

FACEBOOK_POST_MAX = 63206


class FacebookAdapter(SocialPlatformAdapter):
    platform_id = "facebook"

    def definition(self, settings: Settings) -> PlatformDefinition:
        return PlatformDefinition(
            id="facebook",
            name="Facebook",
            description="Connect Facebook Pages for organic Page posts, media, and Meta business management.",
            capabilities=PlatformCapabilities(
                supports_oauth=True,
                supports_refresh=False,
                supports_account_selection=True,
                supports_text_post=True,
                supports_image_post=True,
                supports_link_post=True,
                supports_title=False,
                requires_image=False,
                requires_target_selection=True,
                max_text_length=FACEBOOK_POST_MAX,
                target_label="Facebook Page",
            ),
            required_env_vars=("META_APP_ID", "META_APP_SECRET", "META_REDIRECT_URI"),
            required_scopes=META_PLATFORM_SCOPES,
            ads_supported=True,
            ads_status="ACTIVE" if (settings.meta_app_id or settings.meta_mode == "fake") else "REQUIRES_CREDENTIALS",
            ads_note="Facebook paid campaigns run through your connected Meta Ad Account.",
        )

    def is_configured(self, settings: Settings) -> bool:
        return bool(settings.meta_app_id and settings.meta_app_secret)

    def use_fake_mode(self, settings: Settings) -> bool:
        return settings.meta_mode == "fake" or settings.social_oauth_mode == "fake"

    def connect(self, settings: Settings, state: str, *, code_challenge: str | None = None) -> str:
        return meta_auth_url(settings, state, platform="facebook")

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
        except MetaError as exc:
            raise translate_meta_error(exc, platform="facebook") from exc

        return [
            DiscoveredAccount(
                account_id=page["id"],
                display_name=page.get("name") or page["id"],
                username=page.get("name"),
                account_type="page",
                target_id=page["id"],
                target_name=page.get("name") or page["id"],
                target_type="facebook_page",
                can_publish=True,
            )
            for page in pages
        ]

    def validate_publish(self, content: PublishContent, connection: dict) -> list[str]:
        errors: list[str] = []
        target = content.target_id or connection.get("selected_target_id") or connection.get("platform_account_id")
        if not target:
            errors.append("Select a Facebook Page before publishing.")
        valid_tags, _ = validate_hashtag_list(content.hashtags or [])
        formatted = format_caption_with_hashtags(content.text or "", valid_tags)
        if not formatted.strip() and not (content.image_url or content.image_id) and not content.link_url:
            errors.append("Facebook post requires text, a link, or an image.")
        if len(formatted) > FACEBOOK_POST_MAX:
            errors.append(f"Facebook post exceeds {FACEBOOK_POST_MAX} characters.")
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
                platform="facebook",
                status="FAILED",
                target_id=target,
                target_name=content.target_name or connection.get("selected_target_name"),
                error="Organic publishing is switched off on this server (ALLOW_ORGANIC_PUBLISH=false).",
                error_code="ORGANIC_PUBLISH_NOT_READY",
            )
        valid_tags, _ = validate_hashtag_list(content.hashtags or [])
        caption = format_caption_with_hashtags(content.text or "", valid_tags)[:FACEBOOK_POST_MAX]
        _, writer = meta_gateway(access_token, settings, mode=mode, container=container)
        try:
            if content.image_url:
                post_id = await writer.publish_facebook_photo(str(target), content.image_url, caption)
            else:
                post_id = await writer.publish_facebook_feed_post(str(target), caption, link=content.link_url)
        except (MetaError, TimeoutError, ConnectionError) as exc:
            return PublishResult(
                platform="facebook",
                status="FAILED",
                target_id=target,
                target_name=content.target_name or connection.get("selected_target_name"),
                error=str(exc)[:300],
                error_code="FACEBOOK_POST_FAILED",
            )
        return PublishResult(
            platform="facebook",
            status="PUBLISHED",
            platform_post_id=str(post_id),
            post_url=f"https://facebook.com/{post_id}",
            target_id=str(target),
            target_name=content.target_name or connection.get("selected_target_name"),
        )

