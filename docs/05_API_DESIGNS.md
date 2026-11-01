# AdCraft: API Design & Endpoint Specification
## RESTful API Catalog, Meta Graph Endpoints & Webhooks

---

### 1. API Architecture & Standards

All AdCraft backend endpoints follow strict REST conventions:
- **Base URL:** `http://localhost:8000/api/v1`
- **Authentication:** Session managed via `HttpOnly`, `SameSite=Lax` JWT cookie (`access_token`).
- **Data Format:** `application/json` (except media upload which accepts `multipart/form-data`).
- **Standard Error Envelope:**
  ```json
  {
    "error": {
      "code": "VALIDATION_ERROR",
      "message": "Headline exceeds maximum length of 40 characters",
      "details": { "field": "headline", "length": 46, "limit": 40 }
    }
  }
  ```

---

### 2. Complete REST API Catalog

#### A. Authentication & Workspace Management (`/api/v1/auth`)

| Method | Endpoint | Description | Request Body / Params | Response |
|---|---|---|---|---|
| `POST` | `/auth/register` | Register new user account and auto-create default workspace | `{ "email": "...", "password": "...", "full_name": "..." }` | `{ "user": { "id": "...", "email": "..." } }` |
| `POST` | `/auth/login` | Log in user and set JWT cookie | `{ "email": "...", "password": "..." }` | `{ "user": { "id": "...", "workspaces": [...] } }` |
| `POST` | `/auth/logout` | Log out user and clear cookie | None | `{ "status": "logged_out" }` |
| `GET` | `/auth/me` | Get current authenticated user profile and active workspace | None | `{ "user": { ... }, "active_workspace": { ... } }` |
| `POST` | `/auth/switch-workspace` | Switch current active workspace context | `{ "workspace_id": "..." }` | `{ "active_workspace": { ... } }` |

---

#### B. Campaigns & AdCraft Studio (`/api/v1/campaigns`)

| Method | Endpoint | Description | Request Body / Params | Response |
|---|---|---|---|---|
| `GET` | `/campaigns` | List all campaigns for the active workspace | `?status=ACTIVE&limit=20` | `{ "campaigns": [...] }` |
| `POST` | `/campaigns/draft` | Create a new campaign draft from a natural language brief | `{ "brief": "Target developers in India for ₹5,000" }` | Full campaign document with extracted fields |
| `GET` | `/campaigns/{id}` | Get full campaign details, requirements, variants, and status | None | Campaign JSON document |
| `PUT` | `/campaigns/{id}` | In-place update of campaign fields (title, budget, variants, targeting) | `{ "budget_inr": 6000, "variants": [...] }` | Updated campaign document with incremented `rev` |
| `POST` | `/campaigns/{id}/chat` | Send conversational turn to provide missing info or feedback | `{ "message": "The landing page is https://mysaas.dev" }` | Updated campaign document + agent reply |
| `POST` | `/campaigns/{id}/revise` | Request AI to polish or rewrite ad copy based on instructions | `{ "variant_id": "v1", "instruction": "Make it punchier" }` | Updated variant with new copy diff |
| `POST` | `/campaigns/{id}/approve` | Record explicit cryptographic human approval | `{ "version_num": 2 }` | `{ "approval_id": "...", "content_hash": "..." }` |
| `POST` | `/campaigns/{id}/publish` | Publish approved campaign to Meta (creates objects in PAUSED) | None | `{ "status": "PUBLISHING", "step": 5, "meta_ids": {...} }` |
| `POST` | `/campaigns/{id}/resume-publish` | Resume publishing from last failed step without duplicating | None | Resumed publish status |
| `POST` | `/campaigns/{id}/discard-publish` | Discard failed publish attempt and return to IN_REVIEW | None | Campaign document reset to `IN_REVIEW` |
| `POST` | `/campaigns/{id}/activate` | Activate paused Meta campaign (subject to spend switch) | None | `{ "status": "ACTIVE" }` |
| `POST` | `/campaigns/{id}/pause` | Pause active Meta campaign | None | `{ "status": "PAUSED" }` |
| `DELETE`| `/campaigns/{id}` | Archive or delete a campaign | None | `{ "status": "ARCHIVED" }` |
| `GET` | `/campaigns/{id}/insights` | Retrieve campaign analytics, period comparisons & AI report | `?days=7` | Metrics summary, daily rows & AI report |

---

#### C. Meta Connections & Search (`/api/v1/meta`)

| Method | Endpoint | Description | Request Body / Params | Response |
|---|---|---|---|---|
| `GET` | `/meta/auth-url` | Generate Facebook Login for Business authorization URL | None | `{ "auth_url": "https://facebook.com/..." }` |
| `POST` | `/meta/callback` | Exchange OAuth code for 60-day long-lived access token | `{ "code": "..." }` | `{ "status": "CONNECTED", "expires_in_days": 60 }` |
| `GET` | `/meta/status` | Check if Meta account is connected and token is valid | None | `{ "connected": true, "token_expires_at": "..." }` |
| `POST` | `/meta/connect-direct` | Connect using a manual Meta access token (Developer mode) | `{ "access_token": "..." }` | Connection status and discovered assets |
| `GET` | `/meta/assets` | List available Ad Accounts, Facebook Pages & Instagram accounts | None | `{ "ad_accounts": [...], "pages": [...] }` |
| `POST` | `/meta/assets` | Select active Ad Account and Facebook Page for workspace | `{ "ad_account_id": "...", "page_id": "..." }` | Updated connection record |
| `GET` | `/meta/interests` | Search real Meta audience interest targeting categories | `?q=python&limit=10` | `[{ "id": "6003139266461", "name": "Python" }]` |
| `GET` | `/meta/locations` | Search real Meta geographical locations (cities, regions) | `?q=Bengaluru&country_code=IN` | `[{ "key": "12345", "name": "Bengaluru" }]` |

---

#### D. Organic Social Media Publishing (`/api/v1/organic`)

*Allows publishing organic feed posts and stories to Instagram and Facebook with zero ad spend.*

| Method | Endpoint | Description | Request Body / Params | Response |
|---|---|---|---|---|
| `POST` | `/organic/publish` | Publish organic post to Instagram Feed, Stories, or FB Page | `{ "caption": "...", "hashtags": [...], "image_id": "...", "destinations": ["ig_feed", "fb_feed"] }` | `{ "results": [{ "destination": "ig_feed", "post_id": "...", "status": "PUBLISHED" }] }` |
| `GET` | `/organic/posts` | List recent organic posts published through AdCraft | `?limit=10` | `[{ "id": "...", "caption": "...", "post_url": "..." }]` |
| `DELETE`| `/organic/posts/{id}` | Delete organic post from platform | None | `{ "status": "DELETED" }` |

---

#### E. Hashtag Recommendations (`/api/v1/hashtags`)

| Method | Endpoint | Description | Request Body / Params | Response |
|---|---|---|---|---|
| `POST` | `/hashtags/recommend` | Generate AI-driven hashtags tailored to ad copy | `{ "content": "Ad text...", "limit": 10 }` | `{ "recommended": ["#AITools", "#DevLife", ...] }` |
| `GET` | `/hashtags/explore` | Get curated hashtag categories (Trending, Marketing, etc.) | None | `{ "categories": { "Marketing": [...], ... } }` |

---

#### F. Media & GridFS Storage (`/api/v1/media`)

| Method | Endpoint | Description | Request Body / Params | Response |
|---|---|---|---|---|
| `POST` | `/media/generate` | Generate 1080x1080 JPEG image via AI (Gemini / OpenAI) | `{ "prompt": "Minimalist developer desk with glowing laptop" }` | `{ "image_id": "...", "url": "/api/v1/media/{id}" }` |
| `POST` | `/media/upload` | Upload custom image file (validated to 1080x1080 JPEG) | `multipart/form-data` | `{ "image_id": "...", "filename": "..." }` |
| `GET` | `/media` | List previously generated or uploaded media assets | None | `[{ "id": "...", "filename": "...", "url": "..." }]` |
| `GET` | `/media/{id}` | Download raw JPEG image (supports HMAC-signed public URL for Meta crawler) | `?sig=...&expires=...` | Binary `image/jpeg` stream |

---

#### G. Instagram DM Customer Support Agent (`/api/v1/dm`)

*Hybrid RAG agent that answers customer DMs about products and offers.*

| Method | Endpoint | Description | Request Body / Params | Response |
|---|---|---|---|---|
| `GET` | `/dm/config` | Get DM agent configuration, hours, pricing, and tone | None | DM settings document |
| `PUT` | `/dm/config` | Update business knowledge, auto-reply switch, and handoff msg | `{ "auto_reply_enabled": true, "tone": "friendly", ... }` | Updated DM settings |
| `GET` | `/dm/threads` | List active customer DM threads (NEEDS_HUMAN sorted top) | None | `[{ "thread_id": "...", "sender_id": "...", "status": "NEEDS_HUMAN", ... }]` |
| `GET` | `/dm/threads/{id}/messages` | Get message history for a specific conversation thread | None | `[{ "direction": "INBOUND", "text": "...", "timestamp": "..." }]` |
| `POST` | `/dm/threads/{id}/reply` | Human business owner sends a manual reply to customer | `{ "message": "Here is our direct support number..." }` | `{ "status": "SENT" }` |
| `POST` | `/dm/threads/{id}/handback` | Hand conversation back to AI agent after human intervention | None | `{ "status": "AI_ACTIVE" }` |
| `POST` | `/dm/preview` | Simulate a customer question in the UI without sending a real message | `{ "message": "Is the 20% discount still active on the watch?" }` | `{ "reply": "...", "retrieved_post_id": "...", "confidence": 1.0 }` |

---

#### H. Webhooks (`/api/v1/webhooks`)

| Method | Endpoint | Description | Security |
|---|---|---|---|
| `GET` | `/webhooks/meta` | Meta webhook setup verification challenge handshake | Validates `hub.verify_token` against `META_WEBHOOK_VERIFY_TOKEN`. Returns `hub.challenge`. |
| `POST` | `/webhooks/meta` | Receives real-time Instagram and Facebook messaging events | Validates `X-Hub-Signature-256` HMAC-SHA256 signature against `META_APP_SECRET`. |

---

### 3. Meta Marketing API v26.0 Internal Calls

When AdCraft publishes a campaign, the `MetaSdkGateway` executes the following sequential Graph API requests:

```
1. Image Upload:
   POST https://graph.facebook.com/v26.0/act_{ad_account_id}/adimages
   Body: multipart/form-data with raw JPEG bytes
   Response: { "images": { "filename.jpg": { "hash": "abc12345..." } } }

2. Campaign Object:
   POST https://graph.facebook.com/v26.0/act_{ad_account_id}/campaigns
   Body: { "name": "AdCraft - AI Code Review", "objective": "OUTCOME_TRAFFIC", "status": "PAUSED", "special_ad_categories": [] }
   Response: { "id": "1202100000001" }

3. Ad Set Object:
   POST https://graph.facebook.com/v26.0/act_{ad_account_id}/adsets
   Body: {
     "campaign_id": "1202100000001",
     "name": "AdSet - Developers India",
     "daily_budget": "50000",
     "start_time": "2026-11-05T00:00:00Z",
     "end_time": "2026-11-12T00:00:00Z",
     "billing_event": "IMPRESSIONS",
     "optimization_goal": "LINK_CLICKS",
     "targeting": {
       "geo_locations": { "countries": ["IN"] },
       "age_min": 21,
       "age_max": 45,
       "flexible_spec": [{ "interests": [{ "id": "6003139266461", "name": "Python" }] }]
     },
     "status": "PAUSED"
   }
   Response: { "id": "1202100000002" }

4. Ad Creative Object:
   POST https://graph.facebook.com/v26.0/act_{ad_account_id}/adcreatives
   Body: {
     "name": "Creative - AI Code Review v1",
     "object_story_spec": {
       "page_id": "100200300",
       "instagram_actor_id": "900800700",
       "link_data": {
         "image_hash": "abc12345...",
         "message": "Supercharge your team's pull request workflow with instant AI reviews.",
         "link": "https://mysaas.dev",
         "name": "Cut Code Review Time by 50%",
         "description": "Start your free 14-day trial.",
         "call_to_action": { "type": "LEARN_MORE" }
       }
     }
   }
   Response: { "id": "1202100000003" }

5. Ad Object:
   POST https://graph.facebook.com/v26.0/act_{ad_account_id}/ads
   Body: { "adset_id": "1202100000002", "creative": { "creative_id": "1202100000003" }, "name": "Ad - AI Code Review", "status": "PAUSED" }
   Response: { "id": "1202100000004" }
```
