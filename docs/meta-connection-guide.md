# Meta Marketing API Connection Guide (Graph API v26.0)

This guide documents how to configure, authenticate, and troubleshoot the Meta Marketing API integration within the AI-Powered Ad Campaign Manager.

---

## 1. Operating Modes: Fake Sandbox vs. Real Meta

The system supports two execution modes controlled by the `META_MODE` environment variable in `.env`:

### `META_MODE=fake` (Default / Development & Testing)
- Operates entirely offline using `FakeAdsGateway`.
- Generates deterministic IDs (`act_fake_1`, `page_fake_1`, `ig_fake_1`).
- Requires zero Meta app credentials or tokens.
- Supports fault injection via `FAKE_META_FAIL_AT` (e.g. `CAMPAIGN:190,ADSET:timeout`).
- Ideal for local integration tests, frontend UI development, and CI/CD pipelines.

### `META_MODE=real` (Live Sandbox / Production)
- Uses `MetaSdkGateway` powered by the official `facebook-business` Python SDK and direct Graph API v26.0 requests.
- All requests are automatically signed with `appsecret_proof = HMAC-SHA256(app_secret, access_token)`.
- Tokens are encrypted at rest using AES-256-GCM.
- Reads are automatically retried with exponential backoff on transient errors (rate limit #17, temporary network blips); writes are strict single-shot (fail-fast) to eliminate duplicate campaign creation.

---

## 2. Switching Between Modes

In your project `.env` file:

```env
# Switch mode
META_MODE=fake   # or META_MODE=real

# Required for META_MODE=real:
META_APP_ID=123456789012345
META_APP_SECRET=your_app_secret_here
META_REDIRECT_URI=http://localhost:3000/api/meta/callback
META_LOGIN_CONFIG_ID=
TOKEN_ENCRYPTION_KEY=your_32_byte_base64_encoded_key
```

---

## 3. Obtaining Meta Credentials & Development Tokens

### Step 1: Create a Meta App
1. Go to [Meta for Developers](https://developers.facebook.com/).
2. Click **Create App** and select **Business** or **Other** app type.
3. Under **Add Products**, add **Marketing API**.
4. Retrieve your **App ID** and **App Secret** from **App settings > Basic**.

### Step 2: System User Token (Recommended for Backend Bots)
1. Go to **Meta Business Suite > Business Settings**.
2. Under **Users > System Users**, create a System User (Admin role).
3. Click **Add Assets** and assign your Ad Account, Facebook Page, and Instagram account with full management access.
4. Click **Generate New Token**, select the app, and choose `Never expire`.
5. Select the required permissions (listed below) and copy the token.

### Step 3: User Token via OAuth (Standard Multi-Tenant Flow)
1. In your app settings, add `http://localhost:3000/api/meta/callback` to the **Valid OAuth Redirect URIs**.
2. Log into the web application at `/login`.
3. Open **Settings > Meta Connection** and click **Connect with Facebook**.
4. Authorize the requested permissions in the Meta dialog.
5. The backend will automatically exchange the authorization code for a long-lived 60-day access token and store it securely encrypted in MongoDB.

---

## 4. Required Permissions Checklist

The Meta access token must have the following permissions granted:

| Permission | Purpose |
|---|---|
| `ads_management` | Create, update, and manage campaigns, ad sets, creatives, and ads |
| `ads_read` | Read ad accounts, campaigns, ad sets, ads, and delivery status |
| `business_management` | Read and discover business assets across the portfolio |
| `pages_show_list` | Discover accessible Facebook Pages |
| `pages_read_engagement` | Verify page health and associated engagement |
| `instagram_basic` | Discover linked professional Instagram accounts |
| `instagram_content_publish` | Publish creative media directly to Instagram |
| `instagram_manage_insights` | Read organic and paid Instagram performance metrics |

---

## 5. Verification Smoke Checks

You can run offline or online smoke checks using the provided CLI tool:

```bash
# Offline check (META_MODE=fake or missing credentials prints safe guidance):
cd backend
uv run python scripts/meta_smoke.py

# Full automated payload check:
uv run python scripts/meta_smoke_test.py
```

---

## 6. Troubleshooting Common Meta API Errors

| Error Code | Meaning | Root Cause & Resolution |
|---|---|---|
| **#17 / #4 / #613** | Rate Limit Exceeded | API call limit reached. The system automatically backs off with exponential jitter up to 3 retries. Wait or reduce concurrent requests. |
| **#190** | Invalid / Expired Token | Access token expired, user changed password, or permissions were revoked. The system classifies this as `MetaAuthExpired`, marks the connection `EXPIRED`, and prompts the user on the frontend to Reconnect. |
| **#100 (Subcode 33)** | Missing Permissions | Access token is missing one or more required scopes. Re-generate token with full `ads_management` and Instagram permissions. |
| **#100 (Param error)** | Deprecated Field / Invalid Payload | In Graph API v26.0: <br>• Campaign requires `is_adset_budget_sharing_enabled: false`.<br>• Ad Set requires `targeting_automation: {advantage_audience: 0}` and strict `"stream"` publisher platform (do not use `"explore"`).<br>• Start time must be at least 15 minutes into the future. |
| **No Instagram Account** | Page has no linked Instagram professional account | Ensure the Facebook Page is linked to an Instagram Business/Creator account in Meta Business Suite before selecting it. |
