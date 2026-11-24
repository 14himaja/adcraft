# AI Ad Studio — Build Specification (Phases 0–9)

> Source of truth for implementing the "describe idea → AI ad (copy + image) → edit → publish → activate/pause"
> flow on top of `main`. Every implementer (human or agent) follows this file. If code must differ, update this
> file in the same change. Status/user guide: `docs/project-status-and-user-guide.md`.

## 0. Ground rules

- **TDD**: write the failing test first, watch it fail, implement, watch it pass, run the whole suite.
- **No git commits, no pushes.** Leave all changes in the working tree.
- Backend: Python 3.12, `uv`, FastAPI, PyMongo async, Pydantic v2, google-adk 2.11, google-genai 2.29, Pillow.
  Run from `backend/`: `uv run pytest -q`, `uv run ruff check . && uv run ruff format --check .`.
  MongoDB for tests: Docker replica set `rs0` on `localhost:27017` (already running).
- Frontend: Next.js + TypeScript + Tailwind + SWR, tests with Vitest (`npx vitest run`), `npm run lint`, `npm run build`.
- **Reuse before writing**: `app/domain/models.py` (`AdVariantDraft`, `AssetDraft`, `AdVariant`, `finalize_assets`),
  `app/domain/validators.py` (`policy_violation`), `app/domain/media.py` (`check_instagram_image`),
  `app/domain/rules.py` (limits, CTA list, banned phrases, `OBJECTIVES`), `app/meta/payloads.py`,
  `app/meta/ports.py` (`AdsReader`/`AdsWriter`), `app/meta/fake.py` (`FakeAdsGateway`, `fail_at`),
  `app/meta/sdk_gateway.py` (forces PAUSED unless `ALLOW_REAL_AD_SPEND`), `app/meta/errors.py` (`MetaError`,
  `classify`, `is_retryable`), `app/agents/models.py` (`make_model`), `app/agents/scripted_model.py`,
  `app/agents/nodes.py` (repair helpers), `app/audit.py` (`record`), `app/clock.py`, `app/errors.py` (`AppError`).
- Every external effect (Meta write, AI call) is behind an interface with a fake used by tests and by
  "offline mode" (`META_MODE=fake`, `LLM_PROVIDER=scripted`, `IMAGE_PROVIDER=fake`).
- Never trust ids from the browser for Meta writes: account/page/instagram ids come from the user's saved
  Meta connection; interest ids must come from Meta interest search.
- Error envelope everywhere: `{"error": {"code", "message", "details"}}` via `AppError` subclasses.
  (Existing `HTTPException` uses in `api/campaigns.py` are replaced by `AppError` subclasses.)
- Every state change and every Meta write is audited (`audit.record`).
- Files ≤ ~300 lines, functions ≤ ~60 lines, one responsibility per module.

## 1. Campaign document (collection `campaigns`)

```jsonc
{
  "_id": ObjectId, "user_id": ObjectId, "schema_version": 2,
  "status": "DRAFT",                       // see §2
  "idea": "Promote my Python course ...",  // what the user typed (may be "")
  "title": "Python Course Launch",
  "objective": "TRAFFIC",                  // TRAFFIC | AWARENESS (LEADS/SALES rejected with OBJECTIVE_UNSUPPORTED)
  "landing_url": "https://synxa.ai/python",
  "audience": {
    "countries": ["IN"],
    "cities": [{"key": "1017930", "name": "Bangalore"}],      // keys from Meta location search
    "age_min": 18, "age_max": 24,
    "genders": "ALL",                                        // ALL | MEN | WOMEN
    "interests": [{"id": "6003682002118", "name": "Python (programming language)"}]
  },
  "daily_budget_minor": 10000,             // paise; API accepts/returns rupees as daily_budget (float)
  "currency": "INR",
  "start_date": "2026-10-20", "end_date": "2026-10-22",       // ISO dates
  "variants": [{"headline", "primary_text", "description", "call_to_action"}],   // 1–3, validated
  "selected_variant": 0,
  "image_prompt": "Square photo of a student coding ...",
  "image_id": "ObjectId hex in GridFS bucket 'images'" | null,
  "missing_fields": ["landing_url"],       // computed on save, see §4
  "warnings": ["..."],                     // non-blocking notes from the AI/validation
  "meta": {"campaign_id", "adset_id", "image_hash", "creative_id", "ad_id", "effective_status"},
  "publish": {"status": "RUNNING|FAILED|DONE", "steps": [{"name","status","meta_object_id","attempts","last_error"}],
              "error": {"step","message","meta_code"} | null},
  "insights": {"impressions", "reach", "clicks", "spend_minor", "ctr", "cpc_minor", "updated_at"} | null,
  "rev": 0, "created_at", "updated_at"
}
```

Legacy documents created by the old studio (`status: READY_PAUSED`, flat `daily_budget`, `creative`, `audience.interests`
as names) must still list and delete without errors: the serializer maps them to `status: "DRAFT"` and best-effort fields.

## 2. States (`app/domain/ad_states.py`)

```
DRAFT ──publish──► PUBLISHING ──ok──► PAUSED_ON_META ──activate──► ACTIVE ──pause──► PAUSED ──resume──► ACTIVE
                        │                                           │                      │
                        └──error──► PUBLISH_FAILED ──resume──► PUBLISHING                  └──(end date passed)──► COMPLETED
                                         └──discard──► DRAFT
any state ──delete──► (document removed after Meta objects deleted)
```
Editing (`PUT`, image, copy rewrite) only in `DRAFT`. Conditional updates on `{_id, status, rev}`; mismatch → 409
`CONCURRENT_MODIFICATION`; illegal move → 409 `ILLEGAL_TRANSITION`.

## 3. Settings added to `app/config.py` (+ documented in the user guide)

| Setting | Default | Meaning |
|---|---|---|
| `IMAGE_PROVIDER` | `fake` | `gemini` or `fake` |
| `IMAGE_MODEL` | `gemini-2.5-flash-image` | Gemini image model (check current name in AI Studio) |
| `MAX_DAILY_BUDGET_INR` | `1000` | hard cap on daily budget |
| `MAX_CAMPAIGN_DAYS` | `30` | hard cap on end − start |
| `SAFE_MODE_NO_SPEND` | `true` (exists) | when true, activate/resume are refused (`SPEND_BLOCKED`) |
| `ALLOW_REAL_AD_SPEND` | `false` (exists) | must also be true for activate/resume |
| `INSIGHTS_INTERVAL_HOURS` | `6` (exists) | background insights refresh |

`LLM_PROVIDER` already accepts `gemini` (Phase 0 fix). `GEMINI_API_KEY` is used for both text and images.

## 4. Validation (pure, `app/domain/ad_campaign.py`)

- Copy: reuse `AdVariant`/`finalize_assets` rules (headline ≤ 40, primary_text ≤ 125, description ≤ 30, CTA in
  `CTA_ALLOWED`, banned phrases, no "are you …?"). Accept 1–3 variants for user edits.
- `landing_url` https only; `daily_budget` ≥ 50 and ≤ `MAX_DAILY_BUDGET_INR`; dates: start ≥ today,
  end > start, end − start ≤ `MAX_CAMPAIGN_DAYS`; ages 18–65, min ≤ max; at least one country or city.
- **Special ad categories** (housing, home loan, mortgage, credit card, loan, insurance, job, hiring, vacancy,
  election, political, vote): `special_category_reason(text) -> str | None`; publishing is refused with
  `SPECIAL_AD_CATEGORY_UNSUPPORTED` and the draft carries a warning.
- `missing_fields(campaign) -> list[str]`: required to publish = title, objective, landing_url, audience location,
  daily_budget, start_date, end_date, ≥1 valid variant, image_id. Publish is refused (`DRAFT_INCOMPLETE`) while
  any is missing. Names returned (in this order): `title, objective, landing_url, audience, daily_budget,
  start_date, end_date, variants, image_id`.
- Field errors → 422 `VALIDATION_FAILED`, `message` = all problems joined by "; ", `details.problems` = list of
  `"<field>: <reason>"` strings (e.g. `"variants.0.headline: String should have at most 40 characters"`).
  Only the fields sent in the request are checked (plus the cross-field rules they take part in), so an old
  start date does not block editing the title. Pydantic type errors keep the existing `details.errors` shape.
- `to_minor(rupees: float) -> int` via `Decimal`, never float math for money.

## 5. API (all under the existing `/campaigns` and `/meta` routers; frontend calls them via `/api/v1/...`)

| Method & path | Body → Response | Phase |
|---|---|---|
| `POST /campaigns/draft` | `{idea}` → campaign (DRAFT, AI-filled, image generated) | 2, 3 |
| `POST /campaigns` | manual campaign fields → campaign (DRAFT; **no Meta call any more**) | 1 |
| `GET /campaigns` · `GET /campaigns/{id}` | → list / campaign | 1 |
| `PUT /campaigns/{id}` | partial fields (title, objective, landing_url, audience, daily_budget, dates, variants, selected_variant) → campaign | 1, 4 |
| `POST /campaigns/{id}/copy/improve` | `{instruction}` → campaign (variants rewritten by AI, validated) | 4 |
| `POST /campaigns/{id}/image/generate` | `{prompt?}` → campaign (new image_id) | 3 |
| `POST /campaigns/{id}/image` | multipart `file` → campaign | 3 |
| `PUT /campaigns/{id}/image` | `{image_id}` (from Media Library) → campaign | 8 |
| `GET /images/{image_id}` | → image bytes (owner only) | 3 |
| `GET /media` | → `[{id, filename, source: generated|uploaded, prompt, created_at}]` | 8 |
| `POST /campaigns/{id}/publish` | `{confirm: true}` → `{status: "PUBLISHING"}` (background job) | 5 |
| `GET /campaigns/{id}/publish` | → publish block (steps, error) | 5 |
| `POST /campaigns/{id}/publish/resume` · `/publish/discard` | → status | 5 |
| `POST /campaigns/{id}/activate` | `{confirm: true}` → campaign (ACTIVE) | 6 |
| `POST /campaigns/{id}/pause` · `/resume` | → campaign | 6 |
| `DELETE /campaigns/{id}` | → `{status: "DELETED"}` (Meta objects deleted first, children first) | 6 |
| `GET /campaigns/{id}/insights` · `POST …/insights/refresh` | → insights block (refresh max 1 / 5 min) | 7 |
| `GET /meta/insights` (exists) | → account totals from stored insights | 7 |

Campaign JSON returned to the browser = §1 minus `user_id`, with `id`, `daily_budget` (rupees), `image_url`
(`/api/v1/images/<id>` or null), `missing_fields`, `warnings`, `can_publish`, `can_activate` (false when safe mode).

## 6. AI drafting (Phase 2, `app/agents/ad_drafter.py`)

- One ADK `Agent` (`name="ad_drafter"`, model from `make_model`) with `output_schema=AdDraftOutput`:
  `title, objective (TRAFFIC|AWARENESS), landing_url ("" if unknown), countries[], city_names[], age_min, age_max,
  genders, interest_keywords[2–5], daily_budget_inr, duration_days, variants[3] (headline, primary_text, description,
  call_to_action), image_prompt, missing_info[], warnings[]`.
- The user's idea is wrapped as untrusted data; the instruction lists the limits from `rules.py` and says the agent
  cannot publish, activate or spend.
- Code validates variants with `finalize_assets`; on errors it re-asks with the exact errors (max 2 repairs, reuse
  `repair_message`). Still invalid → keep valid variants, add a warning.
- Code resolves `interest_keywords` with `reader.search_interests` (keep only ids Meta returned, max 5) and
  `city_names` with `reader.search_locations(name, country)`.
- Dates: start = tomorrow (clock), end = start + duration_days (capped by `MAX_CAMPAIGN_DAYS`).
- Then Phase 3 image generation runs with `image_prompt`. If image generation fails, the draft is still saved with a
  warning and `image_id` missing.
- Copy rewrite (Phase 4, `improve_copy`): same agent pattern (`name="copy_editor"`), input = current variants +
  instruction (wrapped), output `AssetDraft`, same validation/repair.
- Tests use `ScriptedModel` scenarios (no network). Offline mode scenario file: `app/agents/scenarios/ad_studio.json`.

## 7. Images (Phase 3, `app/media/`)

- `ImageGenerator` protocol: `async generate(prompt: str) -> bytes`.
  `GeminiImageGenerator` (google-genai `Client(api_key=...).aio.models.generate_content(model=IMAGE_MODEL, contents=prompt)`,
  take the first `inline_data` image part) and `FakeImageGenerator` (Pillow 1080×1080 coloured square with the prompt's
  first words, deterministic). Container picks by `IMAGE_PROVIDER`.
- `normalize_square(data) -> bytes`: centre-crop to 1:1, resize 1080×1080, JPEG quality 90; then `check_instagram_image`.
- Uploads: `check_instagram_image` on the raw upload (reject 9:16 with the existing message), then store as uploaded
  (no crop; 4:5 and 1.91:1 allowed).
- GridFS bucket `images`, metadata `{user_id, campaign_id, source, prompt, content_type}`.
- Prompt sent to the model: `image_prompt + extra + " Square 1:1 Instagram feed ad photo, no text, no logos, high quality."`

## 8. Publishing (Phase 5, `app/meta/publisher.py`)

Steps (each checkpointed in `campaign.publish.steps`, object name `acm-<last6 of id>-<STEP>`, adopt-by-name before each
create, retry only `is_retryable` errors with tenacity (3 attempts), never retry INVALID/AUTH/PERMISSION):

1. `CAMPAIGN` → `campaign_payload` (objective from `OBJECTIVES`)
2. `ADSET` → daily budget (`daily_budget` minor units), `start_time`/`end_time`, targeting
   `{geo_locations: {countries|cities}, age_min, age_max, genders ([1]=men,[2]=women, omit for all),
   flexible_spec: [{interests: [{id}]}], publisher_platforms: ["instagram"], instagram_positions: ["stream","explore"],
   targeting_automation: {advantage_audience: 0}}`, optimization LINK_CLICKS/REACH, billing IMPRESSIONS,
   bid LOWEST_COST_WITHOUT_CAP, PAUSED. Budget below the account's `min_daily_budget_minor` → `BUDGET_BELOW_META_MINIMUM` before any call.
3. `IMAGE` → `upload_image` (bytes from GridFS) → `image_hash`
4. `CREATIVE` → `creative_payload` with the selected variant, page id + instagram id from the saved Meta connection
5. `AD` → `ad_payload`, PAUSED

Failure → step FAILED, `publish.error` = Meta's user message, campaign `PUBLISH_FAILED`, code 190 marks the connection
expired. Resume continues from the first unfinished step. Discard deletes created objects children-first, back to DRAFT.
A background job (injected `spawn`, inline in tests) runs the steps; startup marks stuck `PUBLISHING` as `PUBLISH_FAILED`.

## 9. Activate / pause / resume / delete (Phase 6)

- Activate: `PAUSED_ON_META` only; refused with `SPEND_BLOCKED` unless `ALLOW_REAL_AD_SPEND=true` **and**
  `SAFE_MODE_NO_SPEND=false`; `{confirm: true}` required; updates ad → adset → campaign (campaign last) to ACTIVE.
- Pause: ACTIVE → PAUSED (campaign to PAUSED on Meta; always allowed). Resume: PAUSED → ACTIVE (same spend check).
- Delete: if any Meta ids exist, delete ad → creative → adset → campaign (code 100 "does not exist" counts as deleted),
  then remove the document and its generated images.

## 10. Insights (Phase 7)

- `AdsReader.insights(campaign_id, since, until) -> list[dict]` and `ad_status(ad_id) -> dict` on both gateways
  (fake returns deterministic simulated numbers for ACTIVE/PAUSED objects, flagged `is_simulated`).
- `collect(campaign)` sums the window into `campaign.insights` (spend via `Decimal` → minor units).
- Background loop in the app lifespan every `INSIGHTS_INTERVAL_HOURS`; manual refresh endpoint rate-limited 1 / 5 min.

## 11. Frontend (Phases 2–8)

- Dashboard / AI Assistant: textarea "Describe your ad idea" + example chips + **Generate ad** → `POST /campaigns/draft`
  (loading state "Writing your ad and creating the image…", ~20 s) → opens the studio with the draft.
- Studio edits a saved DRAFT (`PUT` on Save / step change); step 4 shows the 3 variants (pick one), counters
  40/125/30, **Regenerate image** (+ optional text), **Upload my image**, **Choose from Media Library**,
  **AI rewrite** box (`POST …/copy/improve`), missing-fields banner, warnings.
- Buttons: **Save draft**, **Publish to Instagram (paused)** (confirm dialog listing account, Page, @instagram,
  budget, dates, image, text) → progress list polling `GET …/publish` every 1.5 s, Resume / Discard on failure.
- Campaign cards: status badge, **Activate** (spend warning + checkbox; disabled with tooltip when `can_activate`
  is false), **Pause**, **Resume**, **Delete** (confirm), insights numbers, **Refresh**.
- Insights & Analytics and Media Library use the real endpoints (no mock data left).
- Component tests with Vitest + Testing Library for every new component.

## 12a. Implementation notes (backend Phases 0–9, as built)

- Modules: `domain/ad_states.py`, `domain/ad_campaign.py`, `services/ad_campaigns.py` (CRUD + serializer),
  `services/ad_studio.py` (draft + improve orchestration), `services/image_store.py` (GridFS + attach),
  `agents/ad_drafter.py`, `media/images.py`, `meta/publisher.py`, `meta/publish_checks.py`,
  `services/ad_lifecycle.py`, `services/insights.py`, `api/campaigns.py`, `api/media.py`, `api/meta_oauth.py`.
- Error codes: image model failure 502 `IMAGE_GENERATION_FAILED`; rejected upload 422 `IMAGE_REJECTED` (message from
  `check_instagram_image`); copy rewrite still invalid after 2 repairs → 422 `AI_OUTPUT_INVALID` and the variants are
  left unchanged; draft output unusable → 422 `AI_OUTPUT_INVALID`; spend blocked → 409 `SPEND_BLOCKED`;
  rate limited insights refresh → 429 `RATE_LIMITED`.
- `AdVariantDraft.image_concept` is now optional (default `""`); stored variants carry only the 4 spec keys.
- Drafter: a city resolved in country X removes X from `countries` (Meta rejects overlapping locations); no location
  at all → `["IN"]` with a warning; without a Meta connection interests/cities are skipped with a warning;
  `missing_info` items become warnings "Please add: …". Budget/ages/duration are clamped by code.
- Legacy docs serialize as `DRAFT` but their stored status is not `DRAFT`, so `PUT`/image/copy edits return 409.
- Interest ids sent by the browser in `PUT` are stored as given; the Phase 5 publisher re-verifies them before creating ad sets.
- `SCRIPTED_SCENARIO` default is `ad_studio`. Each request builds a fresh `ScriptedModel`, so the offline demo can draft repeatedly.
- `DELETE /campaigns/{id}` calls `delete_meta_objects` children first (ad → creative → ad set → campaign, with code 100 treated as already deleted), deletes generated images from GridFS bucket `images`, and removes the document with full audit trail.
- Interrupted `PUBLISHING` jobs are recovered on server startup by `publisher.recover_interrupted`, marked as `PUBLISH_FAILED` with resume capability.
- Insights background loop in `main.py` refreshes all ACTIVE/PAUSED campaigns periodically according to `INSIGHTS_INTERVAL_HOURS`.

## 12. Definition of done

- `uv run pytest -q` green, Ruff clean, `npx vitest run` green, `npm run lint` and `npm run build` succeed.
- Offline end-to-end test (fake Meta, scripted LLM, fake images): idea → draft → edit → regenerate image → publish →
  PAUSED_ON_META → (allow spend) activate → pause → resume → delete, all over HTTP.
- `docs/project-status-and-user-guide.md` updated to the new reality.
- Review Agent (`.Agent/Review Agent`) run over the whole diff; all HIGH/FINAL findings fixed.
