# Platform Selection & Recommendation — Ad Campaign Manager

> Document 1 of 3 · Last verified: 6 Oct 2026 · Status: Final (platform locked for the batch)

## 1. Summary

**Selected platform: Meta Ads via the Meta Marketing API (Graph API v26.0), with ads placed on Instagram only** (Instagram feed and Explore in v1). Instagram ads are created, targeted, published and measured through the same Meta Marketing API as Facebook ads; the placement is chosen on the ad set (§6.8).

Meta is the only candidate that meets all four hard requirements for this project at once:

1. It is a **social media** ad platform (the brief requires one, which rules out Google Search Ads as the primary choice).
2. A developer can get **read/write API access to a test ad account the same day**, with no business verification and no payment method (Sandbox Ad Accounts).
3. Its official API covers the **full lifecycle** the brief asks for: campaign → targeting → creative/asset upload → publish/activate → insights.
4. It has a mature official Python SDK and a web-based Graph API Explorer for manual testing.

The main limitation is that **sandbox ad accounts never deliver ads**, so they produce no real impressions, clicks or spend. Section 7 describes how the project handles this honestly.

---

## 2. Method

Every claim below is labelled with one of three categories:

| Label | Meaning |
|---|---|
| **[Verified]** | Checked against official platform documentation or changelogs on the date above |
| **[Inferred]** | Our engineering judgement (effort, risk, fit) based on the verified facts |
| **[To verify in Phase 1]** | Plausible but must be confirmed with a real API call before we depend on it |

Assumptions for this project: intern developers with personal Meta accounts, no real ad budget required, and the whole flow must be demonstrable end to end.

---

## 3. Selection Criteria and Weights

| # | Criterion | Weight | Why it matters for this project |
|---|---|---|---|
| C1 | Is it a social media ad platform? | Gate (pass/fail) | Required by the brief |
| C2 | Self-serve test environment | 25% | Without it we cannot demo publishing |
| C3 | Lifecycle API coverage (create, assets, targeting, publish, insights) | 25% | All 10 brief capabilities depend on it |
| C4 | Access barrier (approval, business verification, paid tier) | 20% | Schedule risk for an internship |
| C5 | Documentation and tooling | 15% | Speed of learning an unfamiliar API |
| C6 | Fit for text-first AI generation | 15% | Our agent generates copy and image concepts, not finished video |

Scores are on a 1–5 scale. Weighted total = Σ(score × weight).

---

## 4. Candidate Evaluation

### 4.1 Meta Ads (Facebook & Instagram)

- **Object model [Verified]:** Ad Account → **Campaign** (objective) → **Ad Set** (budget, schedule, targeting, optimization goal) → **Ad**. An **Ad Creative** is a separate, reusable object that the Ad references. Images are uploaded first to the ad account and referenced by hash.
- **Objectives [Verified]:** The current objectives are the "outcome" set: `OUTCOME_AWARENESS`, `OUTCOME_TRAFFIC`, `OUTCOME_ENGAGEMENT`, `OUTCOME_LEADS`, `OUTCOME_APP_PROMOTION` and `OUTCOME_SALES`.
- **Test environment [Verified]:** Sandbox Ad Accounts, created from the App Dashboard after you add the Marketing API product. They support read and write calls but never deliver ads and need no payment method.
- **Auth [Verified]:** OAuth 2.0 (Facebook Login / Facebook Login for Business). Short-lived user tokens (about 1–2 hours) can be exchanged for long-lived tokens (about 60 days). **There is no refresh token.** When a long-lived token expires, the user has to log in again. System User tokens from a Business portfolio are the production alternative.
- **Access tiers [Verified]:** New apps start with **Development**-tier Marketing API access: low rate limits, and only ad accounts the app's admins and developers can access. Standard access requires App Review. Development tier is enough for this project.
- **Analytics [Verified]:** The Insights edge (`/{object_id}/insights`) supports levels from account down to ad, daily breakdowns and custom date ranges.
- **Docs and tooling [Verified]:** Graph API Explorer, the official `facebook-business` Python SDK, and a versioned changelog.

### 4.2 Google Ads

- Fails the **C1 gate** as a primary platform: Google Ads is search, display and YouTube, not a social network.
- **[Verified]** A developer token with *Test Account Access* is issued immediately and works only against test accounts, which do not serve ads. Basic or Standard access needs an application and review.
- **[Inferred]** The API is powerful but heavy (Google Ads Query Language for reporting, deeply nested mutate operations).

### 4.3 LinkedIn Ads

- **[Verified]** The Advertising API is **not self-serve**: you apply for access to the Marketing Developer Platform, and once approved you get a development tier with test ad accounts.
- **[Inferred]** It is the best fit for B2B "software developer" targeting (job titles, skills), but approval timing is outside our control and could block the whole project.

### 4.4 TikTok Ads

- **[Verified]** The Marketing API has a sandbox after developer registration. Approval can require business details.
- **[Inferred]** Ads are video-first. A text and image-concept generator does not produce a publishable TikTok asset without a video pipeline, which is out of scope.

### 4.5 X (Twitter) Ads

- **[Verified]** Ads API access needs a separate application on top of a developer account. Developer access has moved to paid tiers.
- **[Inferred]** The access path is uncertain and the docs and community are smaller. High schedule risk.

### 4.6 Pinterest Ads

- **[Verified]** API v5 has trial access, then standard access after review.
- **[Inferred]** It is image-heavy, has a smaller audience for a developer-tools product in India, and less community tooling.

---

## 5. Comparison Matrix

| Criterion (weight) | Meta | LinkedIn | TikTok | Pinterest | X | Google |
|---|---|---|---|---|---|---|
| C1 Social platform (gate) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| C2 Self-serve test env (25%) | 5 | 2 | 3 | 3 | 1 | 3 |
| C3 Lifecycle coverage (25%) | 5 | 4 | 4 | 4 | 3 | 5 |
| C4 Access barrier (20%) | 5 | 1 | 3 | 3 | 1 | 3 |
| C5 Docs & tooling (15%) | 4 | 3 | 3 | 3 | 2 | 4 |
| C6 Text-first AI fit (15%) | 5 | 5 | 2 | 3 | 4 | 4 |
| **Weighted total (out of 5)** | **4.85** | **2.90** | **3.10** | **3.25** | **2.10** | n/a (gate) |

Scores are **[Inferred]**: they summarise sections 4.1–4.6 and are not measurements.

---

## 6. Meta Marketing API — What We Will Use

### 6.1 Versioning

- **[Verified]** Current version: **v26.0** (released 29 Jul 2026). v25.0 was released 18 Feb 2026. **v24.0 expires 6 Oct 2026.** Each version lives about two years.
- **Decision:** the version is a config value (`META_API_VERSION=v26.0`), never hard-coded. The README links the changelog, and upgrading is a single config change plus a regression run of the evaluation suite.

### 6.2 Endpoints (in call order)

Base URL: `https://graph.facebook.com/{META_API_VERSION}/`

| Step | Call | Purpose | Key fields |
|---|---|---|---|
| R1 | `GET /me/adaccounts` | List ad accounts the user can use | `account_id`, `account_status`, `currency`, `min_daily_budget` |
| R2 | `GET /me/accounts` | List Facebook Pages (needed for creatives) | `id`, `name` |
| R2b | `GET /{page_id}?fields=instagram_business_account{id,username}` | Find the Instagram professional account linked to the Page **[To verify in Phase 1]** | `instagram_business_account.id` → used as `instagram_user_id` |
| R3 | `GET /search?type=adinterest&q=…` | Resolve interest **names → IDs** | `id`, `name`, `audience_size_*` |
| R4 | `GET /search?type=adgeolocation&q=…` | Resolve cities and regions → keys | `key`, `type`, `country_code` |
| R5 | `GET /act_{id}/delivery_estimate` | Audience size estimate for a targeting spec | `estimate_mau_*` |
| P1 | `POST /act_{id}/adimages` | Upload image, returns `hash` | `bytes` or file |
| P2 | `POST /act_{id}/campaigns` | Create campaign (PAUSED) | `name`, `objective`, `special_ad_categories`, `status`, and `is_adset_budget_sharing_enabled` when budget is on the ad set |
| P3 | `POST /act_{id}/adsets` | Create ad set (PAUSED) | `campaign_id`, `optimization_goal`, `billing_event`, `bid_strategy`, `daily_budget` or `lifetime_budget`+`end_time`, `start_time`, `targeting` (incl. `publisher_platforms: ["instagram"]`, `instagram_positions`), `status` |
| P4 | `POST /act_{id}/adcreatives` | Create creative | `object_story_spec.page_id`, `object_story_spec.instagram_user_id`, `link_data{link, message, name, description, image_hash, call_to_action}` |
| P5 | `POST /act_{id}/ads` | Create one ad per approved variant (PAUSED) | `adset_id`, `creative{creative_id}`, `status` |
| A1 | `POST /{object_id}` | Activate, pause or update budget | `status=ACTIVE` / `PAUSED`, `daily_budget` |
| M1 | `GET /{object_id}?fields=effective_status,…` | Check delivery and ad review state | `effective_status` (`PENDING_REVIEW`, `ACTIVE`, `DISAPPROVED`, …) |
| M2 | `GET /{campaign_id}/insights` | Metrics | `level=ad`, `time_increment=1`, `time_range`, fields below |
| X1 | `DELETE /{object_id}` | Cleanup if a user discards a half-published campaign | — |

**Notes [Verified]:**

- `special_ad_categories` is required on every campaign. Use `[]` when none apply. Housing, employment, credit and similar categories restrict targeting.
- In v26, creating a campaign **without** a campaign budget and **without** `is_adset_budget_sharing_enabled` fails with error `100`, subcode `4834011`.
- Budgets are integers in the account currency's **minor unit** (paise for INR). The minimum depends on currency and settings, so we read `min_daily_budget` from the ad account rather than hard-coding $1.
- For a "₹50,000 over 30 days" brief, we use `lifetime_budget = 5000000` (paise) with `start_time`/`end_time` on the ad set rather than a derived daily budget.
- Traffic campaigns: `optimization_goal = LINK_CLICKS` (or `LANDING_PAGE_VIEWS`, which needs a pixel), `billing_event = IMPRESSIONS`, `bid_strategy = LOWEST_COST_WITHOUT_CAP`.
- Targeting uses **IDs**, not free-text names: `{"geo_locations":{"countries":["IN"]},"age_min":22,"age_max":45,"flexible_spec":[{"interests":[{"id":"…","name":"…"}]}]}`.
- **[To verify in Phase 1]** Whether v26 requires an explicit Advantage+ audience flag (`targeting_automation.advantage_audience`) on ad sets, and its default.
- **[To verify in Phase 1]** Which Page permission the creative call requires for our app type (`pages_read_engagement` vs `pages_manage_ads`).

### 6.3 Creative Text: Platform Limits vs Our Policy

**[Verified]** Meta's recommended lengths (headline ~40, primary text ~125, description ~30 characters) are **guidance to avoid truncation in the feed, not hard API limits**. The API accepts longer text.

**Decision:** we enforce 40 / 125 / 30 as **our own policy**, so every variant displays fully on mobile feeds. The validation layer (HLD §7.4) rejects longer text before anything reaches Meta.

CTA values come from Meta's `call_to_action.type` enum. Our v1 allow-list: `LEARN_MORE`, `SIGN_UP`, `DOWNLOAD`, `GET_QUOTE`, `CONTACT_US`, `SUBSCRIBE`.

### 6.4 Ad Review (Policy)

**[Verified]** Policy review is **asynchronous**. A call that creates an ad succeeds; when the ad is activated it goes to `PENDING_REVIEW`, then to `ACTIVE` or `DISAPPROVED`. A policy problem is therefore **not** an error code at creation time. The monitoring job polls `effective_status` and shows any disapproval reason to the user.

### 6.5 Insights Fields

**[Verified]** Fields we request: `impressions`, `reach`, `frequency`, `clicks`, `inline_link_clicks`, `ctr`, `inline_link_click_ctr`, `cpc`, `cpm`, `spend`, `actions`, `cost_per_action_type`, `date_start`, `date_stop`.

| Metric | Available? | Notes |
|---|---|---|
| Impressions, reach, frequency | Yes | **Reach is not additive across days.** Request it for the whole range; never sum daily values |
| Clicks, link clicks, CTR, CPC, CPM | Yes | |
| Spend | Yes | Account currency |
| Engagement | Yes, via `actions` (e.g. `post_engagement`) | |
| Conversions | Only with a Meta Pixel / Conversions API dataset | Out of scope for v1 (no pixel). Documented as a limitation |

**[Verified]** Recent figures can still change for a few days (attribution and late events). The collector re-fetches the last 3 days on each run and upserts.

### 6.6 Authentication and Security

| Item | Approach |
|---|---|
| Flow | OAuth 2.0 authorization code via Facebook Login. Redirect URI registered in the app (HTTPS in production; localhost allowed in development) |
| Scopes | `ads_management`, `ads_read`, `pages_show_list`, `instagram_basic` (to read the linked Instagram account — **[To verify in Phase 1]**), plus the Page permission confirmed in Phase 1 |
| Token lifetime | Exchange the short-lived token for a long-lived one (~60 days) via `GET /oauth/access_token?grant_type=fb_exchange_token`. Store its expiry |
| Refresh | **No refresh token exists.** 7 days before expiry the UI asks the user to reconnect. On error `190` the connection is marked `EXPIRED` and Meta calls stop |
| Storage | Token encrypted at rest with AES-256-GCM (key from an environment secret), never logged, never sent to the LLM |
| `appsecret_proof` | `hex(HMAC_SHA256(key = APP_SECRET, message = access_token))`, sent as a **query parameter** on every server call. Enable "Require App Secret" in the app settings |
| Who can connect | While the app is in Development mode, only users with an app role (admin, developer, tester) can authorize it. Evaluators are added as testers |

### 6.7 Rate Limits

**[Verified]**

- Marketing API calls are limited by **Business Use Case (BUC)** quotas per ad account. Usage is returned in the `X-Business-Use-Case-Usage` response header, which includes `estimated_time_to_regain_access`.
- Other relevant headers: `X-App-Usage`, `X-Ad-Account-Usage`, and `x-fb-ads-insights-throttle` for Insights.
- Throttling error **codes**: `4` (app), `17` (user), `613` (calls per hour), and the `80000`-series for BUC limits (for example `80004` for ads management).
- The Development tier has much lower quotas than Standard.

**Handling:** read the usage headers on every response, slow down above 75% usage, back off with jitter on a throttling code, and wait at least `estimated_time_to_regain_access` when it is given.

### 6.8 Instagram Placement (v1 runs on Instagram only)

| Topic | Detail |
|---|---|
| Account requirement **[Verified]** | The advertiser needs an Instagram **professional** (business or creator) account linked to the Facebook Page / business portfolio used for the ads. The Page is still required in the creative |
| Identity field **[Verified]** | The creative's `object_story_spec` uses **`instagram_user_id`**. The old `instagram_actor_id` was replaced (Marketing API migration deadline 21 Jan 2026), so v26 code must use `instagram_user_id` |
| Placement **[Verified]** | Ad set `targeting.publisher_platforms = ["instagram"]` and `targeting.instagram_positions` (values include `stream` (feed), `explore`, `story`, `reels`, `profile_feed`). v1 uses `["stream", "explore"]` — both accept feed-shaped images. Stories/Reels need 9:16 assets and are a later extension. Exact position values **[To verify in Phase 1]** |
| Image **[Verified guidance]** | An image is mandatory on Instagram. JPG/PNG; aspect ratio between 1.91:1 and 4:5 (1:1 1080×1080 or 4:5 1080×1350 recommended); we require width ≥ 600 px and ≤ 8 MB, checked in code before upload |
| Copy | The primary text is the Instagram caption: shown truncated after ~125 characters (our limit). Headline and description appear only on some placements — still generated and validated |
| CTA | Same `call_to_action.type` enum; shown as a button under the image |
| Insights | Same Insights API; `breakdowns=publisher_platform,platform_position` splits results by Instagram position |
| Sandbox caveat **[To verify in Phase 1]** | Whether a sandbox ad account can create a creative with `instagram_user_id`. If not: link a test Instagram professional account to the test Page, or record this as a documented limitation and use the fake gateway for the demo of that step |

---

## 7. Limitations and How We Handle Them

| # | Limitation | Impact | Our handling |
|---|---|---|---|
| L1 | Sandbox accounts never deliver ads | No real metrics | `MOCK_METRICS=true` turns on a simulator that writes rows marked `is_simulated=true`. The UI shows a **SIMULATED DATA** badge, and analyses say so in their data-quality notes. The real Insights call still runs and its (empty) response is logged |
| L2 | Real metrics need a real ad account and money | Mock only, unless budget is approved | **Optional:** run a ₹100–200/day campaign for 2–3 days on a real account (needs a payment method and a real Page) to show real insights in the demo |
| L3 | A Facebook Page is mandatory for creatives | Setup step | Create a test Page during Phase 1. The user picks the Page in the UI |
| L4 | No refresh tokens | Re-login every ~60 days | Expiry tracking and a reconnect prompt (§6.6) |
| L5 | Development-mode app | Only app-role users can connect | Add evaluators as testers. Documented in the README |
| L6 | Interest targeting is coarse | No direct "job = software developer" targeting | Use interest IDs (programming languages, developer tools) and show the audience estimate. Documented as an approximation |
| L7 | Asynchronous ad review | Disapproval appears after activation | Monitoring polls `effective_status` and surfaces the reason |
| L8 | No conversions without a pixel | Cost per result unavailable | Analyse clicks, CTR, CPC, CPM and frequency only |
| L9 | API versions expire about every 2 years | Calls break after expiry | Version in config; changelog check in the README |
| L10 | Meta has no idempotency key on create calls | Retries could create duplicates | Deterministic object names and a look-up before retry (HLD §10) |
| L11 | Instagram ads need a linked Instagram professional account | Setup step for every user | Connection flow reads the linked account; campaign creation is blocked until one exists |
| L12 | Instagram requires an image with a supported aspect ratio | Upload can be rejected | Size/ratio checked in code on upload, with a clear message |
| L13 | Sandbox support for Instagram creatives is unconfirmed | Publish step may fail in sandbox | Verified in Milestone 0; fallback documented in §6.8 |

---

## 8. Phase 1 Setup Checklist

1. Create a Meta for Developers account and register as a developer.
2. Create an app with the **Business** use case, then add **Marketing API**.
3. Create a **Sandbox Ad Account** under Marketing API → Tools and note `act_<id>`.
4. Create a test **Facebook Page** and link an **Instagram professional account** to it (Page settings → Linked accounts). Note the Instagram account id from call R2b.
5. In Graph API Explorer, generate a token with the scopes from §6.6.
6. Call P1–P5 by hand on `v26.0` and save the working request and response bodies to `docs/meta-payloads/`. This is the contract the adapter is built and tested against.
7. Resolve every **[To verify in Phase 1]** item and update this document.
8. Add teammates and evaluators as app **testers**.

---

## 9. References

- Graph API versions and expiry: https://developers.facebook.com/docs/graph-api/changelog/versions/
- Marketing API overview: https://developers.facebook.com/docs/marketing-apis/
- Sandbox ad accounts: https://developers.facebook.com/ads/blog/post/v2/2016/10/19/sandbox-ad-accounts/
- Insights API: https://developers.facebook.com/docs/marketing-api/insights/
- Rate limiting: https://developers.facebook.com/docs/graph-api/overview/rate-limiting/
- Securing requests (`appsecret_proof`): https://developers.facebook.com/docs/graph-api/securing-requests/
- Access tokens: https://developers.facebook.com/docs/facebook-login/guides/access-tokens/
- Google Ads API access levels: https://developers.google.com/google-ads/api/docs/access-levels
- LinkedIn Marketing API: https://learn.microsoft.com/en-us/linkedin/marketing/
- TikTok API for Business: https://business-api.tiktok.com/portal/docs
