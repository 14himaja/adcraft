import base64
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

PINTEREST_AUTH_URL = "https://www.pinterest.com/oauth/"
PINTEREST_TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
PINTEREST_USER_URL = "https://api.pinterest.com/v5/user_account"
PINTEREST_BOARDS_URL = "https://api.pinterest.com/v5/boards"
PINTEREST_PINS_URL = "https://api.pinterest.com/v5/pins"
PINTEREST_DESC_MAX = 800
PINTEREST_TITLE_MAX = 100


class PinterestAdapter(SocialPlatformAdapter):
    platform_id = "pinterest"

    def definition(self, settings: Settings) -> PlatformDefinition:
        scopes = tuple(s.strip() for s in settings.pinterest_scopes.split(",") if s.strip())
        return PlatformDefinition(
            id="pinterest",
            name="Pinterest",
            description="Connect Pinterest Business accounts, discover Boards, and publish image Pins.",
            capabilities=PlatformCapabilities(
                supports_oauth=True,
                supports_refresh=True,
                supports_account_selection=True,
                supports_text_post=False,
                supports_image_post=True,
                supports_link_post=True,
                supports_title=True,
                requires_image=True,
                requires_target_selection=True,
                max_text_length=PINTEREST_DESC_MAX,
                target_label="Pinterest Board",
            ),
            required_env_vars=("PINTEREST_CLIENT_ID", "PINTEREST_CLIENT_SECRET", "PINTEREST_REDIRECT_URI"),
            required_scopes=scopes,
            ads_supported=False,
            ads_status="REQUIRES_API_APPROVAL",
            ads_note="Pinterest Ads requires API v5 Standard Access video review and supported billing region/partner onboarding.",
        )

    def is_configured(self, settings: Settings) -> bool:
        return bool(settings.pinterest_client_id and settings.pinterest_client_secret)

    def connect(self, settings: Settings, state: str, *, code_challenge: str | None = None) -> str:
        scopes = [s.strip() for s in settings.pinterest_scopes.split(",") if s.strip()]
        params = {
            "client_id": settings.pinterest_client_id,
            "redirect_uri": settings.pinterest_redirect_uri,
            "response_type": "code",
            "scope": ",".join(scopes),
            "state": state,
        }
        return f"{PINTEREST_AUTH_URL}?{urlencode(params)}"

    async def handle_callback(
        self,
        settings: Settings,
        code: str,
        *,
        now: datetime,
        code_verifier: str | None = None,
    ) -> OAuthTokenResult:
        body = await platform_request(
            "pinterest",
            "POST",
            PINTEREST_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.pinterest_redirect_uri,
            },
            auth=(settings.pinterest_client_id, settings.pinterest_client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        expires_in = int(body.get("expires_in") or 2592000)
        scope_str = body.get("scope") or ""
        return OAuthTokenResult(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_at=now + timedelta(seconds=expires_in),
            scopes=tuple(s for s in scope_str.replace(",", " ").split() if s),
            mode="real",
        )

    async def refresh_token(
        self, settings: Settings, refresh_token: str, *, now: datetime
    ) -> OAuthTokenResult | None:
        if not self.is_configured(settings):
            return None
        body = await platform_request(
            "pinterest",
            "POST",
            PINTEREST_TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            auth=(settings.pinterest_client_id, settings.pinterest_client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        expires_in = int(body.get("expires_in") or 2592000)
        scope_str = body.get("scope") or ""
        return OAuthTokenResult(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token") or refresh_token,
            expires_at=now + timedelta(seconds=expires_in),
            scopes=tuple(s for s in scope_str.replace(",", " ").split() if s),
            mode="real",
        )

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
                    account_id="pin_user_fake_1",
                    display_name="AdCraft Studio · Featured Products",
                    username="adcraftstudio",
                    account_type="business",
                    target_id="board_fake_1",
                    target_name="Featured Products",
                    target_type="pinterest_board",
                    can_publish=True,
                    extra={"privacy": "PUBLIC"},
                ),
                DiscoveredAccount(
                    account_id="pin_user_fake_1",
                    display_name="AdCraft Studio · Seasonal Campaigns",
                    username="adcraftstudio",
                    account_type="business",
                    target_id="board_fake_2",
                    target_name="Seasonal Campaigns",
                    target_type="pinterest_board",
                    can_publish=True,
                    extra={"privacy": "PUBLIC"},
                ),
            ]

        headers = {"Authorization": f"Bearer {access_token}"}
        user = await platform_request("pinterest", "GET", PINTEREST_USER_URL, headers=headers)
        username = user.get("username") or "pinterest_user"
        account_type = (user.get("account_type") or "business").lower()
        avatar = user.get("profile_image")

        boards_body = await platform_request(
            "pinterest",
            "GET",
            PINTEREST_BOARDS_URL,
            params={"page_size": 50},
            headers=headers,
        )
        boards = boards_body.get("items") or []
        if not boards:
            return [
                DiscoveredAccount(
                    account_id=str(user.get("id") or username),
                    display_name=f"@{username} (No Boards Found)",
                    username=username,
                    account_type=account_type,
                    target_id=None,
                    target_name=None,
                    target_type="pinterest_board",
                    avatar_url=avatar,
                    can_publish=False,
                    permission_note="Create at least one Pinterest Board before creating Pins.",
                )
            ]

        return [
            DiscoveredAccount(
                account_id=str(user.get("id") or username),
                display_name=f"{board.get('name', 'Board')} (@{username})",
                username=username,
                account_type=account_type,
                target_id=str(board["id"]),
                target_name=board.get("name") or str(board["id"]),
                target_type="pinterest_board",
                avatar_url=avatar,
                can_publish=True,
                extra={"privacy": board.get("privacy", "PUBLIC")},
            )
            for board in boards
        ]

    def validate_publish(self, content: PublishContent, connection: dict) -> list[str]:
        errors: list[str] = []
        board_id = content.target_id or connection.get("selected_target_id")
        if not board_id:
            errors.append("Select a Pinterest Board before publishing a Pin.")
        if not (content.image_url or content.image_bytes or content.image_id):
            errors.append("Pinterest Pins require an image.")
        if content.title and len(content.title) > PINTEREST_TITLE_MAX:
            errors.append(f"Pinterest Pin title exceeds {PINTEREST_TITLE_MAX} characters.")
        valid_tags, _ = validate_hashtag_list(content.hashtags or [])
        desc = format_caption_with_hashtags(content.text or "", valid_tags)
        if len(desc) > PINTEREST_DESC_MAX:
            errors.append(f"Pinterest Pin description exceeds {PINTEREST_DESC_MAX} characters.")
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
        board_id = content.target_id or connection.get("selected_target_id")
        board_name = content.target_name or connection.get("selected_target_name")
        valid_tags, _ = validate_hashtag_list(content.hashtags or [])
        description = format_caption_with_hashtags(content.text or "", valid_tags)[:PINTEREST_DESC_MAX]
        title = (content.title or description.splitlines()[0] if description else "New Pin")[:PINTEREST_TITLE_MAX]

        if connection.get("mode") == "fake":
            return PublishResult(
                platform="pinterest",
                status="PUBLISHED",
                platform_post_id=f"pin_fake_{abs(hash(title + description)) % 1000000}",
                post_url="https://www.pinterest.com/pin/fake/",
                target_id=board_id,
                target_name=board_name,
            )

        if content.image_bytes:
            media_source = {
                "source_type": "image_base64",
                "content_type": content.image_content_type or "image/jpeg",
                "data": base64.b64encode(content.image_bytes).decode("ascii"),
            }
        elif content.image_url:
            media_source = {"source_type": "image_url", "url": content.image_url}
        else:
            return PublishResult(
                platform="pinterest",
                status="FAILED",
                target_id=board_id,
                target_name=board_name,
                error="Pinterest Pin requires an image URL or image payload.",
                error_code="PINTEREST_IMAGE_REQUIRED",
            )

        payload: dict = {
            "board_id": str(board_id),
            "title": title,
            "description": description,
            "media_source": media_source,
        }
        if content.link_url:
            payload["link"] = content.link_url

        try:
            body = await platform_request(
                "pinterest",
                "POST",
                PINTEREST_PINS_URL,
                json=payload,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                retry_transient=False,
            )
            pin_id = str(body.get("id") or "")
            return PublishResult(
                platform="pinterest",
                status="PUBLISHED",
                platform_post_id=pin_id,
                post_url=f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else None,
                target_id=board_id,
                target_name=board_name,
            )
        except Exception as exc:
            return PublishResult(
                platform="pinterest",
                status="FAILED",
                target_id=board_id,
                target_name=board_name,
                error=str(exc)[:300],
                error_code="PINTEREST_POST_FAILED",
            )

