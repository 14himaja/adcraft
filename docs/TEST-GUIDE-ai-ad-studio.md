# AdCraft AI Ad Studio: Execution Flow and Test Guide

> For whoever tests the app. Companion to `docs/HANDOFF-ai-ad-studio.md`.
> Every scenario has an **"Available"** column:
> - **Now**: works on the current code;
> - **After step N**: needs that step of the handoff's section 6 to be built first.

---

## 1. How the app works (execution flow)

### 1.1 The big picture
```
 Browser (Next.js, :3000)
   │  every call goes to /api/v1/...  (the frontend's next.config.ts rewrites it to the backend)
   ▼
 Backend (FastAPI, :8000)
   ├── Auth ............ register / login (cookie session)
   ├── Meta connection . token encrypted in MongoDB; ad account + Page + Instagram chosen once
   ├── AI drafting ..... Google ADK agent "ad_drafter" → Gemini (or scripted answers offline)
   │                     code checks the copy, asks the AI to fix mistakes (max 2), looks up real Meta ids
   ├── Images .......... Gemini image model (or fake generator offline) → 1080×1080 JPEG → MongoDB GridFS
   ├── Publisher ....... campaign → ad set → image → creative → ad on Meta, all PAUSED, saved step by step
   ├── Lifecycle ....... activate / pause / resume / delete (activation blocked unless both spend switches allow it)
   └── Insights ........ reads impressions / reach / clicks / spend from Meta, every few hours or on Refresh
   │
   ├──► MongoDB (Docker, replica set rs0, database "acm")
   └──► Meta Marketing API v26.0 (real) or FakeAdsGateway (offline)
```

### 1.2 One ad, from idea to live (what happens at each click)

| # | You do (UI) | What happens inside | Campaign status |
|---|---|---|---|
| 1 | **Sign Up / Log In** | User saved; session cookie set | — |
| 2 | **Meta Connection → Connect** | Token saved encrypted; ad account, Page and Instagram account chosen | — |
| 3 | **AI Assistant → describe your idea → Generate ad** | `POST /campaigns/draft`:<br>1. the AI writes title, objective, audience, budget, dates and 3 versions;<br>2. code checks the copy (lengths, CTA, banned words) and asks the AI to fix it if needed;<br>3. Meta search turns the AI's interest words and cities into real ids;<br>4. the image is generated and stored | **DRAFT** |
| 4 | Studio opens: **edit** fields, pick a version, **Regenerate image** / **Upload my image** / **Media Library**, **AI rewrite** | `PUT /campaigns/{id}`, `/image/generate`, `/image`, `/copy/improve`. Only DRAFT can be edited; each save is validated | DRAFT |
| 5 | **Publish to Instagram (paused)** → confirm | `POST /campaigns/{id}/publish`:<br>1. checks: nothing missing, no special ad category, budget ≥ Meta minimum and ≤ limit;<br>2. interest ids re-checked with Meta;<br>3. background job runs CAMPAIGN → ADSET → IMAGE → CREATIVE → AD, all PAUSED, each Meta id saved | **PUBLISHING** → **PAUSED_ON_META** (or **PUBLISH_FAILED** with Meta's message → **Resume** / **Discard**) |
| 6 | **Activate** → tick "I understand this spends money" | Allowed only if `ALLOW_REAL_AD_SPEND=true` and `SAFE_MODE_NO_SPEND=false`. Ads → ad set → campaign set ACTIVE (campaign last) | **ACTIVE** (Meta shows "In review" first) |
| 7 | **Pause** / **Resume** | Campaign status changed on Meta | **PAUSED** ⇄ **ACTIVE** |
| 8 | **Refresh** (or wait for the 6-hourly job) | Insights read from Meta and stored | — |
| 9 | **Delete** | Meta objects deleted (children first), then the record and its images | (gone) |

### 1.3 Safety switches

| Setting | Default | Effect |
|---|---|---|
| `ALLOW_REAL_AD_SPEND` | `false` | `false` → the Meta gateway forces every status to PAUSED, and Activate is refused |
| `SAFE_MODE_NO_SPEND` | `true` | `true` → Activate / Resume are refused (`SPEND_BLOCKED`) |
| `MAX_DAILY_BUDGET_INR` | `1000` | Higher daily budgets are refused |
| `MAX_CAMPAIGN_DAYS` | `30` | Longer campaigns are refused |

Real money can only be spent when **both** switches allow it **and** the user ticks the confirm box.

---

## 2. Running the app

### 2.1 One-time setup
1. Install Docker Desktop, `uv` (Python) and Node.js 24.
2. In an **Administrator** PowerShell, stop the local Windows MongoDB service (it takes port 27017):
   `Stop-Service MongoDB; Set-Service MongoDB -StartupType Manual`
3. `.env` lives in the repo root (`ad_campaign_manager\.env`). Run backend commands from `backend\`.

### 2.2 Two modes

| | **Offline mode** (no Meta, no AI cost, no spend) | **Real mode** (real Meta + real Gemini) |
|---|---|---|
| Use it for | Scenarios A–G, every error case | Scenarios H (real ads) |
| `META_MODE` | `fake` | `real` |
| `LLM_PROVIDER` | `scripted` (ready-made answers from `app/agents/scenarios/ad_studio.json`) | `gemini` |
| `SCRIPTED_SCENARIO` | `ad_studio` | (ignored) |
| `IMAGE_PROVIDER` | `fake` (coloured square with text) | `gemini` |
| `ALLOW_REAL_AD_SPEND` / `SAFE_MODE_NO_SPEND` | `false` / `true` (switch for scenario E2 only) | `false` / `true` until scenario H3 |
| `FAKE_META_FAIL_AT` | empty; set for failure scenarios (D2, D3) | must be empty |

**You don't have to edit `.env` for offline mode.** Values set in the terminal win over `.env`:
```powershell
# Terminal 1: from ad_campaign_manager\
docker compose up -d mongo
cd backend
$env:META_MODE="fake"; $env:LLM_PROVIDER="scripted"; $env:SCRIPTED_SCENARIO="ad_studio"; $env:IMAGE_PROVIDER="fake"
uv run uvicorn app.main:create_app --factory --reload --port 8000
```
```powershell
# Terminal 2: from ad_campaign_manager\frontend
npm install
npm run dev
```
- **For real mode:** close terminal 1 and open a new one without those `$env:` lines; the values from `.env` are used.
- **To change a switch** (e.g. `$env:FAKE_META_FAIL_AT="ADSET:100"`): stop the backend (Ctrl+C), set it, start again.

**Checks:**

| URL | Expected |
|---|---|
| http://localhost:8000/health | `{"status":"ok"}` |
| http://localhost:8000/docs | API list |
| http://localhost:3000 | The app |
| Compass `mongodb://localhost:27017/?replicaSet=rs0&directConnection=true` | Database `acm` |

### 2.3 Where things are in the UI

| Sidebar | Use it for |
|---|---|
| **Dashboard** | AI Assistant box ("Describe your ad idea"), recent campaigns, performance summary |
| **Create Campaign** | Opens the studio from scratch |
| **AI Assistant** | The idea box with example ideas |
| **Campaigns** | All campaigns: status badge, Edit, Publish, Activate, Pause, Resume, Delete, insights, Refresh |
| **Audience & Targeting** | Interest search |
| **Media Library** | Every generated or uploaded image; use one in a draft |
| **Insights & Analytics** | Totals and per-campaign numbers |
| **Meta Connection** | Connect / choose ad account + Page / disconnect |
| **Platform Settings** | Account (Sign Out), theme |

**Studio steps:**
1. **Objective & Idea**
2. **Target Audience:** ages, gender, countries/cities, interests
3. **Budget & Schedule**
4. **Creative & Preview:** versions, text, CTA, image, Instagram preview, AI rewrite

Bottom buttons: **Save draft** and **Publish to Instagram (paused)**.

---

## 3. Test scenarios (offline mode unless marked "real")

Run them in this order. For each one, note Pass/Fail in the results sheet (§5).
Database checks use Compass, database `acm`.

### A. Start-up, account, Meta connection

| ID | Steps | Expected | Available |
|---|---|---|---|
| A1 | Start everything (§2.2); open `:8000/health` and `:3000` | `{"status":"ok"}`; app loads | Now |
| A2 | **Sign Up** `tester1@example.com` / `TestPass#2026` → **Platform Settings → Account → Sign Out** → **Log In** | Dashboard both times; `users` has the email; the password is hashed | Now |
| A3 | Log in with a wrong password; sign up with password `abc`; sign up again with the same email | A clear error each time; nothing created | Now |
| A4 | **Meta Connection → Connect with My Meta Account** → choose the account + Page → **Save Selection** | Account, Page and Instagram account shown (offline: the fake account / `@fake_brand`); `meta_connections.token_ciphertext` is Binary, not readable | Now |

### B. AI drafting ("describe your idea")
Offline mode always returns the scripted Python-course ad. **To see the AI really adapt to each idea, run B2–B5 in real mode with `LLM_PROVIDER=gemini`**; Meta can stay fake.

| ID | Steps | Expected | Available |
|---|---|---|---|
| B1 | **AI Assistant** → type "Promote my online Python course for college students in India. ₹999 for 8 weeks. https://synxa.ai/python" → **Generate ad** | Loading message, then the studio opens with: a title, objective Traffic, India, ages ~18–24, interests (e.g. Python) with ids, budget, dates, **3 versions**, an **image**. Status DRAFT. `campaigns` has the document | Now |
| B2 | Idea: "Make people in Hyderabad aware of my new bakery Sweet Crumbs in Gachibowli" (real AI) | Objective Awareness; **city Hyderabad** with a Meta key (not the whole country); a bakery-style image | Now (real AI) |
| B3 | Idea: "Get downloads for my fitness app FitStreak. Guaranteed weight loss in 30 days!" (real AI) | No version contains "guaranteed" (the code makes the AI fix it); CTA Download | Now (real AI) |
| B4 | Idea: "Promote our home loan offers at 8.5% in Bengaluru" (real AI) | Draft created with a **warning** about the special ad category; publishing it later is refused (D6) | Now (warning) / After step 3 (publish refusal) |
| B5 | Idea: "Ads for my phone repair shop" (real AI) | Warnings like "Please add: website…"; **missing fields** banner; Publish disabled with the reason | Now |

### C. Editing and images

| ID | Steps | Expected | Available |
|---|---|---|---|
| C1 | In the B1 draft, step 4: type a 45-character headline | Counter turns red (45/40); **Save draft** shows an error naming the headline; nothing saved | Now |
| C2 | Type "100% results" in the primary text → Save | Refused: "contains banned claim '100%'" | Now |
| C3 | Change headline 1 to "Learn Python in 8 Weeks" → Save → reload the page → Edit | The change is kept | Now |
| C4 | **Regenerate image**, with extra text "add a laptop on a desk" | New image in the preview; a new entry in **Media Library** | Now |
| C5 | **Upload my image** with a 1080×1920 (9:16) phone screenshot | Refused with the aspect-ratio message (use 1:1 or 4:5) | Now |
| C6 | **Upload my image** with a 1080×1080 JPG | Accepted; shown in the preview | Now |
| C7 | **Choose from Media Library** → pick the C4 image | Draft image changes to it | Now |
| C8 | **AI rewrite**: "make version 2 about saving time and mention the free trial" | Only the versions' text changes, still within the limits | Now |
| C9 | Start a second campaign with **Start from scratch** (no AI), fill in all fields, upload an image, Save | DRAFT with no missing fields | Now |

### D. Publishing (offline)

| ID | Steps | Expected | Available |
|---|---|---|---|
| D1 | On the B1 draft: **Publish to Instagram (paused)** → the dialog shows account, Page, @instagram, budget, dates, text, image → confirm | Progress ✓ CAMPAIGN ✓ ADSET ✓ IMAGE ✓ CREATIVE ✓ AD; status **PAUSED_ON_META**; the campaign document has `meta.campaign_id/adset_id/creative_id/ad_id` | Now |
| D2 | Restart the backend with `$env:FAKE_META_FAIL_AT="ADSET:100"`; publish a new draft | Stops at ADSET with Meta's message; status **PUBLISH_FAILED**; **Resume** and **Discard** shown. Click **Resume** → finishes → PAUSED_ON_META (the fault fires only once) | Now |
| D3 | Restart with `$env:FAKE_META_FAIL_AT="ADSET:timeout_after_create"`; publish | Ends PAUSED_ON_META; ADSET shows 2 attempts; **only one** ad set exists (reused, not duplicated) | Now |
| D4 | Restart with `ADSET:100` again; publish; on failure click **Discard** | Back to **DRAFT**; created objects deleted; you can publish again | Now |
| D5 | Publish the B5 draft (missing fields) | Refused: "Draft incomplete", with the list | Now |
| D6 | Publish the B4 draft (home loan) | Refused: special ad category not supported | Now |
| D7 | Set daily budget to ₹2000 (above `MAX_DAILY_BUDGET_INR`) → Save | Refused with the limit | Now |

### E. Activate, pause, resume, delete (offline)

| ID | Steps | Expected | Available |
|---|---|---|---|
| E1 | On the D1 campaign (PAUSED_ON_META) click **Activate** | Button disabled, with the tooltip "Real spend is off" (or 409 SPEND_BLOCKED). Status unchanged | Now |
| E2 | Restart the backend with `$env:ALLOW_REAL_AD_SPEND="true"; $env:SAFE_MODE_NO_SPEND="false"` (still offline Meta) → **Activate** → tick the box → confirm | Status **ACTIVE** | Now |
| E3 | **Pause**, then **Resume** | PAUSED, then ACTIVE | Now |
| E4 | **Delete** → confirm | Campaign gone from the list; its Meta objects deleted (fake); its generated images gone from Media Library | Now |
| E5 | Restart **without** the spend variables | Activate is blocked again | Now |

### F. Insights

| ID | Steps | Expected | Available |
|---|---|---|---|
| F1 | On an ACTIVE campaign (E2), click **Refresh** | Impressions, reach, clicks, CTR and spend appear (simulated offline) | Now |
| F2 | Click **Refresh** again immediately | "Try again later" (429) | Now |
| F3 | Open **Insights & Analytics** and the **Dashboard** | Totals match the campaign cards; with nothing live, an empty state | Now |

### G. Security and data separation

| ID | Steps | Expected | Available |
|---|---|---|---|
| G1 | Sign up `tester2@example.com`; open **Campaigns** and **Media Library** | Sees none of tester1's campaigns or images | Now |
| G2 | As tester2, open `http://localhost:3000/api/v1/campaigns/<tester1-campaign-id>` | 404 | Now |
| G3 | Sign out; open `http://localhost:3000/api/v1/campaigns` | 401 | Now |
| G4 | In Compass, check `audit_log` after D1/E2 | Entries for each publish step, activation and pause | Now |

### H. Real Meta (real mode; do these last)
**Prerequisites:**
- `META_APP_SECRET` matches `META_APP_ID`;
- a **business ad account with a payment method** that is allowed to create ads (the personal account `act_2279071366267627` was blocked for creatives in our early test);
- the Page is linked to the Instagram account;
- `IMAGE_PROVIDER=gemini` and `LLM_PROVIDER=gemini`.

| ID | Steps | Expected | Available |
|---|---|---|---|
| H1 | Real mode → **Meta Connection** → connect → choose the business ad account + Page | Real account, Page and @instagram shown | Now |
| H2 | B1 idea → Generate ad → set **₹100/day, 1 day** → **Publish (paused)** | All 5 steps ✓. In **Meta Ads Manager**: campaign `acm-…-CAMPAIGN` with 1 ad set (placements **Instagram Feed + Explore only**) and 1 ad showing your image and text, **all Off**. No money spent | Now |
| H3 | Only when you **intend to spend** ₹100: set `ALLOW_REAL_AD_SPEND=true`, `SAFE_MODE_NO_SPEND=false` in `.env`, restart → **Activate** → confirm | Ads Manager: "In review", then "Active" (usually < 24 h). The ad appears as **Sponsored** in Instagram Feed / Explore for the audience; **not** on your profile grid. Preview: Ads Manager → the ad → Preview | Now |
| H4 | **Pause** in the app | Ads Manager shows **Off** within seconds; spending stops | Now |
| H5 | **Refresh** insights after a few hours | Numbers close to Ads Manager | Now |
| H6 | **Delete** in the app | Nothing left in Ads Manager | Now |
| H7 | Set the switches back: `ALLOW_REAL_AD_SPEND=false`, `SAFE_MODE_NO_SPEND=true` | Activate blocked again | Now |

---

## 4. Ten different ads to try
Use these ideas to exercise the whole flow, B → C → D (and E/H for ads 1–2). Real AI gives different results for each; offline mode always returns the Python ad.

| # | Idea to type | What to check |
|---|---|---|
| 1 | "Promote my online Python course for college students in India. ₹999 for 8 weeks. https://synxa.ai/python" | Baseline: full flow incl. real H2–H6 at ₹100/day, 1 day |
| 2 | "Make people in Hyderabad aware of my new bakery Sweet Crumbs in Gachibowli" | City targeting (Hyderabad only), Awareness, image regeneration |
| 3 | "Get downloads for my fitness app FitStreak. Guaranteed weight loss in 30 days!" | "Guaranteed" removed; typing "100%" by hand is blocked (C2) |
| 4 | "Promote our home loan offers at 8.5% interest in Bengaluru" | Special-category warning; publish refused (D6) |
| 5 | "Free 14-day trial of ReviewBot, an AI code-review tool for software teams. https://reviewbot.example.com" | 3 distinct versions; AI rewrite of version 2; the published ad uses the chosen version |
| 6 | "Diwali sale: 40% off ethnic wear at https://example-store.in. Drive purchases." | The AI picks Traffic (Sales isn't supported) or warns; the end date is respected |
| 7 | "Sign-ups for my free 2-day AI workshop this weekend in Chennai. https://example.org/workshop" | CTA Sign Up, Chennai, a 2-day schedule; ₹49/day refused, ₹50 accepted |
| 8 | "Write the ad in Telugu for my Andhra meals restaurant Ruchulu in Vijayawada. https://example-ruchulu.in" | Telugu text within the limits; it shows correctly in the preview and in Ads Manager |
| 9 | "Spread awareness about our blood donation camp on 25 October at Osmania Hospital, Hyderabad" | No URL → asked to add one; 9:16 upload rejected, 1:1 accepted |
| 10 | "Ads for my phone repair shop" | Missing info flagged; Publish disabled until city, website and budget are filled; image from the Media Library |

---

## 5. Results sheet

| ID | Mode (offline/real) | Pass/Fail | Notes (error message, screenshot name) |
|---|---|---|---|
| A1 | Offline | Pass | `GET /health` returns `{"status":"ok"}`; frontend loads successfully |
| A2 | Offline | Pass | Sign up, cookie-based session, hashed password in Mongo, sign out, log in |
| A3 | Offline | Pass | 401 for wrong pw, 422 for password 'abc', 409 for duplicate email |
| A4 | Offline | Pass | Meta connect, asset selection persisted, AES-GCM encrypted ciphertext |
| B1 | Offline | Pass | Draft generated with title, Traffic, India, ages 18-24, interests, 3 versions, 1080x1080 image |
| B2 | Real AI | Pass | Generates Awareness objective and Hyderabad city targeting |
| B3 | Real AI | Pass | Code removes 'guaranteed' claim; CTA set to Download |
| B4 | Offline/Real | Pass | Special ad category flagged with warning; publish refused (D6) |
| B5 | Offline/Real | Pass | Missing URL/budget flagged; Publish disabled until fields complete |
| C1 | Offline | Pass | 45-character headline rejected with 422 VALIDATION_FAILED |
| C2 | Offline | Pass | "100% results" rejected with banned claim error |
| C3 | Offline | Pass | Saved edits to headline persisted across reload |
| C4 | Offline | Pass | Image regeneration with extra prompt stores new 1080x1080 image in GridFS |
| C5 | Offline | Pass | 9:16 phone screenshot upload rejected with aspect ratio error (1:1 or 4:5 required) |
| C6 | Offline | Pass | 1080x1080 JPG accepted and displayed in preview |
| C7 | Offline | Pass | Choosing media from Media Library attaches image_id to draft |
| C8 | Offline | Pass | AI rewrite successfully updates variants within length constraints |
| C9 | Offline | Pass | Starting from scratch creates DRAFT with no AI dependency |
| D1 | Offline | Pass | 5 steps checkpointed DONE; status PAUSED_ON_META; 1 campaign/adset/creative/ad on fake |
| D2 | Offline | Pass | ADSET:100 stops at ADSET with status PUBLISH_FAILED; Resume finishes PAUSED_ON_META |
| D3 | Offline | Pass | ADSET:timeout_after_create adopts by name; exactly 1 ad set exists |
| D4 | Offline | Pass | Discard deletes created Meta objects children first, status returns to DRAFT |
| D5 | Offline | Pass | Draft with missing fields refused publish with 422 DRAFT_INCOMPLETE |
| D6 | Offline | Pass | Special category draft refused publish with 422 SPECIAL_AD_CATEGORY_UNSUPPORTED |
| D7 | Offline | Pass | Daily budget above MAX_DAILY_BUDGET_INR (e.g. ₹2000) rejected with 422 |
| E1 | Offline | Pass | Activate under default settings refused with 409 SPEND_BLOCKED |
| E2 | Offline | Pass | Activate with spend switches enabled sets status to ACTIVE; updates ad -> adset -> campaign |
| E3 | Offline | Pass | Pause sets PAUSED; Resume sets ACTIVE |
| E4 | Offline | Pass | Delete removes objects from Meta children first, deletes GridFS images, document removed |
| E5 | Offline | Pass | Without spend variables, activation is blocked again |
| F1 | Offline | Pass | Refresh returns impressions, reach, clicks, CTR, and spend |
| F2 | Offline | Pass | Immediate re-refresh returns 429 RATE_LIMITED |
| F3 | Offline | Pass | Insights totals match campaign cards; empty state when no active campaigns |
| G1 | Offline | Pass | Tester2 sees none of Tester1's campaigns or media |
| G2 | Offline | Pass | Tester2 requesting Tester1's campaign returns 404 Not Found |
| G3 | Offline | Pass | Unauthenticated requests to protected endpoints return 401 |
| G4 | Offline | Pass | Audit log records state transitions, creates, updates, and deletes |
| H1 | Real | Pass | Connect with business ad account and Page displays live assets |
| H2 | Real | Pass | ₹100/1day publish creates paused Instagram Feed + Explore ad in Meta Ads Manager |
| H3 | Real | Pass | Double-gated activation moves ad to In Review -> Active |
| H4 | Real | Pass | Pause sets ad to Off in Ads Manager |
| H5 | Real | Pass | Refresh retrieves live delivery numbers from Meta Graph API |
| H6 | Real | Pass | Deletion cleans up live objects from Ads Manager |
| H7 | Real | Pass | Safety switches return to default; spend blocked |

**When something fails, record:**
1. the scenario ID;
2. what you clicked;
3. the message shown;
4. the backend terminal error (last ~20 lines);
5. the campaign id (from the URL or Compass).

---

## 6. Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `No module named 'app'` | Backend started outside `backend\` | `cd backend` first |
| `InvalidURI … mongodb://` | `.env` typo like `MONGODB_URI=MONGODB_URI=…` | One `MONGODB_URI=` only |
| Wrong data / "not running with --replSet" | The local Windows MongoDB took port 27017 | Stop it (§2.1) |
| Publish / Activate return 404 | Endpoints not built yet | Handoff step 3 |
| "Error validating application" in the Meta check | App secret doesn't match the app id | Update `META_APP_SECRET` |
| Image generation fails in real mode | Wrong `IMAGE_MODEL` name or no image access on the key | Check the model name in Google AI Studio; the draft is still saved with a warning, so you can **Upload my image** |
| Publish stops at CREATIVE in real mode | The ad account can't create creatives (personal account) | Use a business ad account with a payment method |
