# AdCraft: ad_campaign_manager

An AI-assisted Instagram ad manager. You describe what you want to promote; the AI drafts the ad, audience and
picture; you review and publish it to Instagram through the Meta Marketing API. It also answers Instagram DMs from a
knowledge block you write, and posts ordinary (organic) feed posts.

| Part | Tech |
|---|---|
| Backend | FastAPI, Google ADK agents (LiteLLM: Gemini or OpenAI), Meta Marketing API via `facebook-business` |
| Frontend | Next.js (port 3000, proxies `/api/*` to the backend) |
| Database | MongoDB **as a replica set** (the app uses transactions) |

Two ways to run it:

| | Fake execution | Real execution |
|---|---|---|
| Meta | simulated in memory, nothing leaves your machine | your real ad account, Page and Instagram account |
| Money | none | **real ad spend** on your ad account |
| Needs | MongoDB (+ a Gemini key if you want real AI text) | Meta developer app, ad account with a payment method, Page + Instagram professional account |
| Use it for | development, demos, tests | publishing real ads |

Contents: [Setup](#1-setup-once) | [Fake execution](#2-fake-execution-no-meta-no-spend) |
[Real execution](#3-real-execution-publish-real-ads) | [AI provider and cost](#4-ai-provider-and-token-cost) |
[Tests](#5-tests) | [Troubleshooting](#6-troubleshooting) | [Security](#7-security) | [Layout](#8-project-layout)

---

## 1. Setup (once)

**Requirements:** Windows, macOS or Linux; Python 3.12+ with [uv](https://docs.astral.sh/uv/); Node 24 (`frontend/.nvmrc`);
Docker Desktop (for MongoDB).

```powershell
cd ad_campaign_manager
cd backend;  uv sync;  cd ..          # backend dependencies
cd frontend; npm ci;   cd ..          # frontend dependencies
```

### MongoDB (replica set required)

Always reuse the named `acm-dev-mongo-data` Docker volume. Images live in MongoDB GridFS and disappear if the container is recreated without that volume. Run `scripts/backup-db.ps1` before risky database maintenance.

```powershell
docker compose up -d --wait mongo     # waits until the replica set is initialised (about 10 s)
```

The backend refuses writes until the replica set `rs0` is initialised; `--wait` makes sure it is.

> **Port 27017 already in use by a local `mongod`?** A MongoDB installed on the machine hides the Docker one (the app then
> fails with `RSGhost` / "No servers available for writes"). Give the project its own database on another port:
> ```powershell
> docker run -d --name acm-dev-mongo -p 27117:27017 -v acm-dev-mongo-data:/data/db mongo:8 --replSet rs0 --bind_ip_all
> docker exec acm-dev-mongo mongosh --quiet --eval "rs.initiate({_id:'rs0',members:[{_id:0,host:'localhost:27017'}]})"
> $env:MONGODB_URI = "mongodb://localhost:27117/?directConnection=true"   # set this in every backend terminal
> ```

### Configuration

Settings come from environment variables first, then `../.env` (repo root), then `backend/.env`. **Setting a variable in
the terminal overrides the file**, which is how the steps below switch modes without editing anything.

| Variable | Meaning |
|---|---|
| `MONGODB_URI`, `MONGODB_DB` | Database (default `mongodb://localhost:27017`, db `acm`) |
| `JWT_SECRET` | Session signing key, **at least 32 characters** |
| `TOKEN_ENCRYPTION_KEY` | Encrypts stored Meta tokens: base64 of exactly 32 random bytes |
| `META_MODE` | `fake` (simulated Meta) or `real` |
| `LLM_PROVIDER` | `openrouter`, `gemini`, `litellm` (direct OpenAI) or `scripted` (canned answers, no key, never in production) |
| `GEMINI_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY` | Keep any or all; only the key matching `LLM_PROVIDER` is used (users can also set their own under Settings > API Keys and AI) |
| `OPENROUTER_MODEL_FAMILY` | `gemini` or `openai`: which models OpenRouter serves (see [section 4](#4-ai-provider-and-token-cost)) |
| `OPENROUTER_GEMINI_PRIMARY_MODEL`, `OPENROUTER_GEMINI_UTILITY_MODEL`, `OPENROUTER_OPENAI_PRIMARY_MODEL`, `OPENROUTER_OPENAI_UTILITY_MODEL` | The exact OpenRouter model ids per family (defaults: `google/gemini-3.5-flash-lite` for the `gemini` family and `openai/gpt-5` for the `openai` family, for both roles) |
| `LLM_PRIMARY_MODEL`, `LLM_UTILITY_MODEL` | OpenAI/LiteLLM model names. With Gemini, `GEMINI_PRIMARY_MODEL` / `GEMINI_UTILITY_MODEL` (both default to `gemini-3.5-flash-lite`) are used. With direct OpenAI the default is `gpt-5` for both roles |
| `IMAGE_PROVIDER` | `fake` (coloured placeholder), `gemini`, `openai`, `ai` (free third-party service) |
| `ALLOW_REAL_AD_SPEND`, `SAFE_MODE_NO_SPEND` | The two **live-delivery switches** (see [section 3.4](#34-the-two-safety-switches)) |
| `MAX_DAILY_BUDGET_INR`, `MAX_CAMPAIGN_DAYS` | Server caps on one campaign (defaults 1000 per day, 30 days) |
| `META_APP_ID`, `META_APP_SECRET`, `META_REDIRECT_URI`, `META_LOGIN_CONFIG_ID` | Meta app, real mode only |
| `META_WEBHOOK_VERIFY_TOKEN`, `PUBLIC_BASE_URL`, `ALLOW_ORGANIC_PUBLISH` | DM agent and organic posts, see [docs/dm-agent-and-organic-posts.md](docs/dm-agent-and-organic-posts.md) |
| `OPENAI_IMAGE_MODEL`, `OPENAI_IMAGE_QUALITY` | Image model and quality (`low`, `medium` default, `high`; high costs about 4x the image tokens) |

Generate the two secrets:
```powershell
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"   # TOKEN_ENCRYPTION_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"                       # JWT_SECRET
```

---

## 2. Fake execution (no Meta, no spend)

`META_MODE=fake` replaces Meta with an in-memory simulator that passes the same contract tests as the real gateway. You
get one fake ad account (`act_fake_1`), a Page with Instagram `@fake_brand`, and a second Page with no Instagram (to see
how unusable Pages are explained). Campaigns, drafts, images, DM threads and post records are stored in MongoDB as usual;
only the Meta objects live in memory and disappear when the backend restarts.

### 2.1 Start it

Pick **A** (no keys at all) or **B** (real AI text from Gemini). Open two terminals.

**Terminal 1, backend**
```powershell
cd ad_campaign_manager\backend

# --- common to A and B ---
$env:META_MODE = "fake"
$env:IMAGE_PROVIDER = "fake"
$env:ALLOW_REAL_AD_SPEND = "true"        # harmless here: nothing leaves your machine. Without these two,
$env:SAFE_MODE_NO_SPEND = "false"        # Publish answers 409 SPEND_BLOCKED, even in fake mode.
$env:META_APP_SECRET = "test-secret"     # only needed to try the DM webhook
$env:META_WEBHOOK_VERIFY_TOKEN = "verify-me"
$env:PUBLIC_BASE_URL = "http://127.0.0.1:8000"

# --- A: canned AI, no keys ---
$env:LLM_PROVIDER = "scripted"
# --- B: real Gemini text (needs GEMINI_API_KEY in .env or the environment) ---
# $env:LLM_PROVIDER = "gemini"

uv run uvicorn app.main:app --reload --reload-dir app --port 8000
```
You should see `Application startup complete.` Check http://127.0.0.1:8000/health returns `{"status":"ok"}` (API docs at `/docs`).

**Terminal 2, frontend**
```powershell
cd ad_campaign_manager\frontend
npm run dev                               # http://localhost:3000
```

### 2.2 Walkthrough

1. **Register** at http://localhost:3000 and log in.
2. **Settings > Meta Connection > Connect**: in fake mode it connects instantly. Choose the fake ad account and the Page `Fake Brand Page`.
3. **Create an ad**: on the dashboard type an idea (for example *"Promote my Python course for students in Bangalore, https://example.com"*) and press *Generate ad*. With **A** you always get the same sample draft; with **B** Gemini writes it. Edit the text, audience, budget and dates in the chat or the studio. A placeholder picture is generated (`IMAGE_PROVIDER=fake`).
4. **Publish**: *Publish and start Instagram ad* > confirm. The backend runs the same steps as real mode (campaign, ad set, creative, ad) against the simulator and the campaign becomes **ACTIVE**.
5. **Manage**: *Pause*, *Resume*, *Refresh insights* (simulated numbers) and *Delete*.
6. **DM Agent**: write a knowledge block, tick auto-reply, save, use *Try it*. To simulate a customer message, send a signed webhook:
   ```powershell
   $secret = "test-secret"
   $body = '{"object":"instagram","entry":[{"id":"ig_fake_1","messaging":[{"sender":{"id":"cust_1"},"recipient":{"id":"ig_fake_1"},"timestamp":' + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() + ',"message":{"mid":"m' + (Get-Random) + '","text":"What time do you open?"}}]}]}'
   $h = [System.Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($secret))
   $sig = "sha256=" + ([BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($body))).Replace("-","").ToLower())
   Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/webhooks/instagram -Body $body -ContentType "application/json" -Headers @{ "X-Hub-Signature-256" = $sig }
   ```
7. **Post to Instagram**: pick the account, generate or upload a picture, write a caption and post. It is recorded, not sent.

### 2.3 Inject failures (optional)

`FAKE_META_FAIL_AT` makes a Meta step fail once, to exercise retry, resume and discard:
```powershell
$env:FAKE_META_FAIL_AT = "ADSET:timeout_after_create,CAMPAIGN:190"   # STEP[:code|timeout|timeout_after_create]
```
Steps: `CAMPAIGN`, `ADSET`, `CREATIVE`, `AD`, `IMAGE`, `UPDATE`, `DELETE`, `INSIGHTS`, `DM`, `POST`. A bare step injects error code 100.

### 2.4 What fake mode does not prove

Meta's real validation (ad review, budget minimums, interests, payment, permissions), real delivery and real
insights. Use real execution for that. `META_MODE=fake` is refused when `APP_ENV=production`.

---

## 3. Real execution (publish real ads)

When `-PublicUrl` is supplied, `scripts/start-real.ps1` builds the frontend and serves the production build. Next.js development mode sends many small JavaScript chunks through a tunnel and can fail with `ChunkLoadError`, leaving the page and images blank. Use production mode for tunnel sessions; pass `-Prod` to opt in when running without `-PublicUrl`.

> **This spends real money.** Published ads start delivering after Meta's review and are charged to the connected ad
> account up to the daily budget. Start with the smallest budget Meta allows and watch Ads Manager.

### 3.1 What you need on the Meta side

- A **Meta developer app** ([developers.facebook.com](https://developers.facebook.com/)).
- A **Facebook Page** and an **Instagram Business or Creator account linked to that Page**.
- An **ad account** with a **payment method**, and your Facebook user as an admin of the Page and the ad account.

### 3.2 Create and configure the Meta app

1. **Create the app**: *Create App* > type **Business** (or *Other*). Add the products **Marketing API** and **Facebook Login** (or **Facebook Login for Business**).
2. **App ID and secret**: *App settings > Basic*. Copy `App ID` and `App Secret`.
3. **Redirect URI**: *Facebook Login > Settings > Valid OAuth Redirect URIs*, add exactly `http://localhost:3000/api/meta/callback` (the frontend proxies it to the backend). For a deployed site use `https://<your-domain>/api/meta/callback`.
4. **Permissions** the app requests (they are listed in `backend/app/meta/oauth.py`; with Facebook Login for Business put them in the login *configuration* and copy its id into `META_LOGIN_CONFIG_ID`):

   | Permission | Used for |
   |---|---|
   | `ads_management`, `ads_read` | create, change and read campaigns, ad sets, creatives, ads and insights |
   | `business_management` | discover ad accounts and Pages |
   | `pages_show_list`, `instagram_basic` | list Pages and their linked Instagram accounts |
   | `instagram_content_publish` | organic posts |
   | `instagram_manage_messages`, `pages_messaging`, `pages_manage_metadata` | DM agent (subscribes the Page to webhooks) |

5. **Who can use it**: while the app is in **Development mode**, only people with a role on the app (admin, developer, tester) can connect, which is enough to publish on your own accounts. For other people's accounts switch the app to **Live** and complete **App Review** (Advanced Access) and **Business Verification**. Meta's requirements change, so check their current documentation.

### 3.3 Configure the backend

Set these in the backend terminal (or in `.env`, but **never commit real secrets**):

```powershell
cd ad_campaign_manager\backend
$env:META_MODE = "real"
$env:META_APP_ID = "<app id>"
$env:META_APP_SECRET = "<app secret>"
$env:META_REDIRECT_URI = "http://localhost:3000/api/meta/callback"   # must match the Meta app exactly
$env:META_API_VERSION = "v26.0"
$env:JWT_SECRET = "<32+ characters>"
$env:TOKEN_ENCRYPTION_KEY = "<base64 of 32 bytes>"
$env:LLM_PROVIDER = "gemini"            # or litellm with OPENAI_API_KEY
$env:IMAGE_PROVIDER = "gemini"          # real pictures need image quota (Gemini images or OpenAI need billing)
# the two live-delivery switches: see 3.4
```
Remove `FAKE_META_FAIL_AT` and any other fake-mode leftovers from the environment.

### 3.4 The two safety switches

Live delivery needs **both** `ALLOW_REAL_AD_SPEND=true` **and** `SAFE_MODE_NO_SPEND=false`. If either is off:

- *Publish* answers `409 SPEND_BLOCKED` and nothing is written to Meta.
- Resume of a paused campaign is blocked the same way. *Pause* always works, because pausing stops spend.
- The Meta gateway itself also forces any create or update to `PAUSED`, as a second guard.

Turn them on only in the terminal where you intend to publish for real:
```powershell
$env:ALLOW_REAL_AD_SPEND = "true"
$env:SAFE_MODE_NO_SPEND = "false"
```
Other limits always apply: `MAX_DAILY_BUDGET_INR` and `MAX_CAMPAIGN_DAYS`.

### 3.4b Two-command start (Windows PowerShell)

Once the Meta app is configured (steps 3.2 and the app domain `localhost`), these two commands run the whole real stack and stop it again:

```powershell
.\scripts\start-real.ps1      # MongoDB, public tunnel, backend (real Meta, real AI, real images), frontend; opens the app
.\scripts\stop-real.ps1       # stops all of it; the spend and posting switches end with the backend
```

Options: `-Llm gemini|openrouter|litellm` (default `gemini`), `-Family gemini|openai` (with `openrouter`), `-Images gemini|openai|ai|fake` (default `gemini`), `-MaxDailyBudgetInr 150`, `-DryRun` (print the plan only). The script prints the tunnel address and the DM webhook URL; the free tunnel address changes on every start, so update the webhook in the Meta app when you use DMs. The steps below do the same by hand.

### 3.4c One fixed HTTPS address (needed when the Meta app is Live, or when other people connect)

Meta only accepts a plain `http://localhost` login address while the app is in **Development** mode, and `localhost` only exists on your own computer. When the app is **Live**, or when other people (testers, clients) should connect, give the app one fixed **HTTPS** address through a tunnel. Facebook login, post images and the DM webhook then all use that single address.

1. **Create the tunnel** (Dev Tunnels shown; ngrok with a free fixed domain works the same). It must forward to port **3000** (the frontend, which passes `/api/*` on to the backend) and be reachable without a login:
   ```powershell
   winget install Microsoft.devtunnel
   devtunnel user login
   devtunnel create adcraft --allow-anonymous
   devtunnel port create adcraft -p 3000
   devtunnel host adcraft            # prints https://<id>-3000.<region>.devtunnels.ms
   ```
   Keep the address stable: a persistent named tunnel like this one keeps it across restarts.
2. **Tell Meta** (app settings): under **App settings > Basic > App domains** add the host name (for example `8hcq38ls-3000.inc1.devtunnels.ms`); under **Facebook Login for Business > Settings > Valid OAuth Redirect URIs** add `https://<that host>/api/meta/callback`, remove any `http://localhost` entry, and press **Save Changes**. The **Redirect URI Validator** on the same page should then say the address is valid.
3. **Start with that address and open it** (not `localhost`):
   ```powershell
   .\scripts\start-real.ps1 -PublicUrl https://8hcq38ls-3000.inc1.devtunnels.ms
   ```
   Set `$env:ADCRAFT_PUBLIC_URL` once to skip the option. With `-TunnelId <id>` the script also starts `devtunnel host` for you. The script sets `META_REDIRECT_URI`, `PUBLIC_BASE_URL` (`<address>/api`) and `ALLOWED_DEV_ORIGINS` itself; the DM webhook URL it prints is `<address>/api/webhooks/instagram`.
4. **Who can connect:** anyone with a role on the Meta app (administrator, developer or **tester**; up to 500 testers, no review needed) and access to the Page and ad account. Outside clients need Meta's App Review and Business Verification first.

### 3.5 Start and connect

```powershell
uv run uvicorn app.main:app --reload --reload-dir app --port 8000      # backend
cd ..\frontend; npm run dev                                            # frontend (second terminal)
```

1. Open http://localhost:3000, register and log in.
2. **Settings > Meta Connection > Connect with Facebook**, authorise all requested permissions. You return to Settings and the token (valid about 60 days) is stored encrypted.
3. **Pick the ad account and the Page** (only Pages with a linked Instagram account can be chosen) and *Save selection*.

### 3.6 Create and publish a real ad

1. **Draft**: describe the idea on the dashboard, or build it by hand. The AI proposes a title, objective, audience, budget, three ad texts and a picture brief; the code validates every limit.
2. **Review and edit** (chat or studio): headline up to 40 characters, text up to 125, description up to 30; objective **TRAFFIC** (website visits) or **AWARENESS** (reach); at most 5 Meta **interests** (each must still be confirmed by Meta); cities and countries; ages 18 to 65; budget at least ₹50 per day **and** at least your ad account's Meta minimum; start and end date. The picture must be at least 600 px wide and between 4:5 and 1.91:1 (1:1 recommended), JPEG or PNG.
3. **Publish**: *Publish and start Instagram ad*, review the summary and confirm. The server then:
   1. checks the rules above (it refuses housing, employment, credit and political ads, which need special categories this app does not support, and drafts with missing fields),
   2. creates, in order, the **campaign**, **ad set**, uploads the **image**, creates the **creative** and the **ad** (each step is recorded, so a failure can be **resumed** from the failed step or **discarded**, which deletes what was created),
   3. switches the ad, ad set and campaign to **ACTIVE** (campaign last).

   The campaign shows **ACTIVE**. Meta still reviews the ad; check **Ads Manager** for its status and delivery. The ad starts at least 10 minutes after you publish.
4. **Manage** from the campaign card: *Pause*, *Resume*, *Refresh insights* (real Meta numbers; also refreshed every `INSIGHTS_INTERVAL_HOURS`, default 6), *Delete* (removes the Meta objects and images).
5. **If the token expires** (Meta error 190) the connection is marked expired and the UI asks you to reconnect.

Ads run on Instagram **feed** placement only (`stream`).

### 3.7 Organic posts and DM agent on real accounts

- **Organic post** (sidebar *Post to Instagram*): choose an account the login manages, a picture and a caption. Real posting is off until `ALLOW_ORGANIC_PUBLISH=true`, and Meta must be able to download the picture, so set `PUBLIC_BASE_URL` to a public https address of the backend (for example an ngrok or Cloudflare tunnel).
- **DM agent** (sidebar *DM Agent*): register the webhook `https://<public-url>/webhooks/instagram` in the Meta app with the same value as `META_WEBHOOK_VERIFY_TOKEN`, subscribe the `messages` field, then save your knowledge block and tick auto-reply. Replies are sent only within 24 hours of the customer's last message.

Full steps, Meta permissions and review requirements: [docs/dm-agent-and-organic-posts.md](docs/dm-agent-and-organic-posts.md).

### 3.8 Going-live checklist

- [ ] Meta app has the redirect URI, products and permissions above; you have a role on it (or it is Live and reviewed).
- [ ] Ad account has a payment method; Page is linked to an Instagram professional account.
- [ ] `META_MODE=real`, real app id and secret, `META_REDIRECT_URI` identical in the app and the environment.
- [ ] `JWT_SECRET` and `TOKEN_ENCRYPTION_KEY` are your own (not sample values) and stored outside git.
- [ ] Both live-delivery switches on **only** when you mean to spend; caps set sensibly.
- [ ] Rotated any keys that were ever committed (see [Security](#7-security)).

---

## 4. AI provider and token cost

- **Switch provider** with `LLM_PROVIDER` (`openrouter`, `gemini`, or `litellm` for direct OpenAI); no code change. Each user can also save their own key and provider under Settings > API Keys and AI.

### OpenRouter: one key for Gemini and OpenAI models

[OpenRouter](https://openrouter.ai/) serves models from several vendors behind one key. Put the key in `.env` next to your other keys and choose the family with one setting:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<your key>        # your own OPENAI_API_KEY / GEMINI_API_KEY can stay in the file, unused
OPENROUTER_MODEL_FAMILY=openai       # openai = OpenAI GPT models (GPT-5), gemini = Google Gemini models
```

| `OPENROUTER_MODEL_FAMILY` | Ad drafting, chat and copy edits | DM agent replies |
|---|---|---|
| `gemini` | `google/gemini-3.5-flash-lite` | `google/gemini-3.5-flash-lite` |
| `openai` | `openai/gpt-5` | `openai/gpt-5` |

To use a different model, set the matching `OPENROUTER_<FAMILY>_<PRIMARY|UTILITY>_MODEL` to any id from [openrouter.ai/models](https://openrouter.ai/models).

Credit: OpenRouter reserves credit for the longest reply a call may produce, so every reply is capped by `OPENROUTER_MAX_TOKENS` (default 4096; an ad draft needs about 1.5k). If a call fails with `402 ... can only afford N tokens`, your balance is too low for that model: add credit, or pick a cheaper model id (`openai/gpt-5-mini`, `openai/gpt-6-luna`, `google/gemini-3.5-flash-lite`). GPT-5 is a reasoning model ($1.25 in / $10 out per million tokens): expect a few cents and about 15 to 40 seconds per ad draft, against well under 1 cent for the small models. Its reasoning tokens count toward `OPENROUTER_MAX_TOKENS`. Switching back to a direct key later is just `LLM_PROVIDER=gemini` or `litellm`. Users can also pick OpenRouter and the family under Settings > API Keys and AI.

Images do not go through OpenRouter: set `IMAGE_PROVIDER` to `fake`, or to `gemini` / `openai` with that provider's own key.
- If the provider is Gemini but `LLM_PRIMARY_MODEL` still names a `gpt-*` model, the Gemini default is used automatically.
- **Cost controls**: the ad prompt is about 540 tokens (measured); the picture brief is 50 to 80 words; chat history sent to the model is 6 messages; all text work (ads, chat edits, DM replies) uses one model per provider (GPT-5 by default for OpenAI, `gemini-3.5-flash-lite` for Gemini; switch to a smaller model to cut cost); DM replies send the last 6 messages plus your knowledge block; `OPENAI_IMAGE_QUALITY` defaults to `medium`.
- Gemini free-tier keys are limited per model per day, and Gemini image generation needs billing.

---

## 5. Tests

```powershell
cd backend
$env:TEST_MONGODB_URI = "mongodb://localhost:27017/?directConnection=true"   # use your port, e.g. 27117
uv run pytest -q                           # offline: scripted model + fake Meta (about 5 minutes)
uv run ruff check app tests

# Live Gemini end to end (uses quota; Meta stays fake)
$env:RUN_LIVE_GEMINI = "1"; $env:GEMINI_API_KEY = "<key>"
uv run pytest tests/live -s

# Live OpenRouter, both families with one key (uses credit)
$env:RUN_LIVE_OPENROUTER = "1"; $env:OPENROUTER_API_KEY = "<key>"
uv run pytest tests/live/test_openrouter_live.py -s

cd ..\frontend
npx vitest run; npx eslint components lib app; npx tsc --noEmit
```
The offline suite never calls OpenAI, Gemini or Meta.

---

## 6. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Backend: `ServerSelectionTimeoutError ... RSGhost` | A local `mongod` on 27017 hides the Docker one, or the replica set is not initialised yet. Use `docker compose up -d --wait mongo`, or the separate-port setup in [section 1](#mongodb-replica-set-required). |
| `409 SPEND_BLOCKED` on Publish | Live delivery is off. Set both switches ([3.4](#34-the-two-safety-switches)); in fake mode this is harmless. |
| `409 META_NOT_CONNECTED` | Connect Meta in Settings and choose an ad account and Page. |
| `402 ... can only afford N tokens` (OpenRouter) | Balance too low for that model: add credit or choose a cheaper `OPENROUTER_*_MODEL`; see [section 4](#4-ai-provider-and-token-cost). |
| `LLM_UNAVAILABLE` / "AI is busy" | Provider quota or outage; with the Gemini free tier try `GEMINI_PRIMARY_MODEL=gemini-3.5-flash-lite` or wait for the daily reset. |
| Meta error `190` | Token expired or revoked: reconnect in Settings. |
| Meta error `100` | Invalid parameter (for example budget below the ad account minimum). The message is shown on the failed step; fix it and *Resume*, or *Discard*. |
| Page missing from the account list | It has no linked Instagram professional account; link one in Meta Business Suite. |
| `422 BUDGET_BELOW_META_MINIMUM` | Raise the daily budget to Meta's minimum for that ad account. |
| `422 SPECIAL_AD_CATEGORY_UNSUPPORTED` | The ad looks like housing, employment, credit or political content. |
| OAuth shows "redirect_uri mismatch" | `META_REDIRECT_URI` must equal the URI in the Meta app character for character. |

More detail on Meta errors: [docs/meta-connection-guide.md](docs/meta-connection-guide.md).

---

## 7. Security

- **The repository's `.env` is committed and has contained real keys.** Treat any key that appeared in it as exposed: rotate the OpenAI, Gemini and Meta keys and tokens, then keep real values in environment variables or an untracked file, never in git.
- Meta tokens are stored encrypted (AES-256-GCM); requests to Meta are signed with `appsecret_proof`.
- Webhook deliveries are rejected unless `X-Hub-Signature-256` verifies against `META_APP_SECRET`.
- Customer text, the knowledge block and ad ideas reach the model wrapped as data, never as instructions.

---

## 8. Project layout

```
backend/app/
  agents/      ad drafter, chat editor, DM agent, model factory (Gemini / OpenAI / scripted)
  api/         FastAPI routers (auth, campaigns, media, meta_oauth, settings, dm, organic, webhooks)
  domain/      pure rules and state machine (no I/O)
  meta/        Meta gateway (real SDK + fake), OAuth, publisher, payload builders
  services/    campaign lifecycle, images, insights, DM agent, organic posts
backend/tests/ unit, integration, api, e2e, contract, live (opt-in)
frontend/      Next.js app (app/, components/, lib/)
docs/          Meta connection guide, DM agent and organic posts, plans and specs
```

Campaign states: `DRAFT -> PUBLISHING -> ACTIVE <-> PAUSED -> COMPLETED`, with `PUBLISH_FAILED` reachable from
`PUBLISHING` (resume or discard). `PAUSED_ON_META` is a legacy state that *activate* still accepts.
