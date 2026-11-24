# Handoff: AdCraft "AI Ad Studio"

> From Praveen to Himaja · 15 Oct 2026 · Base: `main` @ `761b670`
> **What has been changed, what still needs to be done and how, and a ready-to-use prompt** for your AI coding
> tool (Antigravity / Claude / Cursor).
> The companion file **`docs/TEST-GUIDE-ai-ad-studio.md`** explains the execution flow and has the test
> scenarios with steps.

---

## 1. The goal

A user types one sentence, e.g. "Promote my Python course to college students in India", and the app:
1. **writes the ad:** 3 copy versions, audience with real Meta interest and city ids, budget, dates;
2. **creates the image;**
3. lets the user **edit** everything;
4. **publishes** it to Meta, everything **paused**: campaign → ad set → image → creative → ad;
5. lets the user **activate** it (real spend, behind two safety switches), then **pause / resume / delete** it;
6. shows **real performance numbers**.

All of this from the UI.

---

## 2. Status at a glance

| Part | Status |
|---|---|
| Review Agent adapted to this project (`.Agent/Review Agent`) | ✅ Done |
| Build spec (`docs/.claude/plans/07-ai-ad-studio.spec.md`) | ✅ Done |
| Backend: AI draft from an idea, AI image, upload, Media Library, edit, AI copy rewrite (Phases 0–4, 8) | ✅ Done and tested |
| Frontend: idea box, studio on saved drafts, publish dialog + progress UI, campaign cards with actions, real Insights / Media screens | ✅ Done and tested (expects the publish/activate endpoints below) |
| Backend: **publishing engine** (`app/meta/publisher.py`, `publish_checks.py`) | 🟡 Code done + 14 integration tests; **no HTTP endpoints yet** |
| Backend: **activate / pause / resume / delete-on-Meta** (`app/services/ad_lifecycle.py`) | 🟡 Code written, **no tests and no endpoints yet** |
| Backend: **insights** (Phase 7), **city search** endpoint, startup recovery hook, end-to-end test | ❌ Not started |
| Frontend follow-up: city search, 6 lint errors, dashboard numbers, studio stays open after publish | 🟡 Partly started (some new tests/edits exist; may be incomplete) |
| Final code review with the Review Agent + guide update | ❌ Not started |

**What you can test today in the UI:** sign up, connect Meta, **Describe your idea → Generate ad** (AI text + image), edit the draft, regenerate or upload an image, Media Library, AI rewrite, save, delete.
**What fails today:** the **Publish**, **Activate**, **Pause**, **Resume** and **Refresh insights** buttons. Their endpoints don't exist yet, so they return 404.

---

## 3. How to get and run these changes

The changes are **not committed or pushed**; they are in Praveen's working copy, on top of `main` @ `761b670`. Get them as either:
- **A patch:** Praveen runs `git diff > ai-ad-studio.patch` in the repo root and zips the untracked files (`git ls-files --others --exclude-standard`). You run `git apply ai-ad-studio.patch` on a clean `main` and unzip.
- **A branch,** if Praveen decides to commit later.

Then:
```powershell
# One time: stop the local Windows MongoDB service (Admin PowerShell), it takes port 27017
Stop-Service MongoDB; Set-Service MongoDB -StartupType Manual

docker compose up -d mongo                    # MongoDB replica set rs0
cd backend;  uv sync; uv run pytest -q        # backend tests
cd ..\frontend; npm install; npx vitest run   # frontend tests
```
Full run instructions: `docs/TEST-GUIDE-ai-ad-studio.md` §2.

---

## 4. Documents to read (in this order)

| File | What it is |
|---|---|
| `docs/.claude/plans/07-ai-ad-studio.spec.md` | **Source of truth:** data model §1, states §2, settings §3, validation §4, API §5, AI drafting §6, images §7, publishing §8, activate/pause §9, insights §10, frontend §11, implementation notes §12a |
| `docs/TEST-GUIDE-ai-ad-studio.md` | Execution flow + test scenarios with steps |
| `docs/project-status-and-user-guide.md` | Overall status, phases, `.env` for real ads, the real-ad process |
| `.Agent/Review Agent/PROJECT-FLOW.md` | Project context for an implementer or reviewer |
| `.Agent/Review Agent/references/adcraft-invariants.md` | **13 safety and quality rules** every change must satisfy |
| `.Agent/Review Agent/SKILL.md` | Code-review process ("Local review mode" = review uncommitted changes, no GitHub) |

---

## 5. What has been changed (file by file)

### 5.1 Review Agent: `.Agent/Review Agent/` ✅
It was copied from other projects (Smart Hospital, AI Gateway, Narad) and is now rewritten for AdCraft:
- `PROJECT-FLOW.md`;
- new `references/adcraft-invariants.md`;
- `references/architecture-patterns.md` and the security, performance, dependency and file-analysis references;
- the backend, frontend and ai-engineer sub-skills;
- `SKILL.md`, which gained a "Local review mode" section;
- `config.json`, where the websocket port moved 8000 → 8765 (the backend uses 8000).

Files that belonged only to the other projects were deleted.

### 5.2 Backend, Phase 0 (fix-ups) ✅
| File | Change |
|---|---|
| `app/config.py` | `LLM_PROVIDER` accepts `gemini`; added `gemini_api_key`, `openai_api_key`, `image_provider` (default `fake`), `image_model` (`gemini-2.5-flash-image`), `max_daily_budget_inr` (1000), `max_campaign_days` (30); `scripted_scenario` default `ad_studio` |
| `app/agents/models.py` | Gemini models sent as `gemini/<model>`, API key passed explicitly (values in `.env` are not in `os.environ`) |
| `app/api/meta_oauth.py`, `app/api/auth.py`, `app/main.py` | Lint fixes / formatting |
| `.env` (root) | Only fix: `MONGODB_URI=MONGODB_URI=…` → `MONGODB_URI=mongodb://localhost:27017/?replicaSet=rs0&directConnection=true` |

### 5.3 Backend, Phases 1–4 + Media ✅ (422 tests passed at completion, up from 341)
| File | Purpose |
|---|---|
| `app/domain/ad_states.py` (new) | Campaign states and allowed moves: DRAFT → PUBLISHING → PAUSED_ON_META ⇄ ACTIVE/PAUSED; PUBLISH_FAILED; COMPLETED |
| `app/domain/ad_campaign.py` (new) | Pure validation: copy rules, budget/date/age limits, special ad categories, `missing_fields`, money via `Decimal` |
| `app/services/ad_campaigns.py` (new) | Create DRAFT, get (owner only → 404 for others), edit DRAFT with a version check (409 on conflict), list, delete, serializer (old `READY_PAUSED` records show as DRAFT) |
| `app/services/ad_studio.py` (new) | Idea → AI draft → image; AI copy rewrite |
| `app/services/image_store.py` (new) | Images in MongoDB GridFS (bucket `images`): store, owner-only load, list; generate / upload / reuse for a campaign |
| `app/agents/ad_drafter.py` (new) | ADK agents `ad_drafter` and `copy_editor`. The user's text is treated as untrusted; copy is checked by code with up to 2 AI repairs; interest and city ids come from Meta search; budget, ages and duration are clamped by code |
| `app/agents/scenarios/ad_studio.json` (new) | Offline AI answers (a Python-course ad) for tests and offline demos |
| `app/media/images.py` (new) | `GeminiImageGenerator` (google-genai), `FakeImageGenerator` (Pillow), `normalize_square` → 1080×1080 JPEG |
| `app/api/campaigns.py` (rewritten) | Error envelope; `POST /campaigns` creates a DRAFT and **no longer calls Meta** |
| `app/api/media.py` (new) | Image routes, `GET /images/{id}`, `GET /media` |
| `app/container.py` | Image generator from `IMAGE_PROVIDER`; `spawn` for background jobs; `retry_wait` for tests |
| `app/domain/models.py` | `image_concept` optional |
| `pyproject.toml` / `uv.lock` | `python-multipart` declared (uploads) |
| Tests (new) | `tests/unit/test_ad_states.py`, `test_ad_campaign.py`, `test_image_generators.py`, `tests/agents/test_ad_drafter.py`, `tests/integration/test_ad_campaigns.py`, `tests/api/test_campaigns_api.py`, `test_images_api.py`, `test_ad_studio_api.py`, `campaign_bodies.py`; updated `conftest.py`, `test_config.py`, `test_container.py`, `test_scripted_model.py` |

**Working endpoints:**
- `POST /campaigns/draft`
- `POST /campaigns`, `GET /campaigns`, `GET /campaigns/{id}`, `PUT /campaigns/{id}`, `DELETE /campaigns/{id}` (app-only)
- `POST /campaigns/{id}/copy/improve`
- `POST /campaigns/{id}/image/generate`, `POST /campaigns/{id}/image`, `PUT /campaigns/{id}/image`
- `GET /images/{id}`, `GET /media`
- existing auth and `/meta/*` routes

### 5.4 Backend, Phase 5–6 work in progress 🟡
| File | State |
|---|---|
| `app/meta/publisher.py` (new) | `start_publish`, `run_publish`, `resume_publish`, `discard_publish`, `recover_interrupted`: steps CAMPAIGN → ADSET → IMAGE → CREATIVE → AD, checkpoints, adopt-by-name, safe retries, failure → PUBLISH_FAILED. **Tested** by `tests/integration/test_publisher.py` (14 tests) + `publish_helpers.py` |
| `app/meta/publish_checks.py` (new) | `check_publishable` (DRAFT_INCOMPLETE, special category, budget below Meta minimum, limits) and `verify_interests` (re-check interest ids with Meta) |
| `app/services/ad_lifecycle.py` (new) | `activate`, `pause`, `resume`, `delete_meta_objects`, `SpendBlocked`, `check_caps`, `require_spend_allowed`. **Not tested yet** |
| `app/meta/payloads.py`, `errors.py`, `sdk_gateway.py` + their unit tests | Small changes for publishing |

### 5.5 Frontend ✅ (50 Vitest tests passed at completion; build passed)
| File | Change |
|---|---|
| `lib/api.ts` | Typed function for every spec §5 endpoint; one `api()` wrapper showing the backend's error message |
| `components/AIAssistantCard.tsx` | **Describe your ad idea** box, example chips, **Generate ad** (loading state), **Start from scratch** |
| `components/CampaignStudioModal.tsx` | Edits a saved DRAFT (load by id, PUT on save / step change), missing-fields and warnings banners, Publish disabled with the reason |
| `components/StudioCreativeStep.tsx` (new) | Pick a version, 40/125/30 counters, CTA, Instagram preview, **Regenerate image**, **Upload my image**, **Choose from Media Library**, **AI rewrite** |
| `components/PublishFlow.tsx` (new) | Publish confirm dialog + live progress (polls every 1.5 s) + Resume / Discard |
| `components/CampaignCard.tsx` (new) | Status badge + actions per state (Edit, Publish, Activate with spend warning, Pause, Resume, Delete), insights, Refresh |
| `components/Dialog.tsx` (new) | Accessible dialog |
| `components/CampaignsView.tsx`, `RecentCampaigns.tsx`, `InsightsView.tsx`, `MediaView.tsx` | Real data, mocks removed |
| `app/page.tsx`, `TopHeader.tsx`, `SettingsModal.tsx`, `HeroBanner.tsx`, `Sidebar.tsx` | Wiring; hard-coded account id and @handle removed |
| `vitest.config.ts`, `test/mockApi.tsx` | Test timeout 15 s; shared test helper |
| Tests (new) | `AIAssistantCard`, `CampaignStudioModal`, `PublishFlow`, `CampaignCard`, `MediaView`, `InsightsView` |
| 🟡 Follow-up in progress | `AudienceView`, `MetaConnectCard`, `SettingsModal`, `lib/theme.tsx`, `CampaignPerformanceCard` + new `AudienceView.test.tsx`, `CampaignPerformanceCard.test.tsx`, `SettingsModal.test.tsx`, `lib/theme.test.tsx`: **may be incomplete** |

---

## 6. What still needs to be done, and how

Do these in order, **test first** each time: write the test, see it fail, implement, see it pass, run everything. Before starting, run all suites (§3) to see the real state. The work was stopped mid-way, so some tests may fail; fix those first.

### Step 1: Stabilise
1. Run the backend tests, `ruff check .`, `ruff format --check .`, `npx vitest run`, `npm run lint` and `npm run build`. Note every failure.
2. Finish or revert the half-done frontend follow-up (§5.5 🟡) until vitest and the build are green.

### Step 2: Test `app/services/ad_lifecycle.py`
New `tests/integration/test_ad_lifecycle.py`, with `FakeAdsGateway`:
- activate is refused with `SPEND_BLOCKED` under the default settings;
- activate works when `allow_real_ad_spend=True` and `safe_mode_no_spend=False`, updating ad → ad set → **campaign last**;
- pause is always allowed; resume does the same spend check;
- `delete_meta_objects` deletes children first, and "does not exist" (code 100) counts as deleted;
- only allowed states are accepted (409 `ILLEGAL_TRANSITION` otherwise).

### Step 3: HTTP endpoints for publish and lifecycle (spec §5, §8, §9)
In `app/api/campaigns.py`, or a new `app/api/publishing.py` if `campaigns.py` grows too long:

| Endpoint | Does |
|---|---|
| `POST /campaigns/{id}/publish` `{confirm: true}` | `check_publishable` + `verify_interests` + `start_publish`, then runs `run_publish` through `container.spawn`. Returns `{"status": "PUBLISHING"}` |
| `GET /campaigns/{id}/publish` | Returns the `publish` block directly (steps with `PENDING`, `DONE` or `FAILED`, plus the error) |
| `POST /campaigns/{id}/publish/resume` | `resume_publish` + spawn |
| `POST /campaigns/{id}/publish/discard` | `discard_publish` → DRAFT |
| `POST /campaigns/{id}/activate` `{confirm: true}` | `activate` (409 `SPEND_BLOCKED` unless allowed) |
| `POST /campaigns/{id}/pause` | `pause` |
| `POST /campaigns/{id}/resume` | `resume` |
| `DELETE /campaigns/{id}` | Now calls `delete_meta_objects` first, then deletes the document and its generated images |

- `confirm` must be `Literal[True]`; anything else returns 422.
- Every route loads the campaign as owner only (another user's campaign = 404).
- `can_publish` / `can_activate` in the campaign JSON reflect state and settings.
- In `app/main.py` lifespan: `await recover_interrupted(db, clock=container.clock)` on startup.
- API tests for each endpoint in `tests/api/test_publishing_api.py`, including another user = 404 and confirm missing = 422.

### Step 4: Insights (spec §10)
- Add `insights(meta_campaign_id, since, until)` and `ad_status(ad_id)` to `app/meta/ports.py` `AdsReader`, `FakeAdsGateway` (simulated numbers for ACTIVE/PAUSED objects, `is_simulated: true`) and `MetaSdkGateway` (`/<id>/insights?fields=impressions,reach,clicks,spend,ctr,cpc&time_range=…`, `/<ad_id>?fields=effective_status,ad_review_feedback`).
- Add both to the contract tests in `tests/contract/` for both gateways (mock the SDK with `responses`).
- New `app/services/insights.py`: `collect(campaign)` → `campaign.insights {impressions, reach, clicks, spend_minor (Decimal → paise), ctr (%), cpc_minor, updated_at}` + `meta.effective_status`.
- `GET /campaigns/{id}/insights`; `POST /campaigns/{id}/insights/refresh` (max 1 per 5 minutes, otherwise 429 `RATE_LIMITED`; returns the insights block).
- A background loop in the lifespan every `INSIGHTS_INTERVAL_HOURS` for ACTIVE/PAUSED campaigns. One failure must not stop the others. Past `end_date` → COMPLETED.
- `GET /meta/insights` sums the stored insights and **keeps its current response shape**.

### Step 5: City search
`GET /meta/locations?q=&country=IN` → `[{key, name, type, country_code}]` via `AdsReader.search_locations`. It requires a connection (409 `META_NOT_CONNECTED`). Then finish the frontend city chips in studio step 2.

### Step 6: Frontend follow-up
1. City search: chips, maximum 10, and a "Connect Meta to search cities" message.
2. `npm run lint` exits 0 (the 6 React-effect errors in `AudienceView`, `MetaConnectCard`, `SettingsModal`, `lib/theme.tsx`), with no behaviour change.
3. `CampaignPerformanceCard` shows real totals, with an empty state.
4. After publish or discard, the studio shows the result with **Done**, and the list refreshes.
5. No hard-coded demo values remain, except the example idea chips.

### Step 7: End-to-end test: `backend/tests/e2e/test_ad_studio_e2e.py`
Over HTTP, fakes only:
1. **Main path:**
   - register → direct-connect (fake) → `POST /campaigns/draft` → `PUT` edit → regenerate image → publish;
   - 5 steps DONE, status PAUSED_ON_META, the fake has exactly 1 campaign / ad set / creative / ad, all PAUSED, Instagram-only placement;
   - activate → 409 `SPEND_BLOCKED`;
   - with spend allowed: activate → ACTIVE → refresh insights → pause → resume → delete, leaving no objects in the fake.
2. **Failure cases:**
   - ADSET fails with code 100 → PUBLISH_FAILED with the message → resume → PAUSED_ON_META;
   - ADSET `timeout_after_create` → exactly 1 ad set;
   - discard → DRAFT with no objects left.

### Step 8: Review, then final checks
1. Run the Review Agent in **Local review mode** (`.Agent/Review Agent/SKILL.md`) over the whole working-tree diff plus untracked files.
   - Output: `.Agent/Review Agent/outputs/<date>/review_provisional.md`, `review.json` and `review.md`.
   - Fix every HIGH/FINAL finding, with a test.
2. All green: backend `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`; frontend `npx vitest run`, `npm run lint`, `npm run build`.
3. Run every scenario in `docs/TEST-GUIDE-ai-ad-studio.md` (offline first, then real Meta).
4. Update `docs/project-status-and-user-guide.md` (status table, UI navigation, `.env`, known limits) and spec §12a (any deviation).

---

## 7. Rules that must never be broken

- **No commit, push, stash, reset or checkout** without agreeing first. Never print or log secrets; don't change `.env` values.
- **Everything on Meta is created PAUSED.** Activate/resume only if `ALLOW_REAL_AD_SPEND=true` **and** `SAFE_MODE_NO_SPEND=false` **and** the request has `{"confirm": true}`.
- **The AI never gets the Meta writer;** it can't publish, activate or spend.
- **Ids for Meta writes** come only from the saved Meta connection; interest ids only from Meta search.
- **Tests never call real Meta, AI or image APIs** (`FakeAdsGateway`, `ScriptedModel`, `FakeImageGenerator`, `FixedClock`, inline `spawn`).
- **Money** is integer paise via `Decimal`. **Another user's campaign** = 404. **Error envelope:** `{"error": {code, message, details}}`. **Audit** every state change and Meta write.
- Files ≤ ~300 lines, functions ≤ ~60 lines; reuse existing modules (spec §0).

---

## 8. Ready-to-use prompt (paste into Antigravity / your AI coding tool)

````text
You are finishing the AdCraft "AI Ad Studio" in the repo
C:\Users\DELL\Desktop\AI TEAM\marketing agent\ad_campaign_manager
(FastAPI + PyMongo + Google ADK backend in backend/, Next.js frontend in frontend/,
MongoDB replica set rs0 via `docker compose up -d mongo`; run backend commands from backend/).

1) READ FIRST, in order, before changing anything:
   docs/HANDOFF-ai-ad-studio.md (what is done, what is left, how: follow its section 6 exactly)
   docs/.claude/plans/07-ai-ad-studio.spec.md (source of truth, incl. §12a)
   docs/TEST-GUIDE-ai-ad-studio.md (flow + test scenarios)
   .Agent/Review Agent/PROJECT-FLOW.md and .Agent/Review Agent/references/adcraft-invariants.md

2) CHECK THE REAL STATE: run `git status --porcelain` and all suites:
   backend: uv run pytest -q ; uv run ruff check . ; uv run ruff format --check .
   frontend: npx vitest run ; npm run lint ; npm run build
   List which items of HANDOFF section 6 are done, partial or missing. Don't redo finished work.
   Work was stopped mid-way, so fix any red tests first (HANDOFF step 1).

3) IMPLEMENT HANDOFF section 6, steps 2 → 7, in order, with strict TDD: write a failing test, run it, see it fail
   for the right reason, implement the minimum, see it pass, run the full suite. Use exactly the endpoint paths
   and JSON shapes in the spec (the frontend already calls them). Reuse existing modules; files ≤ ~300 lines,
   functions ≤ ~60 lines.

HARD RULES (never break):
- No git commit/push/stash/reset/checkout. Leave all changes in the working tree.
- Don't change .env values; never print secrets.
- Everything on Meta is created PAUSED. Activate/resume only if ALLOW_REAL_AD_SPEND=true AND
  SAFE_MODE_NO_SPEND=false AND {"confirm": true}; otherwise 409 SPEND_BLOCKED.
- AI agents never receive the Meta writer and cannot publish, activate or spend.
- Ids for Meta writes come from the saved connection; interest ids only from Meta search.
- Tests use fakes only (FakeAdsGateway with fail_at, ScriptedModel, FakeImageGenerator, FixedClock, inline spawn).
- Money in integer paise via Decimal; another user's campaign = 404; error envelope
  {"error":{code,message,details}}; audit every state change and Meta write.

4) REVIEW: run the Review Agent in Local review mode (.Agent/Review Agent/SKILL.md) over the whole
   working-tree diff + untracked files. Write review_provisional.md, review.json and review.md into
   .Agent/Review Agent/outputs/<today>/. Fix every HIGH/FINAL finding with a test. Re-run all suites until green.

5) MANUAL TEST: follow docs/TEST-GUIDE-ai-ad-studio.md: offline mode first (all scenarios),
   then the real-Meta scenarios marked "real". Record results in its results sheet. Fix what breaks.

6) DOCS: update docs/project-status-and-user-guide.md (status, UI navigation, .env, known limits),
   the "Status" column in docs/TEST-GUIDE-ai-ad-studio.md, and spec §12a with any deviation.

FINAL REPLY: files changed (one line each), backend and frontend test counts, lint/build results,
review findings fixed, scenario results, anything still open.
````
