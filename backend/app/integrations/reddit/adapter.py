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

REDDIT_AUTH_URL = "https://www.reddit.com/api/v1/authorize"
REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_REVOKE_URL = "https://www.reddit.com/api/v1/revoke_token"
REDDIT_ME_URL = "https://oauth.reddit.com/api/v1/me"
REDDIT_SUBREDDITS_URL = "https://oauth.reddit.com/subreddits/mine/subscriber"
REDDIT_SUBMIT_URL = "https://oauth.reddit.com/api/submit"
REDDIT_TITLE_MAX = 300
REDDIT_TEXT_MAX = 40000


class RedditAdapter(SocialPlatformAdapter):
    platform_id = "reddit"

    def definition(self, settings: Settings) -> PlatformDefinition:
        scopes = tuple(s.strip() for s in settings.reddit_scopes.split(",") if s.strip())
        return PlatformDefinition(
            id="reddit",
            name="Reddit",
            description="Connect Reddit accounts, discover subscribed subreddits, and submit text or link posts.",
            capabilities=PlatformCapabilities(
                supports_oauth=True,
                supports_refresh=True,
                supports_account_selection=True,
                supports_text_post=True,
                supports_image_post=False,
                supports_link_post=True,
                supports_title=True,
                requires_image=False,
                requires_target_selection=True,
                max_text_length=REDDIT_TEXT_MAX,
                target_label="Subreddit",
            ),
            required_env_vars=("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_REDIRECT_URI"),
            required_scopes=scopes,
            ads_supported=False,
            ads_status="REQUIRES_BILLING_SETUP",
            ads_note="Reddit Ads API v3 uses Business Ad Accounts and USD card billing ($5/day min per Ad Group).",
        )

    def is_configured(self, settings: Settings) -> bool:
        return bool(settings.reddit_client_id and settings.reddit_client_secret)

    def _headers(self, settings: Settings, access_token: str | None = None) -> dict[str, str]:
        headers = {"User-Agent": settings.reddit_user_agent or "AdCraft/1.0"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return headers

    def connect(self, settings: Settings, state: str, *, code_challenge: str | None = None) -> str:
        scopes = [s.strip() for s in settings.reddit_scopes.split(",") if s.strip()]
        params = {
            "client_id": settings.reddit_client_id,
            "response_type": "code",
            "state": state,
            "redirect_uri": settings.reddit_redirect_uri,
            "duration": "permanent",
            "scope": " ".join(scopes),
        }
        return f"{REDDIT_AUTH_URL}?{urlencode(params)}"

    async def handle_callback(
        self,
        settings: Settings,
        code: str,
        *,
        now: datetime,
        code_verifier: str | None = None,
    ) -> OAuthTokenResult:
        body = await platform_request(
            "reddit",
            "POST",
            REDDIT_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.reddit_redirect_uri,
            },
            auth=(settings.reddit_client_id, settings.reddit_client_secret),
            headers={**self._headers(settings), "Content-Type": "application/x-www-form-urlencoded"},
        )
        expires_in = int(body.get("expires_in") or 3600)
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
            "reddit",
            "POST",
            REDDIT_TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            auth=(settings.reddit_client_id, settings.reddit_client_secret),
            headers={**self._headers(settings), "Content-Type": "application/x-www-form-urlencoded"},
        )
        expires_in = int(body.get("expires_in") or 3600)
        scope_str = body.get("scope") or ""
        return OAuthTokenResult(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token") or refresh_token,
            expires_at=now + timedelta(seconds=expires_in),
            scopes=tuple(s for s in scope_str.replace(",", " ").split() if s),
            mode="real",
        )

    async def revoke_token(self, settings: Settings, access_token: str) -> bool:
        if not self.is_configured(settings):
            return False
        try:
            await platform_request(
                "reddit",
                "POST",
                REDDIT_REVOKE_URL,
                data={"token": access_token, "token_type_hint": "access_token"},
                auth=(settings.reddit_client_id, settings.reddit_client_secret),
                headers={**self._headers(settings), "Content-Type": "application/x-www-form-urlencoded"},
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
                    account_id="reddit_fake_1",
                    display_name="r/adcraft_demo (u/adcraft_user)",
                    username="adcraft_user",
                    account_type="subreddit",
                    target_id="adcraft_demo",
                    target_name="r/adcraft_demo",
                    target_type="reddit_subreddit",
                    can_publish=True,
                    extra={"submission_type": "any"},
                ),
                DiscoveredAccount(
                    account_id="reddit_fake_1",
                    display_name="u/adcraft_user (Profile Posts)",
                    username="adcraft_user",
                    account_type="profile",
                    target_id="u_adcraft_user",
                    target_name="u/adcraft_user",
                    target_type="reddit_profile",
                    can_publish=True,
                    extra={"submission_type": "any"},
                ),
            ]

        headers = self._headers(settings, access_token)
        me = await platform_request("reddit", "GET", REDDIT_ME_URL, headers=headers)
        username = me.get("name") or "reddit_user"
        user_id = str(me.get("id") or username)
        avatar = (me.get("icon_img") or "").split("?")[0] or None

        subs_body = await platform_request(
            "reddit",
            "GET",
            REDDIT_SUBREDDITS_URL,
            params={"limit": 50},
            headers=headers,
        )
        children = ((subs_body.get("data") or {}).get("children")) or []
        accounts: list[DiscoveredAccount] = []
        for child in children:
            data = child.get("data") or {}
            sr_name = data.get("display_name")
            if not sr_name:
                continue
            submission_type = data.get("submission_type") or "any"
            restricted = data.get("subreddit_type") == "restricted" and not data.get("user_is_contributor")
            accounts.append(
                DiscoveredAccount(
                    account_id=user_id,
                    display_name=f"r/{sr_name} (u/{username})",
                    username=username,
                    account_type="subreddit",
                    target_id=sr_name,
                    target_name=f"r/{sr_name}",
                    target_type="reddit_subreddit",
                    avatar_url=avatar,
                    can_publish=not restricted,
                    permission_note=(
                        "Restricted subreddit (requires approved contributor access)."
                        if restricted
                        else f"Allows {submission_type} submissions."
                    ),
                    extra={"submission_type": submission_type, "over18": bool(data.get("over18"))},
                )
            )

        # Include personal profile subreddit u_<username> as a fallback target
        accounts.append(
            DiscoveredAccount(
                account_id=user_id,
                display_name=f"u/{username} (Personal Profile)",
                username=username,
                account_type="profile",
                target_id=f"u_{username}",
                target_name=f"u/{username}",
                target_type="reddit_profile",
                avatar_url=avatar,
                can_publish=True,
                extra={"submission_type": "any"},
            )
        )
        return accounts

    def validate_publish(self, content: PublishContent, connection: dict) -> list[str]:
        errors: list[str] = []
        subreddit = content.target_id or connection.get("selected_target_id")
        if not subreddit:
            errors.append("Select a subreddit or profile target before posting to Reddit.")
        title = (content.title or "").strip()
        if not title:
            errors.append("Reddit posts require a post title.")
        elif len(title) > REDDIT_TITLE_MAX:
            errors.append(f"Reddit post title exceeds {REDDIT_TITLE_MAX} characters.")

        metadata = connection.get("metadata") or {}
        sub_type = metadata.get("submission_type")
        if sub_type == "self" and content.link_url and not (content.text or "").strip():
            errors.append("This subreddit only allows text (self) posts, not link posts.")
        if sub_type == "link" and not content.link_url:
            errors.append("This subreddit only allows link posts (provide a link URL).")

        valid_tags, _ = validate_hashtag_list(content.hashtags or [])
        body_text = format_caption_with_hashtags(content.text or "", valid_tags)
        if not content.link_url and not body_text.strip():
            errors.append("Reddit text posts require body text or a link URL.")
        if len(body_text) > REDDIT_TEXT_MAX:
            errors.append(f"Reddit post body exceeds {REDDIT_TEXT_MAX} characters.")
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
        subreddit = content.target_id or connection.get("selected_target_id")
        target_name = content.target_name or connection.get("selected_target_name") or f"r/{subreddit}"
        valid_tags, _ = validate_hashtag_list(content.hashtags or [])
        body_text = format_caption_with_hashtags(content.text or "", valid_tags)[:REDDIT_TEXT_MAX]
        title = (content.title or "").strip()[:REDDIT_TITLE_MAX]

        if connection.get("mode") == "fake":
            return PublishResult(
                platform="reddit",
                status="PUBLISHED",
                platform_post_id=f"t3_fake_{abs(hash(title)) % 100000}",
                post_url=f"https://www.reddit.com/r/{subreddit}/comments/fake/",
                target_id=subreddit,
                target_name=target_name,
            )

        kind = "link" if content.link_url else "self"
        form_data: dict[str, str] = {
            "api_type": "json",
            "sr": str(subreddit),
            "kind": kind,
            "title": title,
            "resubmit": "true",
        }
        if kind == "link" and content.link_url:
            form_data["url"] = content.link_url
        else:
            form_data["text"] = body_text

        try:
            resp = await platform_request(
                "reddit",
                "POST",
                REDDIT_SUBMIT_URL,
                data=form_data,
                headers={**self._headers(settings, access_token), "Content-Type": "application/x-www-form-urlencoded"},
                retry_transient=False,
            )
            json_block = resp.get("json") or {}
            errors = json_block.get("errors") or []
            if errors:
                err_msg = "; ".join(str(e) for e in errors)[:300]
                return PublishResult(
                    platform="reddit",
                    status="FAILED",
                    target_id=subreddit,
                    target_name=target_name,
                    error=f"Reddit rejected submission: {err_msg}",
                    error_code="REDDIT_POST_FAILED",
                )
            data = json_block.get("data") or {}
            post_id = str(data.get("name") or data.get("id") or "")
            return PublishResult(
                platform="reddit",
                status="PUBLISHED",
                platform_post_id=post_id,
                post_url=data.get("url"),
                target_id=subreddit,
                target_name=target_name,
            )
        except Exception as exc:
            return PublishResult(
                platform="reddit",
                status="FAILED",
                target_id=subreddit,
                target_name=target_name,
                error=str(exc)[:300],
                error_code="REDDIT_POST_FAILED",
            )

