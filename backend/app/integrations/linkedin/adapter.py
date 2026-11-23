from datetime import datetime, timedelta
import hashlib
from urllib.parse import quote, urlencode

import httpx
import structlog

from app.config import Settings
from app.domain.hashtags import format_caption_with_hashtags, validate_hashtag_list
from app.integrations.base.adapter import SocialPlatformAdapter
from app.integrations.base.errors import (
    IntegrationApiError,
    IntegrationAuthExpired,
    IntegrationPermissionDenied,
    sanitize_error_message,
)
from app.integrations.base.http import platform_request
from app.integrations.base.models import (
    DiscoveredAccount,
    OAuthTokenResult,
    PlatformCapabilities,
    PlatformDefinition,
    PublishContent,
    PublishResult,
)

log = structlog.get_logger()

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_REVOKE_URL = "https://www.linkedin.com/oauth/v2/revoke"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_ORG_ACLS_URL = "https://api.linkedin.com/rest/organizationAcls"
LINKEDIN_ORG_URL = "https://api.linkedin.com/rest/organizations/{org_id}"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_IMAGES_INIT_URL = "https://api.linkedin.com/rest/images?action=initializeUpload"
LINKEDIN_TEXT_MAX = 3000


def _rest_headers(access_token: str, settings: Settings) -> dict[str, str]:
    # LinkedIn retires each API version after about 12 months (a retired one answers 426 NONEXISTENT_VERSION),
    # so the version is a setting (LINKEDIN_API_VERSION) and not a constant.
    return {
        "Authorization": f"Bearer {access_token}",
        "LinkedIn-Version": settings.linkedin_api_version,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }


class LinkedInAdapter(SocialPlatformAdapter):
    platform_id = "linkedin"

    def definition(self, settings: Settings) -> PlatformDefinition:
        scopes = tuple(s.strip() for s in settings.linkedin_scopes.split(",") if s.strip())
        return PlatformDefinition(
            id="linkedin",
            name="LinkedIn",
            description="Connect LinkedIn Organization Pages and profiles for text and image publishing.",
            capabilities=PlatformCapabilities(
                supports_oauth=True,
                supports_refresh=True,
                supports_account_selection=True,
                supports_text_post=True,
                supports_image_post=True,
                supports_video_post=False,
                supports_link_post=True,
                supports_title=True,
                supports_scheduling=False,
                requires_image=False,
                requires_target_selection=True,
                max_text_length=LINKEDIN_TEXT_MAX,
                supported_media_types=("image/jpeg", "image/png"),
                max_image_size_mb=8,
                max_video_size_mb=0,
                target_label="LinkedIn Organization Page or Profile",
            ),
            required_env_vars=("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "LINKEDIN_REDIRECT_URI"),
            required_scopes=scopes,
            ads_supported=False,
            ads_status="REQUIRES_API_APPROVAL",
            ads_note="LinkedIn Ads requires separate LinkedIn Advertising API approval, a Company Page, and INR/USD billing ($10/day min).",
        )

    def is_configured(self, settings: Settings) -> bool:
        return bool(settings.linkedin_client_id and settings.linkedin_client_secret)

    def connect(self, settings: Settings, state: str, *, code_challenge: str | None = None) -> str:
        scopes = [s.strip() for s in settings.linkedin_scopes.split(",") if s.strip()]
        params = {
            "response_type": "code",
            "client_id": settings.linkedin_client_id,
            "redirect_uri": settings.linkedin_redirect_uri,
            "state": state,
            "scope": " ".join(scopes),
        }
        return f"{LINKEDIN_AUTH_URL}?{urlencode(params, quote_via=quote)}"

    async def handle_callback(
        self,
        settings: Settings,
        code: str,
        *,
        now: datetime,
        code_verifier: str | None = None,
    ) -> OAuthTokenResult:
        body = await platform_request(
            "linkedin",
            "POST",
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.linkedin_redirect_uri,
                "client_id": settings.linkedin_client_id,
                "client_secret": settings.linkedin_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        expires_in = int(body.get("expires_in") or 5184000)
        scope_str = body.get("scope") or ""
        scopes = tuple(s for s in scope_str.replace(",", " ").split() if s)
        return OAuthTokenResult(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_at=now + timedelta(seconds=expires_in),
            scopes=scopes,
            mode="real",
        )

    async def refresh_token(
        self, settings: Settings, refresh_token: str, *, now: datetime
    ) -> OAuthTokenResult | None:
        if not self.is_configured(settings):
            return None
        body = await platform_request(
            "linkedin",
            "POST",
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.linkedin_client_id,
                "client_secret": settings.linkedin_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        expires_in = int(body.get("expires_in") or 5184000)
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
                "linkedin",
                "POST",
                LINKEDIN_REVOKE_URL,
                data={
                    "client_id": settings.linkedin_client_id,
                    "client_secret": settings.linkedin_client_secret,
                    "token": access_token,
                },
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
            org_name = (connection or {}).get("selected_target_name") or (connection or {}).get("account_display_name") or "Connected Business"
            return [
                DiscoveredAccount(
                    account_id="urn:li:organization:9001001",
                    display_name=f"{org_name} (Company Page)",
                    username="business-page",
                    account_type="organization",
                    target_id="urn:li:organization:9001001",
                    target_name=org_name,
                    target_type="linkedin_organization",
                    can_publish=True,
                    permission_note="Approved Administrator role on Organization Page.",
                    extra={"role": "ADMINISTRATOR", "identity_kind": "organization"},
                ),
                DiscoveredAccount(
                    account_id="urn:li:person:fake_member_1",
                    display_name="Connected Member (Personal Profile)",
                    username="member-profile",
                    account_type="personal",
                    target_id="urn:li:person:fake_member_1",
                    target_name="Connected Member",
                    target_type="linkedin_personal",
                    can_publish=True,
                    permission_note="Personal LinkedIn profile identity (separate from Organization Pages).",
                    extra={"identity_kind": "personal"},
                ),
            ]

        accounts: list[DiscoveredAccount] = []
        granted = set((connection or {}).get("scopes") or [])
        has_org_write = "w_organization_social" in granted

        # 1. Discover Organization Pages separately from personal identity
        try:
            acl_body = await platform_request(
                "linkedin",
                "GET",
                LINKEDIN_ORG_ACLS_URL,
                params={"q": "roleAssignee", "role": "ADMINISTRATOR", "state": "APPROVED"},
                headers=_rest_headers(access_token, settings),
            )
            for elem in acl_body.get("elements", []):
                org_urn = elem.get("organization") or elem.get("organizationalTarget")
                if not org_urn:
                    continue
                org_id = str(org_urn).rsplit(":", 1)[-1]
                org_name = f"LinkedIn Organization {org_id}"
                vanity = None
                try:
                    org_detail = await platform_request(
                        "linkedin",
                        "GET",
                        LINKEDIN_ORG_URL.format(org_id=org_id),
                        headers=_rest_headers(access_token, settings),
                    )
                    org_name = org_detail.get("localizedName") or org_detail.get("name") or org_name
                    vanity = org_detail.get("vanityName")
                except (IntegrationPermissionDenied, IntegrationApiError):
                    pass
                accounts.append(
                    DiscoveredAccount(
                        account_id=str(org_urn),
                        display_name=f"{org_name} (Organization Page)",
                        username=vanity,
                        account_type="organization",
                        target_id=str(org_urn),
                        target_name=org_name,
                        target_type="linkedin_organization",
                        can_publish=has_org_write,
                        permission_note=(
                            "Organization Page administrator."
                            if has_org_write
                            else "OAuth token lacks w_organization_social permission for Organization publishing. Page publishing needs LinkedIn approval."
                        ),
                        extra={"role": elem.get("role", "ADMINISTRATOR"), "identity_kind": "organization"},
                    )
                )
        except (IntegrationPermissionDenied, IntegrationApiError) as exc:
            # Community Management API / organizationAcls may not be approved on this LinkedIn app yet
            log.warning("linkedin_organization_acls_failed", error=sanitize_error_message(str(exc)))

        # 2. Retrieve personal LinkedIn identity separately
        try:
            userinfo = await platform_request(
                "linkedin",
                "GET",
                LINKEDIN_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            sub = userinfo.get("sub")
            if sub:
                person_urn = f"urn:li:person:{sub}"
                name = userinfo.get("name") or userinfo.get("email") or "LinkedIn Member"
                accounts.append(
                    DiscoveredAccount(
                        account_id=person_urn,
                        display_name=f"{name} (Personal Profile)",
                        username=userinfo.get("email"),
                        account_type="personal",
                        target_id=person_urn,
                        target_name=name,
                        target_type="linkedin_personal",
                        avatar_url=userinfo.get("picture"),
                        can_publish=not granted or "w_member_social" in granted,
                        permission_note="Personal LinkedIn identity (separate from Company Pages).",
                        extra={"identity_kind": "personal"},
                    )
                )
        except IntegrationAuthExpired:
            raise
        except (IntegrationPermissionDenied, IntegrationApiError):
            pass

        if not accounts:
            accounts.append(
                DiscoveredAccount(
                    account_id="urn:li:person:me",
                    display_name="Connected LinkedIn Member",
                    username="linkedin_member",
                    account_type="personal",
                    target_id="urn:li:person:me",
                    target_name="LinkedIn Member",
                    target_type="linkedin_personal",
                    can_publish=not granted or "w_member_social" in granted,
                    permission_note="Personal LinkedIn identity via Share on LinkedIn (w_member_social).",
                    extra={"identity_kind": "personal"},
                )
            )
        return accounts

    def validate_publish(self, content: PublishContent, connection: dict) -> list[str]:
        errors: list[str] = []
        target = content.target_id or connection.get("selected_target_id") or connection.get("platform_account_id")
        if not target:
            errors.append("Select a LinkedIn Organization Page or Personal Profile before publishing.")
        granted = set(connection.get("scopes") or [])
        is_fake = (connection or {}).get("mode") == "fake"
        if not is_fake and target:
            if str(target).startswith("urn:li:organization:") and granted and "w_organization_social" not in granted:
                errors.append(
                    "LinkedIn Organization Page publishing requires the w_organization_social permission and Page admin role."
                )
            elif str(target).startswith("urn:li:person:") and granted and "w_member_social" not in granted:
                errors.append(
                    "LinkedIn personal profile publishing requires the w_member_social permission."
                )
        if content.scheduled_at:
            errors.append("LinkedIn API does not support scheduled posts. Please publish now or remove scheduling.")
        valid_tags, _ = validate_hashtag_list(content.hashtags or [])
        formatted = format_caption_with_hashtags(content.text or "", valid_tags)
        if not formatted.strip():
            errors.append("LinkedIn post requires text commentary.")
        if len(formatted) > LINKEDIN_TEXT_MAX:
            errors.append(f"LinkedIn post exceeds {LINKEDIN_TEXT_MAX} characters.")
        if content.title and len(content.title) > 400:
            errors.append("LinkedIn title cannot exceed 400 characters.")
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
        target_name = content.target_name or connection.get("selected_target_name")
        valid_tags, _ = validate_hashtag_list(content.hashtags or [])
        commentary = format_caption_with_hashtags(content.text or "", valid_tags)[:LINKEDIN_TEXT_MAX]

        if connection.get("mode") == "fake":
            fake_id = hashlib.sha1(commentary.encode("utf-8")).hexdigest()[:10]
            return PublishResult(
                platform="linkedin",
                status="PUBLISHED",
                platform_post_id=f"urn:li:share:fake_{fake_id}",
                post_url=f"https://www.linkedin.com/feed/update/urn:li:share:fake_{fake_id}",
                target_id=target,
                target_name=target_name,
            )

        # Normalize target ID to URN format if plain numeric ID provided
        if target and not str(target).startswith("urn:li:"):
            if connection.get("account_type") == "organization" or connection.get("selected_target_type") == "linkedin_organization":
                target = f"urn:li:organization:{target}"
            else:
                target = f"urn:li:person:{target}"

        # Resolve image bytes: either from content.image_bytes or download from content.image_url
        image_bytes = content.image_bytes
        image_content_type = content.image_content_type or "image/jpeg"
        if not image_bytes and content.image_url and str(content.image_url).startswith(("http://", "https://")):
            try:
                async with httpx.AsyncClient(timeout=15.0) as dl_client:
                    dl_resp = await dl_client.get(content.image_url)
                    if dl_resp.status_code == 200:
                        image_bytes = dl_resp.content
                        image_content_type = dl_resp.headers.get("Content-Type") or image_content_type
            except Exception as dl_err:
                log.warning("linkedin_image_download_failed", error=str(dl_err))

        # If both image and link URL are provided, include the link in commentary (M-3)
        if image_bytes and content.link_url and content.link_url not in commentary:
            extra_link = f"\n\n{content.link_url}"
            commentary = (commentary[: LINKEDIN_TEXT_MAX - len(extra_link)] + extra_link) if len(commentary) + len(extra_link) > LINKEDIN_TEXT_MAX else (commentary + extra_link)

        headers = _rest_headers(access_token, settings)
        payload: dict = {
            "author": str(target),
            "commentary": commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        try:
            if image_bytes:
                init_body = await platform_request(
                    "linkedin",
                    "POST",
                    LINKEDIN_IMAGES_INIT_URL,
                    json={"initializeUploadRequest": {"owner": str(target)}},
                    headers=headers,
                )
                value = init_body.get("value") or {}
                upload_url = value["uploadUrl"]
                image_urn = value["image"]

                upload_headers = {"Content-Type": image_content_type}
                # Pre-signed S3 URLs reject requests that include both URL signature query params and Authorization header
                if "X-Amz-Signature" not in upload_url and "Signature=" not in upload_url:
                    upload_headers["Authorization"] = f"Bearer {access_token}"

                async with httpx.AsyncClient(timeout=20.0) as client:
                    up = await client.put(
                        upload_url,
                        content=image_bytes,
                        headers=upload_headers,
                    )
                if up.status_code == 401:
                    raise IntegrationAuthExpired(
                        "LinkedIn authorization expired or was revoked. Please reconnect.",
                        {"platform": "linkedin"},
                    )
                if up.status_code >= 300:
                    raise IntegrationApiError(
                        f"LinkedIn image upload failed ({up.status_code})",
                        platform="linkedin",
                        http_status=up.status_code,
                    )
                payload["content"] = {"media": {"id": image_urn, "title": content.title or "Image"}}
            elif content.link_url:
                payload["content"] = {
                    "article": {
                        "source": content.link_url,
                        "title": content.title or content.link_url,
                    }
                }

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(LINKEDIN_POSTS_URL, json=payload, headers=headers)
            if resp.status_code == 401:
                raise IntegrationAuthExpired(
                    "LinkedIn authorization expired or was revoked. Please reconnect.",
                    {"platform": "linkedin"},
                )
            if resp.status_code == 403:
                msg = sanitize_error_message(resp.text[:300])
                return PublishResult(
                    platform="linkedin",
                    status="FAILED",
                    target_id=target,
                    target_name=target_name,
                    error=f"LinkedIn permission denied: Your account lacks required scopes (w_member_social or w_organization_social) for this target. {msg}",
                    error_code="LINKEDIN_PERMISSION_DENIED",
                )
            if resp.status_code == 429:
                return PublishResult(
                    platform="linkedin",
                    status="FAILED",
                    target_id=target,
                    target_name=target_name,
                    error="LinkedIn publishing rate limit reached. Please try again later.",
                    error_code="LINKEDIN_RATE_LIMITED",
                )
            if resp.status_code >= 300:
                msg = sanitize_error_message(resp.text[:300])
                return PublishResult(
                    platform="linkedin",
                    status="FAILED",
                    target_id=target,
                    target_name=target_name,
                    error=f"LinkedIn rejected post ({resp.status_code}): {msg}",
                    error_code="LINKEDIN_POST_FAILED",
                )
            post_id = resp.headers.get("x-restli-id") or (resp.json().get("id") if resp.content else None) or "published"
            post_url = f"https://www.linkedin.com/feed/update/{post_id}" if post_id != "published" else "https://www.linkedin.com/feed/"
            return PublishResult(
                platform="linkedin",
                status="PUBLISHED",
                platform_post_id=str(post_id),
                post_url=post_url,
                target_id=target,
                target_name=target_name,
            )
        except (IntegrationAuthExpired, IntegrationPermissionDenied):
            raise
        except Exception as exc:
            return PublishResult(
                platform="linkedin",
                status="FAILED",
                target_id=target,
                target_name=target_name,
                error=sanitize_error_message(str(exc))[:300],
                error_code="LINKEDIN_POST_FAILED",
            )
