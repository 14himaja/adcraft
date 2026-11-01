# AdCraft: Implementation Plan & Phase Walkthrough
## Development Stages, Milestones & Engineering Journey

---

### 1. Overview of the 9 Suggested Stages + Bonus Milestones

The AdCraft application was engineered systematically following the 9 recommended stages in the internship evaluation brief, along with 3 bonus milestones that elevated the platform:

```
[ Stage 1: Research & Discovery ]
Platform Evaluation -> Meta Marketing API Spike -> Security & Harness Design

[ Stage 2: Engineering Foundation ]
FastAPI Backend -> MongoDB Setup -> Argon2id & JWT Auth -> Logging & Audit Trail

[ Stage 3: Agent Harness Core ]
Google ADK 2.x Integration -> State Machine -> Tools & Guards -> Repair Loop

[ Stage 4: Conversational Creation ]
Brief Extraction -> Clarifying Questions -> 3 Copy Variants -> 1:1 Creative Image

[ Stage 5: Human-in-the-Loop ]
AdCraft Studio Review -> Live Mobile Mockup -> Conversational Revision -> Hash Approval

[ Stage 6: Resilient Publishing ]
Checkpointed 7-Step Publisher -> Meta Object Hierarchy -> Idempotent Resume/Discard

[ Stage 7: Analytics Collection ]
Scheduled Insights Collection -> 5-min Throttling -> Daily Historical Storage -> Metrics

[ Stage 8: Performance & Optimization ]
Grounded AI Report -> CTR/CPC Diagnostic -> Typed Proposals -> Human Confirmation

[ Stage 9: Production Readiness ]
Automated Test Suites (779 Tests) -> Cloudflare Tunnels -> Deployment Guides

[ BONUS 10: Organic Publishing Suite ]
Instagram & Facebook Content Publishing API -> Zero Ad Spend Feed Posts & Stories

[ BONUS 11: Social Knowledge Engine & DM Agent ]
Post Understanding Agent -> Gemini 3072-dim Embeddings -> Hybrid RAG Customer Support

[ BONUS 12: Studio UX Overhaul ]
6-Section Persistent Sidebar -> In-Place Section Save -> Dirty Tracking -> Auto-Save
```

---

### 2. Detailed Phase-by-Phase Walkthrough

#### Stage 1 — Research & Discovery
- **Goal:** Identify the best social media advertising platform, understand its API capabilities, and establish the agent harness architecture.
- **Actions Taken:**
  - Researched Meta, LinkedIn, TikTok, X, Google Ads, and Pinterest across 6 weighted criteria.
  - Locked Meta Marketing API (Graph API v26.0) targeting Instagram and Facebook based on 4 mandatory gates.
  - Tested Meta sandbox account creation and Graph API payloads (`docs/pay_loads/`).
  - Established the core architectural thesis: *"The model proposes, the harness decides."*

---

#### Stage 2 — Engineering Foundation
- **Goal:** Set up the backend, database, authentication, multi-tenant workspace scoping, and audit infrastructure.
- **Actions Taken:**
  - Initialized FastAPI (Python 3.12) with Pydantic v2 settings.
  - Connected MongoDB 7.0 using Motor async driver; configured 23 compound indexes across 9 collections.
  - Implemented multi-user signup and login using **Argon2id** password hashing and `HttpOnly` JWT cookies.
  - Built AES-256-GCM authenticated encryption for all external access tokens.
  - Created append-only `audit_log` service and Structlog correlation ID middleware.

---

#### Stage 3 — Agent Harness Core
- **Goal:** Build the engineering harness that orchestrates and constrains the AI model.
- **Actions Taken:**
  - Integrated Google Agent Development Kit (ADK) 2.x with a LiteLLM adapter bridge.
  - Defined strict read-only tool schemas for Meta interest and location search.
  - Built state-dependent execution guards (`guards.py`) preventing agents from calling tools in invalid states.
  - Programmed the **Self-Repair Loop**: if an AI headline exceeds 40 characters, the harness catches the error and sends the prompt back with the exact character overage, achieving a 100% compliance rate.
  - Implemented 17 campaign state transitions (`app/domain/ad_states.py`).

---

#### Stage 4 — Conversational Campaign Creation
- **Goal:** Enable users to describe campaigns naturally and generate structured requirements and creative assets.
- **Actions Taken:**
  - Developed `AdDrafter` agent to extract product, budget, dates, and geography from conversational briefs.
  - Built missing information detection (`app/domain/requirements.py`) to generate clarifying questions.
  - Generated 3 ad copy variations tailored to the selected objective (`OUTCOME_TRAFFIC` or `OUTCOME_AWARENESS`).
  - Integrated AI image generation (Google Imagen, OpenAI DALL-E, Pollinations AI, and offline mock) normalized to 1080x1080 JPEG.

---

#### Stage 5 — Human-in-the-Loop & Approval Gates
- **Goal:** Empower the user to review, edit, and approve campaigns with strict safety guarantees.
- **Actions Taken:**
  - Built real-time mobile preview mockups simulating Instagram Feed and Stories in the browser.
  - Added conversational feedback support (`POST /campaigns/{id}/revise`), allowing users to ask for rewrites.
  - Created immutable version snapshots in `campaign_versions` and computed visual diffs.
  - Implemented **Cryptographic Hash Approval**: publishing requires a valid record matching `SHA256(canonical_campaign_json)`. Any post-approval edit immediately resets status to `IN_REVIEW`.

---

#### Stage 6 — Campaign Publishing Engine
- **Goal:** Safely create and activate campaign objects on Meta via the official API.
- **Actions Taken:**
  - Built a sequential, checkpointed 7-step publisher (`app/meta/publisher.py`):
    1. Verify approval hash
    2. Upload image to `act_{id}/adimages` -> save `image_hash`
    3. Create Meta Campaign (PAUSED) -> save `campaign_id`
    4. Create Meta Ad Set -> save `adset_id`
    5. Create Meta Ad Creative -> save `creative_id`
    6. Create Meta Ad (PAUSED) -> save `ad_id`
    7. Update status to `ACTIVE` (or remain `PAUSED` if spend switch off)
  - Engineered **Idempotent Resume**: if network drops at step 4, the user can click Resume, which skips steps 1–3 and continues without creating duplicate Meta objects.

---

#### Stage 7 — Analytics & Monitoring
- **Goal:** Periodically fetch delivery metrics, calculate KPIs, and store historical data.
- **Actions Taken:**
  - Integrated Meta's `act_{id}/insights` endpoint fetching impressions, clicks, spend, reach, and actions.
  - Computed calculated metrics: CTR ($\frac{\text{clicks}}{\text{impressions}} \times 100$), CPC ($\frac{\text{spend}}{\text{clicks}}$), and CPM.
  - Enforced a 5-minute cache per campaign to prevent hitting Meta rate limits (code 613).
  - Stored daily rows in `daily_insights` keyed by `(campaign_id, date)`.
  - Built an interactive analytics dashboard in Next.js with date-range filters (7d, 14d, 30d, all).

---

#### Stage 8 — Performance Analysis & Grounded Optimization
- **Goal:** Analyze campaign health and recommend actionable optimizations with human sign-off.
- **Actions Taken:**
  - Developed an AI performance diagnostic agent that evaluates CTR and CPC trends.
  - Implemented **Grounding Verification**: the harness cross-references every number in the AI report against raw metrics in the database, rejecting hallucinations.
  - Separated statements into **Fact, Calculation, Assumption, and Recommendation**.
  - Generated typed optimization proposals (`PAUSE_VARIANT`, `INCREASE_BUDGET`). Applying a proposal requires explicit user confirmation and logs an entry in `audit_log`.

---

#### Stage 9 — Production Readiness, Testing & Security
- **Goal:** Harden the system, eliminate security risks, and verify end-to-end reliability.
- **Actions Taken:**
  - Executed automated test suites: 144 frontend Vitest tests (100% pass) and 635 backend tests (98.8% overall pass rate).
  - Configured Cloudflare Tunnel / Dev Tunnels script (`scripts/start-real.ps1`) for HTTPS webhook delivery.
  - Verified Next.js 16 production build compiles with 0 errors across all 8 routes.
  - Wrote comprehensive documentation, setup guides, and 10 demonstration scenarios.

---

#### Bonus Stage 10 — Organic Social Publishing Suite
- **Why Built:** Evaluators and small businesses often want to test social marketing without spending real advertising money.
- **What Was Built:** Direct integration with Meta's Content Publishing API allowing users to post organic feed updates and stories to Facebook and Instagram with custom captions, AI hashtags, and GridFS images.

---

#### Bonus Stage 11 — Dynamic Social Knowledge Engine & Hybrid RAG DM Agent
- **Why Built:** When ads succeed, customers send Instagram DMs asking about prices, sizes, and offers. Human teams cannot respond instantly 24/7.
- **What Was Built:**
  - Automatic post ingestion upon publishing: captions and images are processed by `PostUnderstandingAgent`.
  - Structured extraction of products, prices, discounts, and offer validity.
  - Google `gemini-embedding-001` (3072-dimensional normalized vectors) indexed in MongoDB.
  - **Hybrid RAG Pipeline:** Resolves customer-shared Instagram URLs (`confidence=1.0`), platform post IDs, and semantic queries.
  - Automated DM agent answers customer questions accurately 24/7, respecting Meta's 24-hour messaging window, and escalates unknown offers to human owners (`NEEDS_HUMAN`).

---

#### Bonus Stage 12 — AdCraft Studio UX Overhaul
- **Why Built:** Linear step wizards frustrate users who want to jump directly between audience targeting, copy preview, and budget.
- **What Was Built:** A persistent 6-section sidebar navigation (Objective, Audience, Budget, Creative Preview, Hashtags, Publishing) with in-place section saving, dirty form tracking, and auto-save on exit.
