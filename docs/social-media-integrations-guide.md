# AdCraft – Multi-Platform Social Media Integrations Configuration Guide

This guide covers environment configuration, OAuth app setup, required permissions, multi-tenant isolation, and current implementation status across all six platforms in AdCraft's **Social Media Connections** center.

---

## 1. Environment Variables

Configure these in `.env` (never commit secrets or expose them in `NEXT_PUBLIC_*` frontend variables):

```env
# Token encryption at rest (32-byte base64 AES-256-GCM key)
TOKEN_ENCRYPTION_KEY=<base64-32-byte-key>

# Optional sandbox mode for offline UI & integration testing
META_MODE=real          # real | fake
SOCIAL_OAUTH_MODE=real  # real | fake

# Meta (Instagram + Facebook)
META_APP_ID=...
META_APP_SECRET=...
META_REDIRECT_URI=http://localhost:3000/api/meta/callback
META_LOGIN_CONFIG_ID=   # optional Facebook Login for Business config ID
ALLOW_ORGANIC_PUBLISH=true
PUBLIC_BASE_URL=https://your-public-origin

# LinkedIn (Community Management API / Share on LinkedIn)
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_REDIRECT_URI=http://localhost:3000/api/integrations/linkedin/callback

# X (Twitter OAuth 2.0 PKCE)
X_CLIENT_ID=...
X_CLIENT_SECRET=...
X_REDIRECT_URI=http://localhost:3000/api/integrations/x/callback

# Pinterest (API v5)
PINTEREST_CLIENT_ID=...
PINTEREST_CLIENT_SECRET=...
PINTEREST_REDIRECT_URI=http://localhost:3000/api/integrations/pinterest/callback

# Reddit (OAuth 2.0)
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_REDIRECT_URI=http://localhost:3000/api/integrations/reddit/callback
REDDIT_USER_AGENT=AdCraft/1.0 (by /u/your_reddit_username)
```

---

## 2. Platform Developer App & Permission Requirements

### Instagram & Facebook (Meta Graph API)
- **Developer Portal:** Meta for Developers (`https://developers.facebook.com/`)
- **Redirect URI:** `http://localhost:3000/api/meta/callback` (and your production HTTPS domain callback)
- **Required Scopes:** `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`, `instagram_manage_messages`, `pages_messaging`, `pages_manage_metadata`, `business_management`, `ads_management`, `ads_read`
- **Notes:** Instagram accounts must be Professional (Business or Creator) accounts linked to a Facebook Page the user manages.

### LinkedIn
- **Developer Portal:** LinkedIn Developer Portal (`https://www.linkedin.com/developers/`)
- **Redirect URI:** `http://localhost:3000/api/integrations/linkedin/callback`
- **Products Required:**
  - **Sign In with LinkedIn using OpenID Connect** (`openid`, `profile`, `email`)
  - **Share on LinkedIn** (`w_member_social`) for personal profile posting
  - **Community Management API** (`r_organization_social`, `w_organization_social`, `rw_organization_admin`) for Organization/Company Page discovery & publishing
- **Important:** Personal profile identity (`urn:li:person:...`) and Organization Page identity (`urn:li:organization:...`) are handled separately. Users must hold an approved `ADMINISTRATOR` role on the Company Page. LinkedIn Ads requires separate Advertising API approval.

### X (Twitter)
- **Developer Portal:** X Developer Portal (`https://developer.x.com/`)
- **App Type:** OAuth 2.0 with PKCE (`S256`), Confidential or Public client
- **Redirect URI:** `http://localhost:3000/api/integrations/x/callback`
- **Scopes:** `tweet.read`, `tweet.write`, `users.read`, `offline.access`
- **Notes:** Text/link publishing uses `POST https://api.x.com/2/tweets` (280-character limit). Media upload and X Ads require appropriate X API access tiers / separate X Ads API v12 approval.

### Pinterest
- **Developer Portal:** Pinterest Developers (`https://developers.pinterest.com/`)
- **Redirect URI:** `http://localhost:3000/api/integrations/pinterest/callback`
- **Scopes:** `user_accounts:read`, `boards:read`, `boards:write`, `pins:read`, `pins:write`
- **Notes:** Pinterest Pins require an image and a target Board. Production multi-tenant access requires Pinterest API v5 Standard Access review.

### Reddit
- **Developer Portal:** Reddit App Preferences (`https://www.reddit.com/prefs/apps`) — **web app** type
- **Redirect URI:** `http://localhost:3000/api/integrations/reddit/callback`
- **Scopes:** `identity`, `mysubreddits`, `submit`, `read`
- **Notes:** Requests must include a descriptive `REDDIT_USER_AGENT` header. Subreddit posting respects each subreddit's `submission_type` (`self`, `link`, `any`) and contributor/moderator restrictions.

---

## 3. Architecture & Multi-Tenant Isolation

- **Backend Modular Package:** `backend/app/integrations/`
  - `base/`: common `SocialPlatformAdapter` interface, normalized models, error taxonomy, and retry policy
  - `oauth/`: signed JWT state + PKCE (`state.py`) and AES-256-GCM encrypted MongoDB storage (`token_store.py`)
  - `instagram/`, `facebook/`, `linkedin/`, `x/`, `pinterest/`, `reddit/`: platform-specific OAuth, discovery, validation, and publishing adapters
  - `publishing.py`: multi-platform validation, preview, independent publishing, and history
  - `advertising/`: separate future-phase paid advertising readiness registry
- **Database Collection:** `social_connections` keyed uniquely by `(user_id, organization_id, platform)` so each user and workspace (`synxait` vs `personal`) has isolated encrypted credentials.
- **Security:** Tokens are encrypted at rest with `TOKEN_ENCRYPTION_KEY`, never returned to the frontend, and never stored in `localStorage`.

---

## 4. Implementation Status Matrix

| Platform | Organic OAuth & Token Encryption | Account / Target Discovery & Selection | Organic Publishing | Paid Advertising Module |
|---|---|---|---|---|
| **Instagram** | Fully implemented (live + sandbox) | Fully implemented | Fully implemented (image + caption + hashtags) | Active via Meta Ads (`MetaConnectCard`) |
| **Facebook** | Fully implemented (live + sandbox) | Fully implemented (Pages) | Fully implemented (text, link, photo, story) | Active via Meta Ads (`MetaConnectCard`) |
| **LinkedIn** | Fully implemented (awaiting app credentials in `.env`) | Fully implemented (Personal + Organization Pages separated) | Implemented (text, link, image; org posting awaits Community Management API approval) | Gated in `advertising/` (awaiting LinkedIn Ads API approval & billing) |
| **X (Twitter)** | Fully implemented (OAuth 2.0 PKCE; awaiting app credentials in `.env`) | Fully implemented (Profile) | Text & link posts implemented; media upload depends on X API tier | Gated in `advertising/` (awaiting X Ads API v12 approval) |
| **Pinterest** | Fully implemented (API v5; awaiting app credentials in `.env`) | Fully implemented (Boards) | Pin creation (image + Board + title/link) implemented; production awaits Standard Access | Gated in `advertising/` (awaiting Standard Access & partner/eligible billing) |
| **Reddit** | Fully implemented (awaiting app credentials in `.env`) | Fully implemented (Subreddits + Profile) | Text (`self`) & link posts implemented | Gated in `advertising/` (awaiting Reddit Business Ad Account billing) |

