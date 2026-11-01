"""Automated Meta API checks: the manual M0 calls from docs/pay_loads, run as a program.

Read-only (default):     uv run --env-file .env python scripts/meta_smoke_test.py
Also create + clean up:  uv run --env-file .env python scripts/meta_smoke_test.py --write
Save request/response:   add --save  (writes JSON to docs/pay_loads/auto/, tokens are never saved)

--write uploads a generated test image, creates a PAUSED campaign, ad set, Instagram creative and ad
(no spend), checks name lookup, ad status and insights, then deletes everything it created.
"""

import argparse
import base64
import hashlib
import hmac
import io
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from PIL import Image

REQUIRED_ENV = ("META_ACCESS_TOKEN", "META_APP_SECRET", "META_AD_ACCOUNT_ID", "META_PAGE_ID")
REQUIRED_PERMISSIONS = {
    "ads_management",
    "ads_read",
    "business_management",
    "pages_show_list",
    "pages_read_engagement",
    "instagram_basic",
    "instagram_content_publish",
    "instagram_manage_comments",
    "instagram_manage_contents",
    "instagram_manage_insights",
    "instagram_manage_messages",
}
SAVE_DIR = Path(__file__).resolve().parents[2] / "docs" / "pay_loads" / "auto"
TOKEN_IN_URL = re.compile(r"(access_token=)[^&\"\s]+")


class MetaError(Exception):
    def __init__(self, error: dict):
        self.code, self.subcode = error.get("code"), error.get("error_subcode")
        super().__init__(
            f"code {self.code}/{self.subcode}: {error.get('message')} (fbtrace_id {error.get('fbtrace_id')})"
        )


class Skip(Exception):
    pass


class Graph:
    def __init__(self, token: str, app_secret: str, version: str, save: bool):
        self.version, self.save = version, save
        self.base = f"https://graph.facebook.com/{version}/"
        proof = hmac.new(app_secret.encode(), token.encode(), hashlib.sha256).hexdigest()
        self.auth = {"access_token": token, "appsecret_proof": proof}

    def call(self, method: str, path: str, label: str, **params) -> dict:
        body = {k: json.dumps(v) if isinstance(v, (dict, list, bool)) else v for k, v in params.items()}
        if method == "POST":
            response = httpx.post(self.base + path, params=self.auth, data=body, timeout=60)
        else:
            response = httpx.request(method, self.base + path, params={**body, **self.auth}, timeout=30)
        data = response.json()
        if self.save:
            self._save(label, method, path, params, data)
        if "error" in data:
            raise MetaError(data["error"])
        return data

    def _save(self, label: str, method: str, path: str, params: dict, data: dict) -> None:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        shown = {
            k: ("<generated test image, base64 omitted>" if k == "bytes" else v) for k, v in params.items()
        }
        request = {"method": method, "path": "/" + path, "params": shown, "api_version": self.version}
        for kind, payload in (("request", request), ("response", data)):
            # Meta embeds the access token in paging "next" links; never write it to disk.
            text = TOKEN_IN_URL.sub(r"\1<redacted>", json.dumps(payload, indent=2))
            (SAVE_DIR / f"{label}.{kind}.json").write_text(text, encoding="utf-8")


def need(ctx: dict, key: str):
    if key not in ctx:
        raise Skip(f"needs '{key}' from an earlier step")
    return ctx[key]


def test_image_base64() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (1080, 1080), (30, 90, 200)).save(buffer, "JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


def read_steps(g: Graph, account: str, page: str) -> list:
    def token_owner(ctx):
        return g.call("GET", "me", "r0_me", fields="id,name")

    def permissions(ctx):
        data = g.call("GET", "me/permissions", "r0_permissions")["data"]
        missing = REQUIRED_PERMISSIONS - {p["permission"] for p in data if p["status"] == "granted"}
        if missing:
            raise RuntimeError(f"not granted: {sorted(missing)}")
        return "all required permissions granted"

    def ad_accounts(ctx):
        data = g.call(
            "GET",
            "me/adaccounts",
            "r1_adaccounts",
            fields="account_id,account_status,currency,min_daily_budget",
        )["data"]
        ours = next((a for a in data if a["id"] == account), None)
        if ours is None:
            raise RuntimeError(f"{account} is not in the token's ad accounts: {[a['id'] for a in data]}")
        if ours.get("account_status") != 1:
            raise RuntimeError(f"{account} account_status={ours.get('account_status')} (1 = active)")
        ctx["min_daily_budget"] = int(ours.get("min_daily_budget") or 0)
        return f"{account} active, {ours['currency']}, min_daily_budget={ctx['min_daily_budget']}"

    def pages(ctx):
        data = g.call("GET", "me/accounts", "r2_pages", fields="id,name")["data"]
        match = next((p for p in data if p["id"] == page), None)
        if match is None:
            raise RuntimeError(f"Page {page} not visible: {[p['id'] for p in data]}")
        return f"{match['name']} ({page})"

    def instagram(ctx):
        data = g.call(
            "GET", page, "r2b_instagram_account", fields="id,name,instagram_business_account{id,username}"
        )
        ig = data.get("instagram_business_account")
        if not ig:
            raise RuntimeError("Page has no linked Instagram professional account")
        ctx["instagram_user_id"] = ig["id"]
        return f"@{ig['username']} ({ig['id']})"

    def interest_search(ctx):
        data = g.call("GET", "search", "r3_search_interest_python", type="adinterest", q="python")["data"]
        if not data:
            raise RuntimeError("no interests returned")
        ctx["interest_id"] = data[0]["id"]
        return f"{data[0]['name']} -> {data[0]['id']}"

    def location_search(ctx):
        data = g.call("GET", "search", "r4_search_location_bengaluru", type="adgeolocation", q="Bengaluru")[
            "data"
        ]
        city = next((d for d in data if d.get("type") == "city"), None)
        if city is None:
            raise RuntimeError("no city returned")
        ctx["city_key"] = city["key"]
        return f"{city['name']} -> {city['key']}"

    return [
        ("R0 token owner", token_owner),
        ("R0 permissions", permissions),
        ("R1 ad accounts", ad_accounts),
        ("R2 pages", pages),
        ("R2b page -> instagram", instagram),
        ("R3 interest search", interest_search),
        ("R4 location search", location_search),
    ]


def write_steps(g: Graph, account: str, page: str) -> list:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    def upload_image(ctx):
        data = g.call("POST", f"{account}/adimages", "r5_adimages", bytes=test_image_base64())
        image = next(iter(data["images"].values()))
        ctx["image_hash"] = image["hash"]
        return f"hash {image['hash']}"

    def campaign_missing_field(ctx):
        try:
            data = g.call(
                "POST",
                f"{account}/campaigns",
                "r6_campaign_missing_budget_sharing",
                name=f"auto-check-{stamp}-should-fail",
                objective="OUTCOME_TRAFFIC",
                status="PAUSED",
                special_ad_categories=[],
            )
        except MetaError as exc:
            if (exc.code, exc.subcode) == (100, 4834011):
                return "rejected as expected (100/4834011)"
            raise
        ctx.setdefault("cleanup_campaigns", []).append(data["id"])
        raise RuntimeError("Meta accepted a campaign without is_adset_budget_sharing_enabled (rule changed?)")

    def campaign_create(ctx):
        data = g.call(
            "POST",
            f"{account}/campaigns",
            "r7_campaign_success",
            name=f"auto-check-{stamp}",
            objective="OUTCOME_TRAFFIC",
            status="PAUSED",
            special_ad_categories=[],
            is_adset_budget_sharing_enabled=False,
        )
        ctx["campaign_id"], ctx["campaign_name"] = data["id"], f"auto-check-{stamp}"
        ctx.setdefault("cleanup_campaigns", []).append(data["id"])
        return f"campaign {data['id']} (PAUSED)"

    def create_adset(ctx, label: str, optimization_goal: str, positions: list[str], **extra) -> str:
        start = (datetime.now(UTC) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
        targeting = {
            "geo_locations": {"cities": [{"key": need(ctx, "city_key")}]},
            "flexible_spec": [{"interests": [{"id": need(ctx, "interest_id")}]}],
            "publisher_platforms": ["instagram"],
            "instagram_positions": positions,
            "targeting_automation": {"advantage_audience": 0},
        }
        data = g.call(
            "POST",
            f"{account}/adsets",
            label,
            name=f"auto-check-{stamp}-adset",
            campaign_id=need(ctx, "campaign_id"),
            lifetime_budget=str(max(10000, ctx.get("min_daily_budget", 0) + 1000)),
            start_time=start.strftime("%Y-%m-%dT%H:%M:%S+0000"),
            end_time=(start + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S+0000"),
            billing_event="IMPRESSIONS",
            optimization_goal=optimization_goal,
            bid_strategy="LOWEST_COST_WITHOUT_CAP",
            status="PAUSED",
            targeting=targeting,
            **extra,
        )
        ctx["adset_id"] = data["id"]
        return f"ad set {data['id']} (PAUSED, {optimization_goal}, Instagram {'+'.join(positions)})"

    def adset_app_plan(ctx):
        # IG Explore is deprecated in v26 (error 100/2490589), so the app uses the feed ("stream") only.
        return create_adset(ctx, "r8_adset_app_plan", "LINK_CLICKS", ["stream"], destination_type="WEBSITE")

    def adset_m0_fallback(ctx):
        if "adset_id" in ctx:
            raise Skip("not needed, R8 worked")
        return create_adset(ctx, "r8b_adset_m0_config", "IMPRESSIONS", ["stream"])

    def creative_create(ctx):
        link = os.environ.get("META_TEST_LINK", "https://www.example.com")
        story = {
            "page_id": page,
            "instagram_user_id": need(ctx, "instagram_user_id"),
            "link_data": {
                "link": link,
                "message": "Automated API check. This ad is never activated.",
                "name": "Automated check",
                "description": "Test only",
                "image_hash": need(ctx, "image_hash"),
                "call_to_action": {"type": "LEARN_MORE", "value": {"link": link}},
            },
        }
        data = g.call(
            "POST",
            f"{account}/adcreatives",
            "r9_adcreative",
            name=f"auto-check-{stamp}-creative",
            object_story_spec=story,
        )
        ctx["creative_id"] = data["id"]
        return f"creative {data['id']} (page {page}, instagram {ctx['instagram_user_id']})"

    def ad_create(ctx):
        data = g.call(
            "POST",
            f"{account}/ads",
            "r10_ad",
            name=f"auto-check-{stamp}-ad",
            adset_id=need(ctx, "adset_id"),
            creative={"creative_id": need(ctx, "creative_id")},
            status="PAUSED",
        )
        ctx["ad_id"] = data["id"]
        return f"ad {data['id']} (PAUSED)"

    def find_campaign_by_name(ctx):
        name = need(ctx, "campaign_name")
        data = g.call(
            "GET",
            f"{account}/campaigns",
            "r11_find_campaign_by_name",
            fields="id,name",
            filtering=[{"field": "name", "operator": "EQUAL", "value": name}],
        )["data"]
        if need(ctx, "campaign_id") not in [c["id"] for c in data]:
            raise RuntimeError(f"name lookup did not return {ctx['campaign_id']}: {data}")
        return f"found {ctx['campaign_id']} by name '{name}'"

    def ad_status(ctx):
        data = g.call(
            "GET", need(ctx, "ad_id"), "r12_ad_status", fields="status,effective_status,configured_status"
        )
        if data.get("status") != "PAUSED":
            raise RuntimeError(f"expected PAUSED, got {data}")
        return f"status {data['status']}, effective_status {data.get('effective_status')}"

    def insights(ctx):
        data = g.call(
            "GET",
            f"{need(ctx, 'campaign_id')}/insights",
            "r13_insights",
            level="ad",
            time_increment=1,
            date_preset="last_7d",
            fields="ad_id,impressions,reach,frequency,clicks,inline_link_clicks,ctr,cpc,cpm,spend,date_start,date_stop",
        )["data"]
        return f"{len(data)} rows (empty is expected: a paused ad has no delivery)"

    return [
        ("R5 upload image", upload_image),
        ("R6 campaign without budget field", campaign_missing_field),
        ("R7 campaign create", campaign_create),
        ("R8 ad set (app plan: LINK_CLICKS, feed)", adset_app_plan),
        ("R8b ad set fallback (M0 config)", adset_m0_fallback),
        ("R9 ad creative (page + instagram_user_id)", creative_create),
        ("R10 ad create", ad_create),
        ("R11 find campaign by name", find_campaign_by_name),
        ("R12 ad status", ad_status),
        ("R13 insights", insights),
    ]


def cleanup(g: Graph, account: str, ctx: dict) -> None:
    for campaign_id in ctx.get("cleanup_campaigns", []):
        try:
            g.call("DELETE", campaign_id, "cleanup_campaign")
            print(f"CLEAN deleted campaign {campaign_id} (its ad sets go with it)")
        except Exception as exc:
            print(f"CLEAN could not delete campaign {campaign_id}: {exc} -> delete it in Ads Manager")
    if "creative_id" in ctx:
        try:
            g.call("DELETE", ctx["creative_id"], "cleanup_creative")
            print(f"CLEAN deleted creative {ctx['creative_id']}")
        except Exception as exc:
            print(f"CLEAN could not delete creative {ctx['creative_id']}: {exc}")
    if "image_hash" in ctx:
        try:
            g.call("DELETE", f"{account}/adimages", "cleanup_image", hash=ctx["image_hash"])
            print(f"CLEAN deleted test image {ctx['image_hash']}")
        except Exception as exc:
            print(f"CLEAN could not delete test image: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--write", action="store_true", help="also run R5-R13 (PAUSED objects, auto-deleted)")
    parser.add_argument(
        "--save", action="store_true", help="save request/response JSON to docs/pay_loads/auto/"
    )
    args = parser.parse_args()

    missing_env = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing_env:
        sys.exit(f"Missing in .env: {', '.join(missing_env)}")
    account, page = os.environ["META_AD_ACCOUNT_ID"], os.environ["META_PAGE_ID"]
    g = Graph(
        os.environ["META_ACCESS_TOKEN"],
        os.environ["META_APP_SECRET"],
        os.environ.get("META_API_VERSION", "v26.0"),
        args.save,
    )

    steps = read_steps(g, account, page) + (write_steps(g, account, page) if args.write else [])
    ctx: dict = {}
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    try:
        for name, step in steps:
            try:
                status, detail = "PASS", step(ctx)
            except Skip as exc:
                status, detail = "SKIP", exc
            except Exception as exc:
                status, detail = "FAIL", exc
            counts[status] += 1
            print(f"{status}  {name}: {detail}")
    finally:
        if args.write:
            cleanup(g, account, ctx)

    print(f"\n{counts['PASS']} passed, {counts['FAIL']} failed, {counts['SKIP']} skipped")
    if args.save:
        print(f"Saved request/response files to {SAVE_DIR}")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
