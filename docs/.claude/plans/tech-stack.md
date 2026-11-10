# Tech Stack — Ad Campaign Manager

> Document 5 · Last updated: 6 Oct 2026 · Related: HLD (Doc 2), LLD, Implementation Roadmap
> Decisions locked: **Instagram** placements via the Meta Marketing API · **Google ADK 2.x** as the agent framework · **MongoDB** as the database.

## 0. Principles

1. **Reuse before writing.** If a maintained library or the platform's official SDK does it, we use it and keep only a thin adapter of our own (§2).
2. **Small, single-purpose modules** (Single Responsibility). One module = one reason to change.
3. **Depend on interfaces at the edges** (Dependency Inversion). Meta and the LLM sit behind small interfaces, so a fake can replace each in tests and in the offline demo.
4. **Narrow interfaces** (Interface Segregation). Agent tools get a *read-only* ads interface; only the publisher gets the write interface.
5. **Interchangeable implementations** (Liskov). The real and fake Meta gateways must pass the **same contract test suite**.
6. **Extend by adding, not editing** (Open/Closed). New agents, tools and proposal types are registered in tables; the workflow core doesn't change.
7. **Pinned versions.** Fast-moving libraries (ADK, LiteLLM, the Meta SDK) are pinned in `uv.lock`; upgrades are separate commits with a green test suite.

## 1. Summary

| Layer | Choice |
|---|---|
| Backend language | Python 3.12 |
| Web framework | FastAPI + Uvicorn |
| Validation / models | Pydantic v2, pydantic-settings |
| **Agent framework** | **Google ADK 2.x** (`google-adk`, pinned): `Workflow` graph, `Agent`, function nodes, callbacks, `AgentEvaluator` |
| Model access | ADK `LiteLlm` wrapper → OpenAI models (`openai/<model>` from config); `ScriptedModel` (our `BaseLlm` subclass) for tests and the offline demo |
| **Meta / Instagram API** | **Official `facebook-business` SDK 26.x** (matches Graph API v26.0) behind our `AdsReader` / `AdsWriter` interfaces |
| Retries / backoff | tenacity |
| Database | MongoDB 8.0 (local: Docker single-node replica set; deployed: MongoDB Atlas) |
| DB driver | PyMongo ≥ 4.13 async API (`AsyncMongoClient`); GridFS for ad images |
| Image checks | Pillow (dimensions and format for Instagram rules) |
| Scheduling | APScheduler 3.x (`AsyncIOScheduler`), in-process |
| Auth | argon2-cffi (passwords), PyJWT (session cookie), httpx (two OAuth token-exchange calls) |
| Token encryption | `cryptography` (AES-256-GCM) |
| Logging | structlog (JSON) + MongoDB `audit_log` |
| Frontend | Next.js (App Router) + React + TypeScript, Tailwind CSS, SWR, Recharts |
| Backend tests | pytest, pytest-asyncio, httpx `ASGITransport`, `responses` (SDK HTTP mocking in gateway contract tests), respx (OAuth calls) |
| Frontend tests | Vitest + React Testing Library; Playwright end to end |
| Lint / format | Ruff; ESLint + Prettier |
| Package managers | uv, npm |
| Runtimes | Python 3.12, Node.js 24 LTS |
| CI / deploy | GitHub Actions; backend on Render (Docker, always-on), frontend on Vercel, DB on Atlas |
| Secret scanning | gitleaks |

## 2. Reuse Map — What We Don't Build

| Need | We reuse | We write only |
|---|---|---|
| Agent loop, tool calling, structured output, sessions, callbacks | Google ADK | Agent definitions, instructions, the per-turn `Workflow`, two callbacks |
| Model provider access, retries on 429/5xx | LiteLLM (via ADK `LiteLlm`) | Model config |
| Graph API calls, `appsecret_proof`, paging, error objects | `facebook-business` SDK | `MetaSdkGateway` (~150 lines): maps SDK calls/errors to our interface |
| Backoff and retry policies | tenacity | Which errors are retryable (a table) |
| Request/response validation, settings | Pydantic, pydantic-settings | Domain models |
| Password hashing, JWT, encryption | argon2-cffi, PyJWT, cryptography | 3 small wrapper modules |
| Scheduling | APScheduler | Job functions |
| Agent evaluation | ADK `AgentEvaluator` / `adk eval` | Eval sets |
| Image inspection | Pillow | One `check_instagram_image()` function |
| Stats | Python stdlib (`math.erf`) | One z-test function |

We **do** write ourselves (because it is the product, and it is what the evaluation grades): the campaign state table, approvals, publish checkpointing, validation rules, grounding and policy checks.

## 3. Backend Choices and Rejected Alternatives

| Need | Choice | Why | Rejected |
|---|---|---|---|
| Agent framework | Google ADK 2.x | Future multi-agent growth (sub-agents, A2A), graph workflows, tool-guard callbacks, built-in eval and dev UI | LangGraph (strong fit, but the team chose ADK for future agents), LangChain (model-led loop), custom loop |
| Model wrapper | ADK `LiteLlm` (`openai/<model>`) | ADK Python reaches OpenAI through LiteLLM; one switch to change providers | Direct OpenAI SDK (bypasses ADK) |
| Meta client | `facebook-business` SDK | Official, versioned with the API (26.x for v26.0), handles `appsecret_proof` and paging | Hand-written httpx client (more code to maintain) |
| SDK is synchronous | `asyncio.to_thread()` inside the gateway | Keeps FastAPI's event loop free; one place | Rewriting async HTTP ourselves |
| Retries | tenacity | Declarative, tested library | Hand-written backoff loops |
| DB driver | PyMongo async | Official; Motor is deprecated | Motor, ODMs |
| ADK sessions | `InMemorySessionService`, one per chat turn | MongoDB already holds all durable state; no custom session service to maintain | Custom MongoDB `BaseSessionService` (add later only if long-lived paused runs are needed) |
| Image storage | GridFS | Same database, no extra service | S3 / Cloudinary |
| Scheduler | APScheduler (in-process) | A handful of periodic jobs | Celery + Redis |
| Rate limiting | ~15-line in-process limiter | Single instance | slowapi |

## 4. Frontend

| Need | Choice | Why |
|---|---|---|
| Framework | Next.js App Router + TypeScript | `/api/*` rewrites to the backend keep the session cookie first-party; Vercel deploy |
| Styling | Tailwind CSS | Consistent tokens without a component library |
| Data | SWR | Caching + polling (publish progress) |
| Charts | Recharts | Daily per-ad metrics |
| Diff | Backend `GET /diff` | One tested implementation |

## 5. Testing Stack (TDD)

| Level | Tool | Covers |
|---|---|---|
| Unit | pytest | Domain rules, requirements, state table, hashing, diff, metrics, grounding, policy, image checks |
| Integration | pytest + real MongoDB (per-test database) | Conditional transitions, transactions, unique indexes, upserts, audit |
| Agent | pytest + ADK `InMemoryRunner` + **`ScriptedModel`** | Each workflow: routing, validate→repair loop, tool guard, structured outputs — no network |
| Contract | One shared test suite run against **`FakeAdsGateway`** and **`MetaSdkGateway`** (SDK HTTP mocked with `responses` using the saved Milestone 0 payloads) | The fake behaves like the real gateway (Liskov) |
| API | httpx `ASGITransport` | Endpoints, auth, ownership, error envelopes |
| **Full process (mocked)** | `tests/e2e/test_full_lifecycle.py` with `ScriptedModel` + `FakeAdsGateway` + a controllable clock | Brief → questions → plan → variants → feedback → approve → publish → activate → insights → report → proposal → apply, end to end, offline |
| Frontend | Vitest + Testing Library | Approval dialog, SIMULATED badge, report labels |
| Browser E2E | Playwright, app in **mock mode** | The four demo scenarios |
| Live model eval | ADK `AgentEvaluator` / `evals/run_live_eval.py` | Real models on the 20-brief set (Doc 3 §6) |

**Mock mode** (`META_MODE=fake`, `LLM_PROVIDER=scripted`) runs the *whole application* offline with the same code paths. It is used for Playwright, the demo video's failure scenarios and local development without Meta credentials. It is refused when `APP_ENV=production`.

## 6. Dependencies

**Backend (`backend/pyproject.toml`)** — versions pinned in `uv.lock`

- Runtime: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `google-adk` (2.x), `litellm`, `facebook-business` (26.x), `tenacity`, `pymongo>=4.13`, `httpx`, `apscheduler>=3.10,<4`, `argon2-cffi`, `pyjwt`, `cryptography`, `structlog`, `pillow`, `python-multipart`
- Dev: `pytest`, `pytest-asyncio`, `responses`, `respx`, `ruff`

**Frontend (`frontend/package.json`)**

- Runtime: `next`, `react`, `react-dom`, `swr`, `recharts`
- Dev: `typescript`, `tailwindcss`, `eslint`, `prettier`, `vitest`, `@testing-library/react`, `@testing-library/user-event`, `jsdom`, `@playwright/test`

Adding anything else needs a one-line justification in the commit that adds it.

## 7. Environment Variables

| Variable | Used by | Example / default |
|---|---|---|
| `APP_ENV` | backend | `development` / `test` / `production` |
| `MONGODB_URI` | backend | `mongodb://localhost:27017/?replicaSet=rs0&directConnection=true` |
| `MONGODB_DB` | backend | `acm` |
| `JWT_SECRET` | backend | ≥ 32 random bytes |
| `TOKEN_ENCRYPTION_KEY` | backend | base64 of 32 random bytes |
| `META_MODE` | backend | `real` / `fake` (fake refused in production) |
| `META_APP_ID`, `META_APP_SECRET` | backend | Meta app dashboard |
| `META_API_VERSION` | backend | `v26.0` |
| `META_REDIRECT_URI` | backend | `http://localhost:3000/api/meta/callback` |
| `INSTAGRAM_POSITIONS` | backend | `stream,explore` |
| `LLM_PROVIDER` | backend | `litellm` / `scripted` (scripted refused in production) |
| `OPENAI_API_KEY` | backend (read by LiteLLM) | provider key |
| `LLM_PRIMARY_MODEL`, `LLM_UTILITY_MODEL` | backend | `gpt-6.1-sol`, `gpt-6-luna` |
| `MOCK_METRICS` | backend | `true` for sandbox |
| `FAKE_META_FAIL_AT` | backend (fake mode only) | e.g. `ADSET` |
| `INSIGHTS_INTERVAL_HOURS` | backend | `6` |
| `BACKEND_URL` | frontend (rewrites) | `http://localhost:8000` |

## 8. Version Policy

- The Graph API version and model IDs are configuration. The `facebook-business` major version tracks the Graph API version (26.x ↔ v26.0); both are upgraded together.
- `google-adk` is pinned to the exact version proven in the Milestone 2 spike; ADK upgrades run the agent tests and the eval set before merging.
- Python and Node are pinned in `.python-version` and `.nvmrc`.
