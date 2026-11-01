# AdCraft: Meta Account Details, Permissions & Setup Guide
## Developer Portal, Permissions, Tokens & Webhook Configuration

---

### 1. Overview of Required Meta Assets

To connect AdCraft to Meta's live or sandbox ecosystem, you need five assets in your Meta account:

```
+-------------------------------------------------------------------+
|                        REQUIRED META ASSETS                       |
+-------------------------------------------------------------------+
| 1. Meta Developer Account  | developers.facebook.com access       |
| 2. Meta Business App       | App created under App Type: Business |
| 3. Facebook Business Page  | The public brand identity            |
| 4. Instagram Pro Account   | Linked to your Facebook Page         |
| 5. Meta Ad Account         | Sandbox or Live Ad Account           |
+-------------------------------------------------------------------+
```

---

### 2. Step-by-Step Meta Developer Setup

#### Step 1: Create a Meta Developer Account
1. Visit [Meta for Developers](https://developers.facebook.com/).
2. Log in with your Facebook credentials and complete developer registration.

#### Step 2: Create a Meta Business App
1. Go to **My Apps** -> Click **Create App**.
2. Select **Other** as the use case -> Click **Next**.
3. Select **Business** as the App Type -> Click **Next**.
4. Enter an App Name (e.g., `AdCraft-Manager`), enter your email, and select your Business Portfolio (if available).
5. Click **Create App**.

#### Step 3: Add Required Products to Your App
In the App Dashboard, add the following three products from the Product Catalog:
1. **Marketing API:** Enables creating campaigns, ad sets, creatives, ads, and retrieving insights.
2. **Facebook Login for Business:** Enables OAuth 2.0 user login and authorization.
3. **Webhooks:** Enables real-time delivery of Instagram customer DMs to AdCraft.

---

### 3. Required API Scopes & Permissions

When authorizing via Facebook Login for Business or generating a token via the Graph API Explorer, the following scopes must be selected:

| Scope | Category | Why AdCraft Requires It |
|---|---|---|
| `ads_management` | Paid Ads | Create, edit, and publish campaigns, ad sets, and ads. |
| `ads_read` | Paid Ads | Read ad account status and retrieve performance insights. |
| `pages_show_list` | Organic & Ads | Discover Facebook Pages owned by the user. |
| `pages_read_engagement` | Organic & Ads | Read posts, comments, and engagement on the Page. |
| `pages_manage_posts` | Organic | Publish organic posts directly to the Facebook Page feed. |
| `instagram_basic` | Instagram | Read Instagram Business Account handle, profile, and media. |
| `instagram_content_publish` | Instagram | Publish organic feed photos and stories to Instagram. |
| `instagram_manage_messages` | Instagram DMs | Receive customer DMs via webhooks and send AI replies. |
| `business_management` | Account Setup | Read linked ad accounts and business assets. |

---

### 4. Generating Access Tokens

AdCraft supports two methods for connecting your Meta account:

#### Option A: In-App Facebook Login (Recommended for End Users)
1. Open AdCraft in your browser (`http://localhost:3000`).
2. Go to **Settings** -> **Meta Connection**.
3. Click **Connect with Meta**.
4. Log in, select your Facebook Page and Instagram Account, and grant permissions.
5. AdCraft automatically exchanges the short-lived token for a **60-day long-lived access token** and encrypts it using AES-256-GCM.

#### Option B: Direct Token via Graph API Explorer (Fastest for Developers/Evaluators)
1. Open the [Meta Graph API Explorer](https://developers.facebook.com/tools/explorer/).
2. In the **Meta App** dropdown, select your AdCraft app.
3. In **User or Page**, select **User Token**.
4. In **Permissions**, add the 9 scopes listed in Section 3 above.
5. Click **Generate Access Token** and approve the popup.
6. Copy the generated token string.
7. In AdCraft, go to **Settings** -> **Direct Token Connection**, paste the token, and click **Connect**.

---

### 5. Finding Your Meta Identifiers

You will need the following IDs to verify your connection in AdCraft:

1. **Ad Account ID (`act_...`):**
   - Go to [Meta Ads Manager](https://adsmanager.facebook.com/).
   - Look at the URL or top-left account selector: `act_123456789012345`.
2. **Facebook Page ID:**
   - Open your Facebook Page -> Click **About** -> **Page Transparency**.
   - Your numeric Page ID is shown (e.g., `100200300400500`).
3. **Instagram Business Account ID:**
   - In Graph API Explorer, execute: `GET me/accounts?fields=instagram_business_account{id,username}`
   - The returned `id` is your Instagram Business Account ID.

---

### 6. Configuring Webhooks for the Instagram DM Agent

To receive incoming Instagram customer messages in real time:

1. **Expose Localhost to the Internet via HTTPS:**
   - Meta requires an HTTPS callback URL. Run a Cloudflare Tunnel or VS Code Dev Tunnel:
     ```bash
     cloudflared tunnel --url http://localhost:8000
     ```
   - Copy the public HTTPS URL (e.g., `https://adcraft-tunnel.trycloudflare.com`).
2. **Configure Webhook in Meta Developer Portal:**
   - In your Meta App Dashboard, navigate to **Webhooks** -> Select **Instagram** from the dropdown.
   - Click **Subscribe to this object**.
   - **Callback URL:** `https://adcraft-tunnel.trycloudflare.com/api/v1/webhooks/meta`
   - **Verify Token:** Enter the value matching `META_WEBHOOK_VERIFY_TOKEN` in your `.env` (e.g., `my_secret_verify_token_123`).
   - Click **Verify and Save**.
3. **Subscribe to Fields:**
   - Under Instagram Webhook fields, click **Subscribe** on:
     - `messages` (Receives customer text and shared post links)
     - `messaging_postbacks` (Receives button clicks)

---

### 7. Spend Safety Configuration & Switches

To ensure that live tests **never** incur accidental financial charges on your credit card:

1. **Safety Switch 1: Ads Published as `PAUSED`**
   - When a campaign is published through AdCraft, the Meta Campaign, Ad Set, and Ad objects are created with `status="PAUSED"`. Meta will never deliver impressions or charge money for paused ads.
2. **Safety Switch 2: Activation Spend Lock**
   - Activating an ad requires clicking **Activate** in AdCraft. The backend checks:
     ```python
     if not settings.spend_allowed:
         raise SpendSafetyBlocked("Live spend is disabled in configuration.")
     ```
   - Real spend requires **both** settings in `.env`:
     ```env
     ALLOW_REAL_AD_SPEND=true
     SAFE_MODE_NO_SPEND=false
     ```
   - As long as `ALLOW_REAL_AD_SPEND=false` (the default), you are 100% mathematically safe from credit card charges.
3. **Safety Switch 3: Daily Spend Cap**
   - Even if real spend is enabled, the backend hard-caps daily budgets at ₹1,000 INR (`MAX_DAILY_BUDGET_INR=1000`). Any higher value is rejected by deterministic code.
