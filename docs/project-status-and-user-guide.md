# AdCraft (Ad Campaign Manager): Status, User Guide, Build Plan and Test Scenarios

> Covers branch `main` at commit `761b670` (14 Oct 2026). For the people building and testing the app.
>
> **The goal:** you **describe your idea** in one sentence → the AI **creates the ad** (text **and image**) → you **review and edit** it → you **publish** it to Instagram (paused) → you **activate** it → later you **pause** it, all from the UI.
>
> | Part | Sections |
> |---|---|
> | Where we are today | 1, 2 |
> | How to run it and get around the UI | 3, 4 |
> | **How to build everything that's missing** (Phases 0–9) | 5 |
> | `.env` and Meta setup for real ads | 6 |
> | The real-ad process | 7 |
> | **Test scenarios:** 10 basic UI checks and **10 different ads** | 8, 9 |
> | Known issues | 10 |

---

## 1. Where we are

| Area | Today | Built in |
|---|---|---|
| Sign up / log in / log out | ✅ Real | Auth |
| Connect Meta (`.env` token or OAuth) and choose ad account + Page | ✅ Real | Meta OAuth |
| Meta interest and city search | ✅ Real Meta data | Meta Search |
| Create a campaign in the 4-step studio | ✅ Saved in app as DRAFT (no premature Meta writes) | Phase 1 |
| Campaign list, delete | ✅ Real (deletes Meta objects children-first + GridFS images) | Phase 6 |
| **Describe an idea → AI drafts the ad** | ✅ Real (Google ADK agent + Gemini / Scripted offline) | Phase 2 |
| **AI image generation** | ✅ Real (Gemini image model / Fake generator offline) | Phase 3 |
| Upload your own image | ✅ Real (1080×1080 JPEG GridFS storage; 9:16 rejected) | Phase 3 |
| AI rewrite of the ad text ("AI Polish Copy") | ✅ Real (Google ADK copy_editor agent with code validation) | Phase 4 |
| Edit a saved campaign | ✅ Real (`PUT /campaigns/{id}` with pure validation) | Phase 4 |
| Ad set, image upload, creative, ad on Meta | ✅ Real (Checkpointed publisher engine, Instagram placements) | Phase 5 |
| Publish progress, Meta errors shown in the UI | ✅ Real (Live polling, step-by-step progress, Resume & Discard) | Phase 5 |
| Activate / Pause / Resume from the UI | ✅ Real (Double-gated spend check, ad -> adset -> campaign order) | Phase 6 |
| Delete on Meta too | ✅ Real (Children-first deletion, code 100 handled safely) | Phase 6 |
| Real performance numbers (reach, clicks, spend) | ✅ Real (Insights service, 5-min rate limit, background sync) | Phase 7 |
| Media Library (stored images) | ✅ Real (GridFS bucket `images`, list and reuse in draft) | Phase 8 |
| Audience & Targeting → apply to a campaign | ✅ Real (Meta interest and city search applied to studio) | Phase 8 |
| Spending limits and safety switches | ✅ Real (`ALLOW_REAL_AD_SPEND`, `SAFE_MODE_NO_SPEND`, Caps) | Phase 9 |

**In one line:** The full end-to-end AI Ad Studio is built and tested: idea → AI draft (copy + 1080×1080 image) → edit & rewrite → publish paused to Instagram → double-gated activation → pause/resume/delete on Meta → real performance analytics.

---

## 2. What each screen really does today

| Sidebar item | What you see | Real or mock |
|---|---|---|
| **Dashboard** | Banner, AI Assistant card ("Describe your ad idea"), recent campaigns, performance summary | Real |
| **Create Campaign** | 4-step studio: Objective & Idea → Target Audience → Budget & Schedule → Creative & Preview | Real |
| **AI Assistant** | "Describe your ad idea" input box with example idea chips and loading state | Real |
| **Campaigns** | All user campaigns: status badges, Edit, Publish, Activate, Pause, Resume, Delete, Insights | Real |
| **Audience & Targeting** | Real-time Meta interest search and country-code selector | Real |
| **Media Library** | User's generated and uploaded images served from MongoDB GridFS | Real |
| **Insights & Analytics** | Real Meta delivery metrics (impressions, reach, clicks, CTR, spend in INR) | Real |
| **Meta Connection** | Connect / choose ad account + Page / Instagram handle / token expiry / disconnect | Real |
| **Platform Settings** | Meta settings, Account (Sign Out), Theme switcher (Dark/Light mode) | Real |

---

## 3. How to run it

### 3.1 One-time setup
1. Install **Docker Desktop**, **uv** (Python) and **Node.js 24**.
2. Stop the local Windows MongoDB service; Docker's MongoDB uses the same port, 27017. In an **Administrator** PowerShell:
   ```powershell
   Stop-Service MongoDB; Set-Service MongoDB -StartupType Manual
   ```
3. The `.env` file is in the **project root**: `ad_campaign_manager\.env`.

### 3.2 Every time

**Terminal 1** (from `ad_campaign_manager\`):
```powershell
docker compose up -d mongo
docker compose ps                         # wait for (healthy)
cd backend
uv sync
uv run --env-file ../.env python scripts/meta_smoke.py      # optional Meta check
uv run uvicorn app.main:create_app --factory --reload --port 8000
```

**Terminal 2:**
```powershell
cd ad_campaign_manager\frontend
npm install
npm run dev
```

| URL | What |
|---|---|
| http://localhost:3000 | The app |
| http://localhost:8000/health | `{"status":"ok"}` |
| http://localhost:8000/docs | API docs |
| Compass: `mongodb://localhost:27017/?replicaSet=rs0&directConnection=true` | Database `acm` |

### 3.3 Common errors

| Error | Cause | Fix |
|---|---|---|
| `No module named 'app'` / `No environment file found at ../.env` | Started from the wrong folder | Run backend commands from `backend\` |
| `InvalidURI: URI must begin with 'mongodb://'` | Typo like `MONGODB_URI=MONGODB_URI=...` | Only one `MONGODB_URI=` |
| `llm_provider Input should be 'litellm' or 'scripted'` | `LLM_PROVIDER=gemini` without the Gemini fix | Phase 0, step 1 |
| Wrong or standalone MongoDB | The local MongoDB service took port 27017 | Stop it (3.1 step 2) |
| Meta check: `Error validating application` | `META_APP_SECRET` doesn't match `META_APP_ID` | Copy the App secret from Meta for Developers → App settings → Basic |

---

## 4. UI guide

### 4.1 Today
```
http://localhost:3000 → Sign Up / Log In → Dashboard
Sidebar:
 ├─ Dashboard ............ banner, AI shortcuts, recent campaigns
 ├─ Create Campaign ...... 4-step studio → "Create Campaign (PAUSED)"
 ├─ AI Assistant ......... shortcuts (open the studio)
 ├─ Campaigns ............ list, status, delete
 ├─ Audience & Targeting . interest search
 ├─ Media Library ........ (mock)
 ├─ Insights & Analytics . (mock)
 ├─ Meta Connection ...... connect, choose ad account + Page, disconnect
 └─ Platform Settings .... Meta, AI, Account (Sign Out), Appearance
```
**Connect Meta:** **Meta Connection → Connect with My Meta Account** uses the token in `.env`; this is the easiest for testing. **Connect with Meta** is the real Facebook login, which needs a correct app secret.

### 4.2 Target flow (after Phases 0–9)
```
Dashboard
 └─ AI Assistant: "Describe your ad idea" box ─► [Generate ad]
      └─ Draft review screen (= the studio, prefilled by the AI)
          1. Objective & Idea      AI-suggested title, objective, landing URL     (editable)
          2. Target Audience       AI-suggested ages, places, interests (real ids) (editable)
          3. Budget & Schedule     daily budget, start/end date                   (editable)
          4. Creative & Preview    3 AI ad versions (headline, text, CTA) + AI image
                                   [Regenerate image] [Upload my image] [AI: rewrite with my instruction]
          [Save draft]  [Publish to Instagram (paused)]
 └─ Campaigns
      campaign card: status badge (DRAFT / PUBLISHING / PAUSED ON META / ACTIVE / FAILED)
      [Edit] [Publish] [Activate] [Pause] [Resume] [Delete]
      publish progress: ✓ campaign ✓ ad set ✓ image ✓ creative ✓ ad (or the error + Resume/Discard)
 └─ Insights & Analytics: real reach, impressions, clicks, CTR, spend per campaign
 └─ Media Library: every generated or uploaded image, reusable
```

---

## 5. Build plan for everything marked ❌

The design and code for publishing (Phases 5–6) already exist as a detailed plan in `docs/.claude/plans/04-06-brief-review-publish.plan.md` (Part C); adapt it to the current campaign model.

Rules for every phase:
- write tests first;
- keep everything **PAUSED** unless `ALLOW_REAL_AD_SPEND=true`;
- show every Meta error in the UI;
- one PR per phase.

### Phase 0: Fix-ups (½ day)
1. **Commit the Gemini fix.** It's already done in Praveen's working copy: `backend/app/config.py` (`LLM_PROVIDER` accepts `gemini`, adds `gemini_api_key` / `openai_api_key`), `backend/app/agents/models.py` (sends `gemini/<model>` with the key), plus a test in `tests/agents/test_scripted_model.py`.
2. **Correct `META_APP_SECRET`** in `.env`.
3. **README:** remove the `c:\Users\sreej\...` path; add the run steps from section 3.
4. **Lint:** fix the 4 Ruff warnings (`uv run ruff check . --fix`, then fix the rest by hand).

**Done when:** the backend starts with the shared `.env`, and `uv run pytest -q` and `uv run ruff check .` are clean.

### Phase 1: Campaign data model and states (1 day)
**Why:** today a campaign is one flat record with no draft/publish states, no image link and interest *names* only.

1. Extend the campaign document. Fields:
   - `status`
   - `idea` (the user's text)
   - `objective`
   - `landing_url`
   - `audience { countries[], cities[{key,name}], age_min, age_max, genders, interests[{id,name}] }`
   - `daily_budget_minor` (paise)
   - `start_date`, `end_date`
   - `variants[{headline, primary_text, description, cta}]` and `selected_variant`
   - `image_id`
   - `meta { campaign_id, adset_id, image_hash, creative_id, ad_id }`
   - `publish { status, steps[], error }`
2. Add a state table (reuse `app/domain/states.py` and `app/services/transitions.py` from M2): `DRAFT → PUBLISHING → PUBLISHED_PAUSED ⇄ ACTIVE`, with `PUBLISH_FAILED → PUBLISHING (resume) / DRAFT (discard)` and `ACTIVE/PAUSED → COMPLETED`.
3. Endpoints:
   - `POST /campaigns` creates a **DRAFT** only; it must stop creating anything on Meta;
   - `GET /campaigns/{id}`;
   - `PUT /campaigns/{id}` edits, allowed in DRAFT only.
4. Frontend: keep interest **ids** from the interest search; send the budget in rupees and let the backend convert to paise (₹500 → `50000`).

**Done when:** creating a campaign saves a DRAFT with interest ids, and an edit of a DRAFT works. Editing a published campaign is refused (409).

### Phase 2: "Describe your idea" → AI drafts the ad (2 days)
1. **Backend: `POST /campaigns/draft`** with body `{ "idea": "..." }`. One AI call (Gemini via the existing ADK setup; an agent with an `output_schema`) returns:
   - `title`, `objective` (`TRAFFIC` or `AWARENESS` for now);
   - `landing_url` if the idea has one, otherwise empty;
   - audience keywords, ages, countries or cities;
   - suggested daily budget and duration;
   - **3 ad variants** (headline ≤ 40, text ≤ 125, description ≤ 30, CTA from the allowed list);
   - an **`image_prompt`** describing a 1:1 Instagram image.
2. **Validate with code, not the AI:**
   - lengths, CTA and banned claims ("guaranteed", "100%", "#1", "risk-free", "Are you…?") with `app/domain/models.py` → `finalize_assets` (M2);
   - if invalid, send the exact errors back to the AI, at most twice (the M2 repair loop).
3. **Resolve interests:** for each audience keyword call Meta interest search and keep only **real ids**; drop anything Meta doesn't return.
4. Save the result as a **DRAFT** campaign (fields from Phase 1) and return it.
5. **Frontend:** turn the AI Assistant card into an input box, **"Describe your ad idea"**, with a **Generate ad** button and a loading state. When it finishes, open the studio prefilled with the draft. The shortcut buttons become example ideas.
6. Prompt safety: the user's text is treated as data; the AI can't publish, activate or spend.

**Done when:** typing an idea produces a DRAFT with 3 valid variants, real interest ids and an image prompt, in under about 20 seconds.

### Phase 3: AI image generation + upload your own image (1–2 days)
1. **Settings:** `IMAGE_PROVIDER=gemini`, `IMAGE_MODEL=gemini-2.5-flash-image` (Gemini's image model; check the current model name in Google AI Studio). It uses the same `GEMINI_API_KEY`.
2. **Backend: `POST /campaigns/{id}/image/generate`** with body `{ "prompt": "optional extra instructions" }`:
   1. Build the prompt: draft `image_prompt` + brand/product + "square 1:1 Instagram feed ad, no text overlay, high quality".
   2. Call the image model with the `google-genai` client (already installed with ADK) and take the image bytes.
   3. With **Pillow**, centre-crop and resize to **1080×1080 JPG**.
   4. Check it with `check_instagram_image()` (`app/domain/media.py`, M2): JPG/PNG, ≤ 8 MB, ≥ 600 px wide, ratio 0.8–1.91.
   5. Store it in MongoDB **GridFS** (bucket `images`) with the owner, campaign and prompt; set `campaign.image_id`.
3. **Backend: `POST /campaigns/{id}/image`** (multipart upload of your own image) → same check → GridFS. Story-shaped (9:16) images get the clear error "use 1:1 or 4:5".
4. **Backend: `GET /images/{id}`** serves the bytes (owner only). `GET /media` lists the user's images (used in Phase 8).
5. **Frontend (step 4 of the studio):**
   - show the generated image in the Instagram preview;
   - buttons **Regenerate image** (with an optional text box), **Upload my image** and **Choose from Media Library**.
6. Phase 2 calls generate automatically once after creating the draft.

**Done when:** every new draft has a generated 1080×1080 image shown in the preview; regenerate and upload both work; a 9:16 upload is rejected with a clear message.

### Phase 4: Edit and AI rewrite (1 day)
1. Everything in the studio is editable for a DRAFT and saved with `PUT /campaigns/{id}`. Show length counters: headline 40, text 125, description 30.
2. **"AI Polish Copy" becomes real:** `POST /campaigns/{id}/copy/improve` with body `{ "instruction": "make headline 1 shorter and mention free trial" }`. The AI changes only what's asked; the same validation and repair as Phase 2 applies.
3. The user picks which variant to publish (`selected_variant`). This first version publishes one ad; publishing all 3 can come later.
4. *(Optional)* Keep earlier versions and show a before/after diff, using `services/versions.py` from M2.

**Done when:** a manual edit and an AI rewrite both save, and an invalid edit (a 41-character headline) is blocked with the exact reason.

### Phase 5: Publish to Instagram, paused (2–3 days)
1. **`POST /campaigns/{id}/publish`** (DRAFT only) runs these steps in the background, saving each Meta id as it goes:

   | Step | Meta call | Built from |
   |---|---|---|
   | CAMPAIGN | `POST act_<id>/campaigns`, PAUSED, `special_ad_categories=[]`, `is_adset_budget_sharing_enabled=false` | objective |
   | ADSET | `POST act_<id>/adsets`, PAUSED | daily budget (paise), start/end, `targeting = {geo_locations, age_min, age_max, genders, flexible_spec:[{interests:[{id}]}], publisher_platforms:["instagram"], instagram_positions:["stream","explore"], targeting_automation:{advantage_audience:0}}`, optimization `LINK_CLICKS` (Traffic) or `REACH` (Awareness), billing `IMPRESSIONS` |
   | IMAGE | `POST act_<id>/adimages` with the image bytes from GridFS → `image_hash` | `image_id` |
   | CREATIVE | `POST act_<id>/adcreatives`, `object_story_spec {page_id, instagram_user_id, link_data {link, message, name, description, image_hash, call_to_action}}` | selected variant |
   | AD | `POST act_<id>/ads`, PAUSED, `{adset_id, creative:{creative_id}}` | — |

   The payload builders already exist in `app/meta/payloads.py`; the safety guard in `app/meta/sdk_gateway.py` already forces PAUSED.
2. **Never create duplicates:** name each object `acm-<id>-<STEP>`; before each create, look it up by name and reuse it if it exists. Retry only timeouts and rate limits (not "invalid parameter").
3. **On error:** stop, mark the step FAILED, and **show Meta's own error message** in the UI. Offer **Resume** (continue from the failed step) and **Discard** (delete what was created, children first, back to DRAFT).
4. **Frontend:**
   - a **Publish to Instagram (paused)** button with a confirm dialog showing the account, Page, @instagram, budget, dates, ad and image;
   - a progress list ✓/✗ per step, refreshed every 1.5 s;
   - the status badge becomes **PAUSED ON META** when done.
5. **Objectives:** support **Traffic** and **Awareness** first. **Leads** needs a lead form; **Sales** needs a Meta Pixel. Until then, block them with a clear message (or support them in a later phase).

**Done when:** in Ads Manager the campaign has **1 ad set (Instagram Feed + Explore only), 1 ad with the right image and text, all Off**, and a forced error shows Meta's message with working Resume and Discard.

### Phase 6: Activate, Pause, Resume, Delete on Meta (1 day)
1. **`POST /campaigns/{id}/activate`** (only from PUBLISHED_PAUSED, only if `ALLOW_REAL_AD_SPEND=true`, body `{confirm: true}`):
   - set the ad → ad set → **campaign last** to ACTIVE;
   - status ACTIVE (Meta shows "In review" first).
2. **`POST /campaigns/{id}/pause`:** campaign (and ads) → PAUSED; status PAUSED.
3. **`POST /campaigns/{id}/resume`:** back to ACTIVE (same spend check).
4. **`DELETE /campaigns/{id}`:** if published, delete on Meta first (ad → creative → ad set → campaign), then in the app.
5. Record every action in the audit log (who, when, before → after).
6. **Frontend:**
   - an **Activate** dialog with a spend warning ("up to ₹X per day until DATE"; checkbox "I understand this spends money");
   - **Pause** / **Resume** buttons on the campaign card;
   - Delete asks for confirmation.

**Done when:** Activate → Ads Manager "In review" / "Active"; Pause → "Off" within seconds; Delete leaves nothing in Ads Manager.

### Phase 7: Real performance numbers (1–2 days)
1. **A background job** (APScheduler, every `INSIGHTS_INTERVAL_HOURS`): for each ACTIVE or PAUSED campaign, read `GET <campaign_id>/insights?level=ad&time_increment=1` for the last 3 days and save one row per ad per day. Use an upsert, so running it twice never duplicates. Convert spend to paise without floats.
2. **Status job:** read each ad's `effective_status` (PENDING_REVIEW / ACTIVE / DISAPPROVED + reason) and show it on the card.
3. **Endpoints:** `GET /campaigns/{id}/insights` (daily rows + totals: impressions, reach, clicks, CTR, CPC, spend) and a **Refresh** button (`POST …/insights/refresh`, limited to once per 5 minutes).
4. **Frontend:** wire the **Insights & Analytics** screen and the campaign cards to these numbers. Remove the mock charts.

**Done when:** after a real ad has run, the numbers match Ads Manager (within Meta's normal delay).

### Phase 8: Media Library and audience apply (1 day)
1. **Media Library:** list `GET /media` (generated and uploaded images); the **Upload** button calls Phase 3's upload; **Use in campaign** sets `image_id` on a DRAFT.
2. **Audience & Targeting:** save named audiences (`POST /audiences`); **Apply to campaign** fills step 2 of the studio.

### Phase 9: Safety, limits and tests (1 day, then ongoing)
1. **Spend limits in `.env`:** `MAX_DAILY_BUDGET_INR` (e.g. 1000) and `MAX_CAMPAIGN_DAYS` (e.g. 7). The backend refuses anything above them.
2. **Make `SAFE_MODE_NO_SPEND` actually used:** when `true`, Activate and Resume are refused with a clear message.
3. **Special ad categories:** if the idea is about housing, jobs, credit or politics, warn and block for now; Meta requires special handling.
4. **Tests:**
   - unit tests for validation and payloads;
   - API tests for every endpoint (another user's campaign → 404);
   - fake-Meta tests for publish failures (timeout, invalid parameter, expired token);
   - one end-to-end test: idea → draft → image → edit → publish → activate → pause.

**Total:** roughly 12–15 working days for one developer.

---

## 6. `.env` and Meta setup for real ads

| Setting | Testing (no spend) | Real ads |
|---|---|---|
| `META_MODE` | `real` (or `fake` = offline) | `real` |
| `META_ACCESS_TOKEN` | current token | Long-lived or system-user token with `ads_management`, `ads_read`, `pages_show_list`, `instagram_basic`, `business_management` |
| `META_APP_ID` / `META_APP_SECRET` | same app | same app |
| `META_AD_ACCOUNT_ID` | any | **Business ad account with a payment method**, e.g. `act_29033614559610596` |
| `META_PAGE_ID` | Page linked to @synxait | same |
| `ALLOW_REAL_AD_SPEND` | `false` (everything forced PAUSED) | `true` |
| `SAFE_MODE_NO_SPEND` | `true` | `false` (enforced from Phase 9) |
| `MAX_DAILY_BUDGET_INR` (built; default `1000`) | `100` | your limit, e.g. `500` |
| `MAX_CAMPAIGN_DAYS` (built; default `30`) | `2` | e.g. `7` |
| `LLM_PROVIDER` / `LLM_PRIMARY_MODEL` | `gemini` / `gemini-2.5-flash` | same |
| `GEMINI_API_KEY` | set | set |
| `IMAGE_PROVIDER` / `IMAGE_MODEL` (built; default `fake` / `gemini-2.5-flash-image`) | `gemini` / `gemini-2.5-flash-image` | same |
| `SCRIPTED_SCENARIO` (offline, `LLM_PROVIDER=scripted`) | `ad_studio` (default: canned Python-course draft + rewrite) | not used |
| `MONGODB_URI` | `mongodb://localhost:27017/?replicaSet=rs0&directConnection=true` | same (or Atlas) |

Restart the backend after any change.

**In Meta (not in `.env`):**
1. In Business Manager, the ad account, the Facebook Page and the Instagram account belong to (or are shared with) the same business.
2. The ad account has a **payment method**.
3. The ad account **allows ad creatives**. In our M0 test, the personal account `act_2279071366267627` blocked creative creation.
4. The Meta app has Marketing API access, and the tester is an admin, developer or tester of the app.
5. Ads follow Meta's advertising policies (no "guaranteed" claims, no personal-attribute questions, no before/after body images).

---

## 7. The real-ad process (once Phases 0–6 are built)

```
Describe idea ─► AI draft (text + image) ─► Edit ─► Publish (paused) ─► Check Ads Manager ─► Activate ─► Meta review ─► Live ─► Pause
```

1. **Dashboard → AI Assistant:** type the idea → **Generate ad**.
2. **Review and edit** in the studio:
   - pick one of the 3 versions, fix the text, regenerate or upload the image;
   - check the audience and budget (small: ₹100/day, 1–2 days).
3. **Publish to Instagram (paused):** confirm. The progress list goes ✓ campaign ✓ ad set ✓ image ✓ creative ✓ ad. Status: **PAUSED ON META**. Nothing is spent.
4. **Check in Meta Ads Manager:** 1 ad set with Instagram placements only, and the ad preview shows your image and text.
5. **Activate:** confirm the spend warning. Meta shows "In review" (usually less than 24 h), then "Active".
6. **Where it appears:** in other people's Instagram **Feed and Explore** as **Sponsored**. It does **not** appear on @synxait's profile grid; ads never do. To see it yourself, use **Ads Manager → the ad → Preview → Instagram feed**.
7. **Pause** from the campaign card: Ads Manager shows "Off", and spending stops.
8. **Insights:** reach, clicks and spend appear after the next collection, or press **Refresh**.
9. Afterwards set `ALLOW_REAL_AD_SPEND=false` again.

---

## 8. Basic UI checks (run these first)

| # | Check | Steps | Expected | Works today? |
|---|---|---|---|---|
| 1 | Start-up | Start everything; open `:8000/health` and `:3000` | `{"status":"ok"}`, app loads | ✅ |
| 2 | Sign up / log out / log in | Sign Up `tester1@example.com` / `TestPass#2026` → Settings → Account → Sign Out → Log In | Dashboard both times; `acm.users` has the email with a hashed password | ✅ |
| 3 | Wrong input | Wrong password; password `abc`; same email again | Clear error each time | ✅ |
| 4 | Connect Meta | Meta Connection → Connect with My Meta Account → choose account + Page → Save Selection | Account, Page, @synxait and expiry shown; `meta_connections.token_ciphertext` is Binary | ✅ |
| 5 | Interest search | Studio step 2 → type `python` | Real Meta interests | ✅ |
| 6 | Create a campaign | Studio steps 1–4 → Create Campaign (PAUSED) | Campaign listed as PAUSED; Ads Manager shows an empty paused campaign `AdCraft - <title>` | ✅ (shell only) |
| 7 | Budget below minimum | Daily budget 40 | Rejected | ✅ (check the UI message) |
| 8 | Users separated | Sign up `tester2@example.com` | Doesn't see tester1's campaigns | ✅ |
| 9 | Delete | Delete the campaign | Gone from the app | ⚠️ stays on Meta until Phase 6 |
| 10 | Disconnect / reconnect | Disconnect → create a campaign → reconnect | Campaign saved without `meta_campaign_id` | ⚠️ no warning shown until Phase 5 |

---

## 9. Ten different ads to test (the full flow, after Phases 0–6)

Run each ad through these stages and record the result:

| Stage | What to do |
|---|---|
| **A. Describe** | Type the idea into the AI Assistant, then **Generate ad** |
| **B. Check the draft** | 3 variants within the limits, a sensible audience, real interest ids, an image |
| **C. Edit** | The change listed for that ad |
| **D. Publish (paused)** | Check Ads Manager: 1 ad set (Instagram only), 1 ad, everything Off |
| **E. Activate** (only ads 1 and 2, with real spend and a tiny budget) | "In review" → "Active" |
| **F. Pause** | "Off" in Ads Manager |
| **G. Delete** | Nothing left in Ads Manager |

Each ad also has an **edge case** that tests one rule.

### Ad 1: Online Python course (baseline happy path)
- **Idea:** "Promote my online Python course for college students in India. ₹999 for 8 weeks of live classes. Website https://synxa.ai/python"
- **Expect:** objective Traffic; ages ~18–24; India; interests like Python, Computer programming; CTA Learn More or Sign Up; image of a student coding on a laptop.
- **Edit:** change headline 1 to "Learn Python in 8 Weeks".
- **Edge case:** none. This is the reference run; do all stages A–G, **including Activate at ₹100/day for 1 day**.

### Ad 2: Local bakery in Hyderabad (city targeting, Awareness)
- **Idea:** "Make people in Hyderabad aware of my new bakery 'Sweet Crumbs' in Gachibowli. Fresh cakes and cookies."
- **Expect:** objective Awareness; **city Hyderabad** (a real Meta city key, not the whole country); ages 22–45; image of cakes in a bakery window.
- **Edit:** **Regenerate image** with "add a chocolate cake in front".
- **Edge case:** city targeting. Check the ad set in Ads Manager targets Hyderabad only. Do stages A–G **including Activate (₹100/day, 1 day)**.

### Ad 3: Fitness app download (banned claim)
- **Idea:** "Get downloads for my fitness app FitStreak. Guaranteed weight loss in 30 days!"
- **Expect:** CTA **Download**. The AI must **not** use "guaranteed"; validation removes or repairs it.
- **Edit:** try to type "100% results" into the headline by hand.
- **Edge case:** the manual edit is **blocked** with "contains banned claim '100%'". Publish only the clean version.

### Ad 4: Home loan / real estate (special ad category)
- **Idea:** "Promote our home loan offers at 8.5% interest in Bengaluru."
- **Expect:** the app **warns and blocks**: "Housing/credit ads need Meta's special ad category; not supported yet" (Phase 9).
- **Edge case:** nothing is created on Meta. If it isn't blocked, record this as a bug.

### Ad 5: SaaS free trial (3 variants + AI rewrite)
- **Idea:** "Free 14-day trial of ReviewBot, an AI code-review tool for software teams. https://reviewbot.example.com"
- **Expect:** 3 clearly different variants; interests like GitHub, Software development.
- **Edit:** **AI Polish Copy** with "make variant 2 about saving review time and mention the free trial". Only variant 2 changes. Pick variant 2 to publish.
- **Edge case:** the published ad uses variant 2's text (check the Ads Manager preview).

### Ad 6: Diwali clothing sale (Sales objective)
- **Idea:** "Diwali sale: 40% off ethnic wear at my online store https://example-store.in. Drive purchases."
- **Expect:** the AI picks Sales, but the app says "Sales needs a Meta Pixel; switching to Traffic" (or blocks), per Phase 5.
- **Edit:** accept Traffic; add the end date as the day after Diwali.
- **Edge case:** the end date is respected in the ad set schedule.

### Ad 7: Weekend workshop sign-ups (short schedule)
- **Idea:** "Get sign-ups for my free 2-day AI workshop this Saturday and Sunday in Chennai. Register at https://example.org/workshop"
- **Expect:** CTA **Sign Up**; Chennai; start and end dates only for the coming 2 days.
- **Edit:** change the budget to ₹50/day (the minimum).
- **Edge case:** ₹49/day is rejected; ₹50 is accepted. Dates in the past are rejected.

### Ad 8: Telugu-language restaurant ad (non-English text)
- **Idea:** "Write the ad in Telugu for my Andhra meals restaurant 'Ruchulu' in Vijayawada. Website https://example-ruchulu.in"
- **Expect:** headline and text in Telugu, still within the length limits (counted in characters); a South Indian thali image.
- **Edit:** change one word in the Telugu text by hand.
- **Edge case:** the Telugu text appears correctly in the Ads Manager preview (no broken characters).

### Ad 9: Blood donation drive (non-profit, tiny budget)
- **Idea:** "Spread awareness about our blood donation camp on 25 October at Osmania Hospital, Hyderabad."
- **Expect:** objective Awareness; no landing URL. The app asks for one or uses the Page link.
- **Edit:** **Upload my image**: first a **9:16 phone screenshot** (must be rejected with "use 1:1 or 4:5"), then a 1080×1080 photo (accepted).
- **Edge case:** the wrong image shape is rejected before anything reaches Meta.

### Ad 10: Mobile repair shop (own photo, missing details)
- **Idea:** "Ads for my phone repair shop."
- **Expect:** the AI asks or flags what's missing (city, website, budget) instead of guessing. The draft shows these as **missing** and Publish is disabled until they're filled.
- **Edit:** fill in "Secunderabad", `https://example-fixit.in` and ₹100/day; choose a photo from the **Media Library** (the one uploaded in Ad 9).
- **Edge case:** Publish stays disabled while required fields are empty, then works.

### Results sheet (copy for each ad)

| Ad | A Draft OK | B Image OK | C Edit OK | D Paused on Meta | E Active | F Paused | G Deleted | Notes / Meta error |
|---|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |  |  |
| … |  |  |  |  |  |  |  |  |

---

## 10. Platform limits and operational notes
 
1. **Business Ad Account required for real creatives**: Meta blocks creative creation on personal ad accounts (e.g. `act_2279071366267627`). Always use a verified Business ad account with a valid payment method.
2. **Instagram Account linking**: The Facebook Page must be linked to an Instagram Business or Creator account to enable Instagram Feed and Explore ad placement.
3. **Double-gated spend safety**: Real ad spend requires both `ALLOW_REAL_AD_SPEND=true` and `SAFE_MODE_NO_SPEND=false` in the backend configuration, plus an explicit user confirmation checkbox in the UI.
4. **Special Ad Categories**: Ads relating to credit, employment, housing, or social issues/politics require specialized Meta authorization and are intentionally blocked with `SPECIAL_AD_CATEGORY_UNSUPPORTED`.
5. **Objectives supported**: `TRAFFIC` and `AWARENESS` are fully supported. `LEADS` (which requires instant forms) and `SALES` (which requires Meta Pixel) are flagged as unsupported in this studio version.
6. **Rate limits**: Manual insights refresh is rate-limited to 1 request per 5 minutes per campaign (`429 RATE_LIMITED`) to protect against Meta Graph API throttling.
7. **MongoDB Replica Set**: PyMongo transactions require a replica set (`rs0`). Ensure Docker or local MongoDB is started with `--replSet rs0`.
