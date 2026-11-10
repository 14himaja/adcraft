import asyncio
import base64
import json
from datetime import date

import requests
from facebook_business.api import FacebookAdsApi, FacebookSession
from facebook_business.exceptions import FacebookRequestError
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt

from app.config import Settings
from app.meta.errors import DEFAULT_WAIT, MetaError, is_retryable, meta_error_from_body
from app.meta.ports import Edge, InterestOption

GRAPH_URL = "https://graph.facebook.com"
READ_ATTEMPTS = 4
TIMEOUT_S = 30


def _retry_after_s(headers) -> float | None:
    raw = (headers or {}).get("X-Business-Use-Case-Usage")
    if not raw:
        return None
    try:
        usage = json.loads(raw)
        minutes = max(
            entry.get("estimated_time_to_regain_access", 0) for entries in usage.values() for entry in entries
        )
    except (ValueError, AttributeError, TypeError):
        return None
    return minutes * 60 or None


def _to_meta_error(exc: FacebookRequestError) -> MetaError:
    body = exc.body() if isinstance(exc.body(), dict) else {}
    error = meta_error_from_body(body, exc.http_status())
    error.retry_after_s = _retry_after_s(exc.http_headers())
    return error


class MetaSdkGateway:
    """AdsReader + AdsWriter over the official facebook-business SDK."""

    def __init__(
        self,
        *,
        access_token: str,
        settings: Settings,
        wait=DEFAULT_WAIT,
    ):
        session = FacebookSession(
            app_id=settings.meta_app_id or None,
            app_secret=settings.meta_app_secret or None,
            access_token=access_token,
            timeout=TIMEOUT_S,
        )
        self._api = FacebookAdsApi(session, api_version=settings.meta_api_version)
        self._wait = wait
        self._settings = settings
        self._page_apis: dict[str, FacebookAdsApi] = {}

    async def _call(self, method: str, path: tuple, params: dict | None = None, api=None) -> dict:
        def send() -> dict:
            try:
                return (api or self._api).call(method, path, params=params).json()
            except FacebookRequestError as exc:
                raise _to_meta_error(exc) from None
            except requests.Timeout:
                err = TimeoutError("Meta did not respond in time")
                err.__suppress_context__ = True
                raise err from None
            except requests.ConnectionError:
                err = ConnectionError("Could not reach Meta")
                err.__suppress_context__ = True
                raise err from None

        try:
            return await asyncio.to_thread(send)
        except (TimeoutError, ConnectionError, MetaError) as err:
            err.__suppress_context__ = True
            raise err from None

    async def _read(self, path: tuple, params: dict | None = None) -> dict:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(READ_ATTEMPTS),
            wait=self._wait,
            retry=retry_if_exception(is_retryable),
            reraise=True,
        ):
            with attempt:
                return await self._call("GET", path, params)
        raise AssertionError("unreachable")

    @property
    def _spend_allowed(self) -> bool:
        return self._settings.spend_allowed

    # --- AdsReader ---------------------------------------------------------------------------

    async def list_ad_accounts(self) -> list[dict]:
        body = await self._read(
            ("me", "adaccounts"),
            {"fields": "account_id,name,account_status,currency,min_daily_budget", "limit": 100},
        )
        return [
            {
                "id": row["id"],
                "name": row.get("name") or row["id"],
                "currency": row.get("currency"),
                "account_status": row.get("account_status"),
                "min_daily_budget_minor": (
                    int(row["min_daily_budget"]) if row.get("min_daily_budget") else None
                ),
            }
            for row in body.get("data", [])
        ]

    async def list_pages(self) -> list[dict]:
        body = await self._read(("me", "accounts"), {"fields": "id,name", "limit": 100})
        pages = [{"id": row["id"], "name": row.get("name", "")} for row in body.get("data", [])]
        try:
            accounts = await self.list_ad_accounts()
            for acc in accounts:
                acc_id = acc.get("id")
                if acc_id:
                    p_body = await self._read((acc_id, "promote_pages"), {"fields": "id,name", "limit": 50})
                    for row in p_body.get("data", []):
                        if not any(p["id"] == row["id"] for p in pages):
                            pages.append({"id": row["id"], "name": row.get("name", "")})
        except Exception:
            pass
        return pages

    async def instagram_account_for_page(self, page_id: str) -> dict | None:
        body = await self._read(
            (page_id,), {"fields": "instagram_business_account{id,username,profile_picture_url}"}
        )
        instagram = body.get("instagram_business_account")
        if not instagram:
            return None
        return {
            "id": instagram["id"],
            "username": instagram.get("username", ""),
            "profile_picture_url": instagram.get("profile_picture_url"),
        }

    async def search_interests(self, query: str, limit: int = 5) -> list[InterestOption]:
        body = await self._read(("search",), {"type": "adinterest", "q": query, "limit": limit})
        return [
            InterestOption(
                id=row["id"], name=row["name"], audience_size_lower=row.get("audience_size_lower_bound")
            )
            for row in body.get("data", [])
        ][:limit]

    async def search_locations(self, query: str, country: str) -> list[dict]:
        body = await self._read(
            ("search",),
            {
                "type": "adgeolocation",
                "q": query,
                "location_types": ["city", "region"],
                "country_code": country,
            },
        )
        return [
            {
                "key": row["key"],
                "name": row["name"],
                "type": row["type"],
                "country_code": row.get("country_code"),
            }
            for row in body.get("data", [])
            if row.get("country_code") in (None, country)
        ]

    async def delivery_estimate(
        self, account_id: str, targeting: dict, optimization_goal: str = "LINK_CLICKS"
    ) -> dict:
        body = await self._read(
            (account_id, "delivery_estimate"),
            {"targeting_spec": targeting, "optimization_goal": optimization_goal},
        )
        row = (body.get("data") or [{}])[0]
        return {
            "lower": row.get("estimate_mau_lower_bound") or 0,
            "upper": row.get("estimate_mau_upper_bound") or 0,
        }

    async def find_by_name(self, account_id: str, edge: Edge, name: str) -> str | None:
        body = await self._read(
            (account_id, edge),
            {
                "fields": "id,name",
                "limit": 2,
                "filtering": [{"field": "name", "operator": "EQUAL", "value": name}],
            },
        )
        rows = body.get("data", [])
        return rows[0]["id"] if rows else None

    async def insights(self, campaign_id: str, since: date, until: date) -> list[dict]:
        body = await self._read(
            (campaign_id, "insights"),
            {
                "level": "campaign",
                "fields": "impressions,reach,clicks,spend,ctr,cpc",
                "time_range": {"since": since.isoformat(), "until": until.isoformat()},
            },
        )
        return body.get("data", [])

    async def ad_status(self, ad_id: str) -> dict:
        body = await self._read((ad_id,), {"fields": "effective_status,ad_review_feedback,issues_info"})
        return {
            "effective_status": body.get("effective_status", "UNKNOWN"),
            "review_feedback": body.get("ad_review_feedback"),
            "issues": [
                i.get("error_message") or i.get("error_summary") for i in body.get("issues_info") or []
            ],
        }

    async def get_ad_creative(self, creative_id: str) -> dict:
        body = await self._read(
            (creative_id,),
            {"fields": "id,effective_instagram_media_id,instagram_permalink_url"},
        )
        return {
            "id": body.get("id", creative_id),
            "effective_instagram_media_id": body.get("effective_instagram_media_id"),
            "instagram_permalink_url": body.get("instagram_permalink_url"),
        }

    async def list_recent_posts(self, page_id: str, ig_user_id: str | None = None) -> list[dict]:
        posts = []
        if ig_user_id:
            try:
                body = await self._read((ig_user_id, "media"), {"fields": "id,caption,permalink,media_type,media_url,timestamp", "limit": 25})
                for row in body.get("data", []):
                    posts.append({
                        "id": row["id"],
                        "platform": "instagram",
                        "caption": row.get("caption", ""),
                        "permalink": row.get("permalink", f"https://instagram.com/p/{row['id']}"),
                        "media_type": row.get("media_type", "IMAGE"),
                        "media_url": row.get("media_url"),
                        "timestamp": row.get("timestamp"),
                    })
            except Exception as exc:
                pass
        if page_id:
            try:
                body = await self._read((page_id, "feed"), {"fields": "id,message,permalink_url,created_time,full_picture", "limit": 25})
                for row in body.get("data", []):
                    posts.append({
                        "id": row["id"],
                        "platform": "facebook",
                        "caption": row.get("message", ""),
                        "permalink": row.get("permalink_url", f"https://facebook.com/{row['id']}"),
                        "media_type": "IMAGE",
                        "media_url": row.get("full_picture"),
                        "timestamp": row.get("created_time"),
                    })
            except Exception as exc:
                pass
        return posts

    # --- AdsWriter (never retried here: the publisher decides) --------------------------------

    async def upload_image(self, account_id: str, data: bytes, filename: str) -> str:
        body = await self._call(
            "POST",
            (account_id, "adimages"),
            {"bytes": base64.b64encode(data).decode(), "name": filename},
        )
        return next(iter(body["images"].values()))["hash"]

    async def create(self, account_id: str, edge: Edge, params: dict) -> str:
        safe_params = dict(params)
        # Keep objects paused unless the deployment explicitly enables real ad delivery.
        if (edge in ("campaigns", "adsets", "ads") or "status" in safe_params) and not self._spend_allowed:
            safe_params["status"] = "PAUSED"
        return (await self._call("POST", (account_id, edge), safe_params))["id"]

    async def update(self, object_id: str, params: dict) -> None:
        safe_params = dict(params)
        if "status" in safe_params and not self._spend_allowed:
            safe_params["status"] = "PAUSED"
        await self._call("POST", (object_id,), safe_params)

    async def delete(self, object_id: str) -> None:
        await self._call("DELETE", (object_id,))

    # --- Social: DMs and organic posts (Instagram Graph API) ----------------------------------

    async def _as_page(self, page_id: str) -> FacebookAdsApi:
        """Page-level calls (messages, webhook subscription) need the Page's token, not the login token."""
        api = self._page_apis.get(page_id)
        if api is not None:
            return api
        token = (await self._read((page_id,), {"fields": "access_token"}))["access_token"]
        session = FacebookSession(
            app_id=self._settings.meta_app_id or None,
            app_secret=self._settings.meta_app_secret or None,
            access_token=token,
            timeout=TIMEOUT_S,
        )
        api = FacebookAdsApi(session, api_version=self._settings.meta_api_version)
        self._page_apis[page_id] = api
        return api

    async def send_dm(self, page_id: str, recipient_id: str, text: str) -> str:
        body = await self._call(
            "POST",
            (page_id, "messages"),
            {"recipient": {"id": recipient_id}, "message": {"text": text}, "messaging_type": "RESPONSE"},
            api=await self._as_page(page_id),
        )
        return body.get("message_id") or body.get("id", "")

    async def customer_name(self, page_id: str, customer_id: str) -> str | None:
        """Instagram profiles have name/username, Messenger ones first/last name; a refusal means no name."""
        api = await self._as_page(page_id)
        for fields in ("name,username", "first_name,last_name"):
            try:
                body = await self._call("GET", (customer_id,), {"fields": fields}, api=api)
            except MetaError:
                continue
            full = " ".join(p for p in (body.get("first_name"), body.get("last_name")) if p)
            if name := body.get("name") or full or body.get("username"):
                return name
        return None

    async def publish_photo(self, ig_user_id: str, image_url: str, caption: str, story: bool = False) -> str:
        params = {"image_url": image_url, "caption": caption}
        if story:  # stories ignore captions
            params = {"image_url": image_url, "media_type": "STORIES"}
        container = await self._call("POST", (ig_user_id, "media"), params)
        published = await self._call("POST", (ig_user_id, "media_publish"), {"creation_id": container["id"]})
        return published["id"]

    async def publish_facebook_photo(self, page_id: str, image_url: str, caption: str) -> str:
        """A normal Page photo post. Needs the pages_manage_posts permission and the Page's own token."""
        api = await self._as_page(page_id)
        body = await self._call("POST", (page_id, "photos"), {"url": image_url, "caption": caption}, api=api)
        return body.get("post_id") or body["id"]

    async def publish_facebook_story(self, page_id: str, image_url: str) -> str:
        """A Page photo story: upload the photo unpublished, then turn it into a story."""
        api = await self._as_page(page_id)
        photo = await self._call("POST", (page_id, "photos"), {"url": image_url, "published": False}, api=api)
        body = await self._call("POST", (page_id, "photo_stories"), {"photo_id": photo["id"]}, api=api)
        return body.get("post_id") or photo["id"]

    async def subscribe_messages(self, page_id: str) -> None:
        await self._call(
            "POST",
            (page_id, "subscribed_apps"),
            {"subscribed_fields": "messages"},
            api=await self._as_page(page_id),
        )

    async def messages_subscribed(self, page_id: str) -> bool:
        body = await self._call(
            "GET",
            (page_id, "subscribed_apps"),
            {"fields": "subscribed_fields"},
            api=await self._as_page(page_id),
        )
        return any("messages" in app.get("subscribed_fields", []) for app in body.get("data", []))
