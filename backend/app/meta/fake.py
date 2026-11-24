import hashlib
from datetime import date

from app.meta.errors import MetaError
from app.meta.ports import Edge, InterestOption

STEP_FOR_EDGE = {
    "campaigns": "CAMPAIGN",
    "adsets": "ADSET",
    "adcreatives": "CREATIVE",
    "ads": "AD",
}
TIMEOUT_MODES = ("timeout", "timeout_after_create")

FAKE_ACCOUNT = {
    "id": "act_fake_1",
    "name": "Fake Ad Account",
    "currency": "INR",
    "account_status": 1,
    "min_daily_budget_minor": 9673,
}
SYNXAIT_ACCOUNT = {
    "id": "act_2279071366267627",
    "name": "Synxait Ad Account (Dev/Test)",
    "currency": "INR",
    "account_status": 1,
    "min_daily_budget_minor": 9673,
}
FAKE_PAGES = [
    {"id": "page_fake_1", "name": "Fake Brand Page"},
    {"id": "page_fake_2", "name": "Page Without Instagram"},
    {"id": "1415879818267624", "name": "Social Ads Demo (Synxait Dev/Test)"},
]
FAKE_INSTAGRAM = {
    "page_fake_1": {"id": "ig_fake_1", "username": "fake_brand", "profile_picture_url": "https://fake.invalid/p.jpg"},
    "1415879818267624": {"id": "17841416182311813", "username": "synxait", "profile_picture_url": "https://fake.invalid/synxait.jpg"},
}
INTERESTS = [
    InterestOption(id="6003682002118", name="Python (programming language)", audience_size_lower=24_568_027),
    InterestOption(
        id="6003000000001", name="JavaScript (programming language)", audience_size_lower=30_000_000
    ),
    InterestOption(id="6003000000002", name="GitHub", audience_size_lower=8_000_000),
    InterestOption(id="6003000000003", name="Software development", audience_size_lower=45_000_000),
    InterestOption(id="6003000000004", name="Computer programming", audience_size_lower=60_000_000),
]
LOCATIONS = [
    (
        {"key": "1017930", "name": "Bangalore", "type": "city", "country_code": "IN"},
        ("bengaluru", "bangalore"),
    ),
    ({"key": "1035921", "name": "Mumbai", "type": "city", "country_code": "IN"}, ("mumbai", "bombay")),
]


def parse_fail_at(spec: str) -> dict[str, BaseException | str]:
    """'ADSET:timeout_after_create,CAMPAIGN:190,AD' -> {step: failure}. A bare step injects code 100."""
    failures: dict[str, BaseException | str] = {}
    for item in (part.strip() for part in spec.split(",")):
        if not item:
            continue
        step, _, how = item.partition(":")
        how = how.strip() or "100"
        failures[step.strip().upper()] = (
            how
            if how in TIMEOUT_MODES
            else MetaError(
                http_status=400, meta_code=int(how), message=f"Injected Meta error {how} at {step}"
            )
        )
    return failures


class FakeAdsGateway:
    """In-memory Meta for tests and mock mode. Passes the same contract tests as MetaSdkGateway."""

    def __init__(self, *, fail_at: dict[str, BaseException | str] | None = None):
        self.fail_at = dict(fail_at or {})
        self.objects: dict[str, dict] = {}
        self.images: dict[str, bytes] = {}
        self.sent_dms: list[dict] = []
        self.customer_names: dict[str, str] = {}  # customer id -> name the "Instagram" profile lookup returns
        self.name_lookups: list[str] = []
        self.published_posts: list[dict] = []
        self.facebook_posts: list[dict] = []
        self.subscribed_pages: list[str] = []
        self.creative_polls: dict[str, int] = {}
        self._next_id = 0

    def _injected(self, step: str) -> str | None:
        failure = self.fail_at.pop(step, None)  # one-shot, so a retry or Resume can succeed
        if isinstance(failure, BaseException):
            raise failure
        if failure == "timeout":
            raise TimeoutError(f"injected timeout before {step}")
        return failure

    def _get(self, object_id: str) -> dict:
        if object_id not in self.objects:
            raise MetaError(
                http_status=400, meta_code=100, meta_subcode=33, message=f"Object {object_id} does not exist"
            )
        return self.objects[object_id]

    def by_edge(self, edge: Edge) -> list[dict]:
        return [obj for obj in self.objects.values() if obj["edge"] == edge]

    async def list_ad_accounts(self) -> list[dict]:
        return [dict(FAKE_ACCOUNT), dict(SYNXAIT_ACCOUNT)]

    async def list_pages(self) -> list[dict]:
        return [dict(page) for page in FAKE_PAGES]

    async def instagram_account_for_page(self, page_id: str) -> dict | None:
        instagram = FAKE_INSTAGRAM.get(page_id)
        return dict(instagram) if instagram else None

    async def search_interests(self, query: str, limit: int = 5) -> list[InterestOption]:
        q = query.lower()
        return [option for option in INTERESTS if q in option.name.lower()][:limit]

    async def search_locations(self, query: str, country: str) -> list[dict]:
        q = query.lower()
        return [
            dict(loc)
            for loc, aliases in LOCATIONS
            if loc["country_code"] == country and any(q in alias for alias in aliases)
        ]

    async def delivery_estimate(
        self, account_id: str, targeting: dict, optimization_goal: str = "LINK_CLICKS"
    ) -> dict:
        return {"lower": 1_200_000, "upper": 1_400_000}

    async def find_by_name(self, account_id: str, edge: Edge, name: str) -> str | None:
        return next(
            (oid for oid, obj in self.objects.items() if obj["edge"] == edge and obj["name"] == name), None
        )

    async def insights(self, campaign_id: str, since: date, until: date) -> list[dict]:
        self._injected("INSIGHTS")
        obj = self._get(campaign_id)
        if not obj.get("delivered") and obj.get("status") != "ACTIVE":
            return []
        return [
            {
                "impressions": "1200",
                "reach": "800",
                "clicks": "30",
                "spend": "152.35",
                "ctr": "2.5",
                "cpc": "5.078333",
                "date_start": since.isoformat(),
                "date_stop": until.isoformat(),
                "is_simulated": True,
            }
        ]

    async def ad_status(self, ad_id: str) -> dict:
        self._injected("AD_STATUS")
        obj = self._get(ad_id)
        status = obj.get("status", "PAUSED")
        return {"effective_status": status, "review_feedback": None, "issues": []}

    async def get_ad_creative(self, creative_id: str) -> dict:
        self._injected("CREATIVE_GET")
        obj = self.objects.get(creative_id) or {}
        params = obj.get("params") or {}
        explicit_media_id = obj.get("effective_instagram_media_id") or params.get("effective_instagram_media_id")
        explicit_permalink = obj.get("instagram_permalink_url") or params.get("instagram_permalink_url")

        if explicit_media_id:
            media_id = explicit_media_id
            permalink = explicit_permalink or f"https://instagram.com/p/{media_id}"
        else:
            polls = self.creative_polls.get(creative_id, 0) + 1
            self.creative_polls[creative_id] = polls
            if polls == 1:
                media_id = None
                permalink = None
            else:
                media_id = f"ig_media_{creative_id}"
                permalink = f"https://instagram.com/p/{media_id}"

        return {
            "id": creative_id,
            "effective_instagram_media_id": str(media_id) if media_id else None,
            "instagram_permalink_url": str(permalink) if permalink else None,
        }

    async def list_recent_posts(self, page_id: str, ig_user_id: str | None = None) -> list[dict]:
        posts = []
        for p in self.published_posts:
            posts.append({
                "id": p.get("media_id", "ig_post_1"),
                "platform": "instagram",
                "caption": p.get("caption", ""),
                "permalink": f"https://instagram.com/p/{p.get('media_id', 'ig_post_1')}",
                "media_type": "IMAGE",
                "timestamp": date.today().isoformat(),
            })
        for p in self.facebook_posts:
            posts.append({
                "id": p.get("post_id", "fb_post_1"),
                "platform": "facebook",
                "caption": p.get("caption", ""),
                "permalink": f"https://facebook.com/posts/{p.get('post_id', 'fb_post_1')}",
                "media_type": "IMAGE",
                "timestamp": date.today().isoformat(),
            })
        if not posts:
            posts.append({
                "id": "ext_post_synced_1",
                "platform": "instagram",
                "caption": "Handcrafted Artisan Coffee & Fresh Pastry Combo at ₹149! Valid until 2026-11-15.",
                "title": "Artisan Coffee Combo",
                "permalink": "https://instagram.com/p/ext_post_synced_1",
                "media_type": "IMAGE",
                "timestamp": date.today().isoformat(),
            })
        return posts

    async def upload_image(self, account_id: str, data: bytes, filename: str) -> str:
        self._injected("IMAGE")
        image_hash = hashlib.md5(data, usedforsecurity=False).hexdigest()
        self.images[image_hash] = data
        return image_hash

    async def create(self, account_id: str, edge: Edge, params: dict) -> str:
        failure = self._injected(STEP_FOR_EDGE[edge])
        self._next_id += 1
        object_id = f"fake_{edge}_{self._next_id}"
        self.objects[object_id] = {
            "edge": edge,
            "account_id": account_id,
            "name": params.get("name"),
            "params": dict(params),
            "status": params.get("status", "PAUSED"),
        }
        if failure == "timeout_after_create":
            raise TimeoutError(f"injected timeout after creating {object_id}")
        return object_id

    async def update(self, object_id: str, params: dict) -> None:
        self._injected("UPDATE")
        obj = self._get(object_id)
        obj["params"].update(params)
        obj["status"] = params.get("status", obj["status"])
        if obj["status"] == "ACTIVE":
            obj["delivered"] = True

    async def delete(self, object_id: str) -> None:
        self._injected("DELETE")
        self._get(object_id)
        del self.objects[object_id]

    async def send_dm(self, page_id: str, recipient_id: str, text: str) -> str:
        self._injected("DM")
        self.sent_dms.append({"page_id": page_id, "recipient_id": recipient_id, "text": text})
        return f"fake_mid_{len(self.sent_dms)}"

    async def customer_name(self, page_id: str, customer_id: str) -> str | None:
        self.name_lookups.append(customer_id)
        return self.customer_names.get(customer_id)

    async def publish_photo(self, ig_user_id: str, image_url: str, caption: str, story: bool = False) -> str:
        self._injected("POST")
        post = {"ig_user_id": ig_user_id, "image_url": image_url, "caption": caption}
        self.published_posts.append(post | {"story": True} if story else post)
        return f"fake_media_{len(self.published_posts)}"

    async def publish_facebook_photo(self, page_id: str, image_url: str, caption: str) -> str:
        self._injected("POST")
        self.facebook_posts.append(
            {"page_id": page_id, "image_url": image_url, "caption": caption, "story": False}
        )
        return f"fake_fb_{len(self.facebook_posts)}"

    async def publish_facebook_feed_post(self, page_id: str, message: str, link: str | None = None) -> str:
        self._injected("POST")
        self.facebook_posts.append(
            {"page_id": page_id, "image_url": None, "caption": message, "link": link, "story": False}
        )
        return f"fake_fb_{len(self.facebook_posts)}"

    async def publish_facebook_story(self, page_id: str, image_url: str) -> str:
        self._injected("POST")
        self.facebook_posts.append({"page_id": page_id, "image_url": image_url, "caption": "", "story": True})
        return f"fake_fb_{len(self.facebook_posts)}"

    async def subscribe_messages(self, page_id: str) -> None:
        self.subscribed_pages.append(page_id)

    async def messages_subscribed(self, page_id: str) -> bool:
        return page_id in self.subscribed_pages
