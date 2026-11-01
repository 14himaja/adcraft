# AdCraft: Social Media Platform Research & Selection Document
## Platform Evaluation, Trade-Offs & API Capabilities

---

### 1. Executive Summary

As part of Phase 0 of this project, we conducted extensive research across major social media advertising platforms to select the single best platform for building an AI-powered ad campaign manager.

The evaluation compared **Meta (Facebook & Instagram)**, **LinkedIn Ads**, **TikTok Ads**, **X (formerly Twitter) Ads**, **Google Ads**, and **Pinterest Ads**.

**Decision:** We selected **Meta Ads via Marketing API (Graph API v26.0)** targeting **Instagram and Facebook**.

---

### 2. The Four Mandatory Selection Gates

Before scoring platforms, we established four non-negotiable criteria ("Hard Gates") that any platform had to satisfy:

| Gate | Requirement | Why it is mandatory |
|---|---|---|
| **Gate 1: Social Platform** | Must be a social media platform | The project brief requires a social media marketing platform. This eliminates Google Search Ads. |
| **Gate 2: Day-1 Sandbox Access** | Must allow instant developer onboarding and sandbox accounts | The project timeline cannot tolerate multi-week corporate verification or enterprise sales approvals. |
| **Gate 3: Full Lifecycle API** | Must expose APIs for Campaign, AdSet, Creative, Publishing, and Analytics | The application must create and monitor ads end-to-end, not just edit drafts. |
| **Gate 4: Official Python SDK** | Must have an actively maintained official Python SDK | Ensures robust type handling, retry mechanics, and clean integration with modern async Python. |

---

### 3. Comprehensive Platform Comparison Matrix

| Platform | Campaign Creation API | Analytics / Insights API | Sandbox Capabilities | Developer Access Speed | Official Python SDK | Verdict |
|---|---|---|---|---|---|---|
| **Meta (Facebook & Instagram)** | **Yes (Full)** | **Yes (Full)** | **Yes (Instant Sandbox Accounts)** | **Immediate (Self-service)** | **Yes (`facebook-business`)** | **SELECTED (Winner)** |
| **LinkedIn Ads** | Yes | Yes | Limited / Requires live billing | 2–4 weeks manual review | Community-only | Rejected (Slow onboarding, expensive B2B minimums) |
| **TikTok Ads** | Yes | Yes | Sandbox restricted by region | 1–3 weeks business review | No official Python SDK | Rejected (Strict geographic gates, SDK missing) |
| **X (Twitter) Ads** | Limited | Limited | Deprecated / Invite-only | \$100–\$5,000/month API tier | Community-only | Rejected (High paywalls, unstable developer tiers) |
| **Google Ads** | Yes (Search/Display) | Yes | Yes (Test accounts) | Instant | Yes (`google-ads`) | Rejected (Not a social media platform per Gate 1) |
| **Pinterest Ads** | Yes | Yes | No sandbox environment | 1–2 weeks manual review | Community-only | Rejected (No sandbox, niche ecommerce focus) |

---

### 4. Why Meta Ads Was Selected

Meta (combining Instagram and Facebook) is the undisputed gold standard for social media advertising:

1. **Massive Reach:** Unified access to over 3.9 billion monthly active users across Facebook, Instagram, Messenger, and Audience Network.
2. **Official Python SDK:** Meta provides `facebook-business`, a battle-tested, officially maintained Python library supporting Graph API v26.0.
3. **Instant Sandbox Access:** Meta allows developers to create sandbox ad accounts within 60 seconds from the Meta Developer Dashboard, with no credit card required.
4. **Rich Targeting APIs:** Meta provides direct search endpoints (`act_{id}/delivery_estimate`, `search?type=adinterest`, `search?type=adgeolocation`), allowing the AI agent to search real audiences dynamically.
5. **Real-Time Customer Messaging:** Meta's Graph API supports Instagram Webhooks, allowing us to build an automated Instagram Direct Message (DM) agent that interacts with real customers.
6. **Dual Publishing Capability:** Meta supports both paid advertising via Marketing API and organic publishing (zero ad spend) via Content Publishing API.

---

### 5. Meta Marketing API v26.0 Capabilities

AdCraft integrates with the following core Meta Graph API endpoints:

```
                      +-----------------------------+
                      |     META GRAPH API v26.0    |
                      +-----------------------------+
                                     |
    +-----------------+--------------+----------------+----------------+
    |                 |                               |                |
    v                 v                               v                v
[ me/adaccounts ]  [ act_{id}/campaigns ]   [ act_{id}/adimages ]  [ act_{id}/insights ]
Lists ad accounts  Creates campaign         Uploads 1080x1080      Retrieves real-time
and billing info   container with objective JPEG creative          impressions, clicks,
                                                                   spend, and CTR
    |                 |                               |
    |                 v                               v
    |              [ act_{id}/adsets ]         [ act_{id}/adcreatives ]
    |              Sets budget, dates, and     Pairs image hash with
    |              demographic targeting       headline, body, and CTA
    |                                                 |
    +-------------------------------------------------+
                                     |
                                     v
                             [ act_{id}/ads ]
                             Creates the final ad object
                             and handles pause/activation
```

#### Detailed Endpoint Reference:
- **Campaign Creation:** `POST /v26.0/act_{ad_account_id}/campaigns`
  - Defines the campaign container, objective (`OUTCOME_TRAFFIC` or `OUTCOME_AWARENESS`), and status (`PAUSED`).
- **Ad Set Creation:** `POST /v26.0/act_{ad_account_id}/adsets`
  - Configures daily budget (e.g. 50,000 paise = ₹500), start time, end time, billing event (`IMPRESSIONS`), optimization goal (`LINK_CLICKS`), and targeting (countries, ages, interests).
- **Creative Upload:** `POST /v26.0/act_{ad_account_id}/adimages`
  - Uploads raw JPEG bytes and returns a permanent `image_hash`.
- **Ad Creative Object:** `POST /v26.0/act_{ad_account_id}/adcreatives`
  - Links the image hash, headline, primary body text, website landing URL, and call-to-action button (e.g., `LEARN_MORE`).
- **Ad Creation:** `POST /v26.0/act_{ad_account_id}/ads`
  - Links the ad set and creative together. Created in `PAUSED` status.
- **Ad Activation:** `POST /v26.0/{ad_id}` with `status="ACTIVE"`.
- **Analytics & Insights:** `GET /v26.0/{object_id}/insights`
  - Returns impressions, clicks, spend, reach, CTR, CPC, and conversion actions.

---

### 6. Authentication & Token Management

Meta requires secure OAuth 2.0 authentication. Passwords are **never** stored.

```
+------------+       1. Click "Connect Meta"       +--------------------+
|  AdCraft   | ----------------------------------> | Facebook Login for |
|  Frontend  | <---------------------------------- |      Business      |
+------------+     2. Returns Short-Lived Token    +--------------------+
      |
      | 3. Send token to Backend
      v
+------------+       4. Exchange Token Request     +--------------------+
|  AdCraft   | ----------------------------------> |   Meta Graph API   |
|  Backend   | <---------------------------------- |    OAuth Server    |
+------------+     5. Returns 60-Day Long Token    +--------------------+
      |
      | 6. AES-256-GCM Encrypt
      v
+-----------------------+
| MongoDB `connections` | (Stored as encrypted ciphertext)
+-----------------------+
```

1. **Short-Lived Token:** The user completes Facebook Login for Business in the browser, granting permissions. Meta returns a token valid for 1–2 hours.
2. **Long-Lived Token Exchange:** The backend immediately calls:
   `GET /oauth/access_token?grant_type=fb_exchange_token&client_id={id}&client_secret={secret}&fb_exchange_token={short_token}`
   Meta returns a **60-day long-lived access token**.
3. **Encrypted Storage:** The token is encrypted using **AES-256-GCM authenticated encryption** (`TOKEN_ENCRYPTION_KEY`) before saving in MongoDB. It is decrypted only in memory when making API calls.
4. **Expiration Detection:** Every API request verifies `token_expires_at <= clock.now()`. If expired, the application cleanly prompts the user to reconnect.

---

### 7. Rate Limits & Error Handling

Meta enforces strict API rate limits. AdCraft handles them defensively:

| Meta Error Code | Meaning | How AdCraft Handles It |
|---|---|---|
| **Code 17** | User request rate limit reached | Exponential backoff with random jitter (waits 2s, 4s, 8s, up to 5 retries). |
| **Code 4** | Application-level rate limit | Same exponential backoff policy; logs warning in audit trail. |
| **Code 613** | Insights API rate limit | Strict 5-minute caching per campaign prevents repeated calls. |
| **Code 190** | Access token expired or revoked | Catches error, marks connection as `EXPIRED`, and guides user to re-authenticate. |
| **Code 100** | Invalid parameter (e.g. bad date) | Surfaces user-friendly validation error; does not retry invalid requests. |

---

### 8. Platform Limitations & Workarounds

During research, we discovered several platform-specific constraints and engineered robust solutions:

1. **Sandbox Ad Delivery Limitation:**
   - *Limitation:* Meta Sandbox ad accounts accept campaigns and generate valid IDs, but Meta's delivery engine does **not** deliver sandbox ads to real users. Therefore, sandbox impressions remain at 0.
   - *Solution:* AdCraft includes a safe metrics simulator (`MOCK_METRICS=true`). When enabled in development, it generates realistic CTR, CPC, and impression trends for demonstration and testing, while leaving real API publishing intact.
2. **Deprecated Instagram Explore Placement:**
   - *Limitation:* In Graph API v26.0, Meta deprecated the standalone `explore` placement parameter. Sending it causes API rejection.
   - *Solution:* Our configuration automatically filters out `explore` (`instagram_position_list`), defaulting safely to Instagram Feed (`stream`) and Stories.
3. **Aspect Ratio Requirements:**
   - *Limitation:* Feed ads require square (1:1) aspect ratios (1080x1080 pixels), while Stories require vertical (9:16) aspect ratios (1080x1920 pixels).
   - *Solution:* AdCraft's media pipeline (`app/domain/media.py`) automatically centre-crops, resizes, and validates images to exact 1080x1080 pixels with JPEG quality 90 before uploading to Meta.

---

### 9. Conclusion

Meta Ads via Marketing API v26.0 provides the most comprehensive, developer-accessible, and production-ready foundation for this project. Its rich targeting endpoints, official Python SDK, multi-platform coverage (Instagram & Facebook), and real-time webhook infrastructure make it the ideal choice for AdCraft.
