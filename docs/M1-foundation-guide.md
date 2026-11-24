# M1 Foundation — Complete Guide

> **Current Status:**
> - **Milestone 1 (Foundation):** **100% COMPLETED** (All 8 tasks implemented, tested with 52 passing tests, and committed).
> - **Pending in M1:** None.
> - **Next Milestone:** Milestone 2 (Harness Core + Google ADK Spike).

---

## What is M1?

**M1** stands for **Milestone 1: Foundation**. It is the first coding phase of our project: **AI-Powered Ad Campaign Manager**.

Before we can build smart AI agents or publish ad campaigns to Instagram through the Meta API, we must build a rock-solid backend foundation. 

### Why build the foundation before AI and Meta features?
Think of building this software like building a modern skyscraper:
- If you start by decorating the penthouse (the AI prompts, chat interface, and Instagram ad buttons) without laying deep concrete pillars and plumbing, the building will collapse under the slightest pressure.
- An ad campaign involves **real money, user accounts, sensitive platform access tokens, and strict audit requirements**.
- If our system crashes, publishes ads without approval, leaks passwords, or gets confused about what time it is, users lose money and trust.

### What problem does this foundation solve?
M1 solves all the cross-cutting, foundational problems upfront:
1. **Configuration crashes:** If a critical secret (like a database URL or encryption key) is missing, the app refuses to start immediately instead of crashing midway during an ad purchase.
2. **Data safety and reliability:** We use MongoDB with replica set transactions and strict unique indexes so duplicate accounts or duplicate campaigns can never be created.
3. **Security:** Passwords are never stored in plain text (we use Argon2id). Meta tokens are encrypted using AES-256-GCM. Session cookies are HttpOnly and secure.
4. **Accountability:** Every single action is tracked with an immutable correlation ID and recorded in an append-only audit log.
5. **Reliable testing:** We have an injectable clock and per-test isolated databases so tests run fast, reliably, and independently without touching production data.

### What is possible after M1?
With M1 finished:
- A user can register, log in, view their profile, and log out safely.
- The backend handles errors with a clean, predictable format.
- Every important action leaves an audit trail.
- We can now safely build the campaign state machine, approval gates, AI agents, and Meta gateway in Milestones 2 and 3 on top of this foundation.

---

## High-Level Architecture Flow

```text
User / Frontend
      ↓
FastAPI Backend (create_app factory)
      ↓
[Middleware & Observability] (Correlation ID, Structlog)
      ↓
[Security & Error Envelope] (Argon2id, JWT Cookie, AES-GCM Encryption, Rate Limiter)
      ↓
Configuration & Clock (Settings, Injectable Clock)
      ↓
MongoDB Replica Set (Unique Indexes, Transactions, Audit Log)
      ↓
Business Logic & State Machine (Milestone 2)
      ↓
Meta API Gateway & Google ADK Agents (Milestone 3 & 4)
```

M1 represents the entire lower half of this diagram: the bedrock that keeps the application safe, tested, and reliable.

---

# 1. Project Structure

Here is how our project is organized:

```text
ad_campaign_manager/
├── .github/
│   └── workflows/
│       └── ci.yml               # Automated GitHub Actions test & lint pipeline
├── .env.example                 # Example configuration template (safe to commit)
├── .gitignore                   # Files that Git must never track (secrets, caches)
├── docker-compose.yml           # Runs local MongoDB single-node replica set
├── docs/                        # Project documentation and API payload contracts
│   ├── .claude/plans/           # Roadmaps, low-level design, milestone plans
│   ├── pay_loads/               # Verified Meta API v26.0 payloads from Graph API Explorer
│   └── M1-foundation-guide.md   # This comprehensive guide
└── backend/
    ├── pyproject.toml           # Python dependencies, Ruff rules, Pytest settings
    ├── uv.lock                  # Exact pinned versions of all installed packages
    ├── app/                     # Production application code
    │   ├── __init__.py
    │   ├── main.py              # Application factory (create_app)
    │   ├── config.py            # Typed Settings with validation
    │   ├── clock.py             # Injectable clock (SystemClock, FixedClock)
    │   ├── db.py                # MongoDB connection and index definitions
    │   ├── observability.py     # Correlation ID middleware & structured logging
    │   ├── audit.py             # Append-only audit logger
    │   ├── errors.py            # AppError hierarchy and standard error envelope
    │   ├── security/            # Security utilities
    │   │   ├── __init__.py
    │   │   ├── passwords.py     # Argon2id password hashing
    │   │   ├── jwt.py           # HS256 JWT creation and validation
    │   │   └── crypto.py        # AES-256-GCM token encryption
    │   └── api/                 # Web API routes and dependencies
    │       ├── __init__.py
    │       ├── deps.py          # FastAPI dependencies & RateLimiter
    │       └── auth.py          # /auth/register, /auth/login, /auth/me, /auth/logout
    └── tests/                   # Automated tests (mirroring app structure)
        ├── __init__.py
        ├── conftest.py          # Shared fixtures (db, client, settings)
        ├── unit/                # Unit tests (run in milliseconds, no external services)
        │   ├── test_config.py
        │   ├── test_clock.py
        │   ├── test_observability.py
        │   ├── test_architecture.py
        │   ├── test_passwords.py
        │   ├── test_jwt.py
        │   ├── test_crypto.py
        │   └── test_rate_limiter.py
        ├── integration/         # Integration tests (use real MongoDB replica set)
        │   ├── test_db.py
        │   └── test_audit.py
        └── api/                 # End-to-end API route tests (via HTTP client)
            ├── test_health.py
            ├── test_correlation_id.py
            └── test_auth.py
```

### Why are `app/` and `tests/` separated?
- **Separation of Concerns:** Production code in `app/` only contains what is needed to run the software. It never imports test libraries.
- **Mirroring:** Tests are categorized by speed and boundary:
  - `unit/`: Fast logic checks (password hashes, token formats, rate math).
  - `integration/`: Tests checking real database interactions, unique indexes, and transactions.
  - `api/`: Simulated HTTP requests verifying real status codes, cookie headers, and error envelopes.

---

# 2. Git Repository Setup

### Why a Dedicated Git Repository?
Version control records every single change made to the codebase. If an error is introduced, we can instantly trace who changed what, why, and roll back if necessary.

In M1, we followed strict **Test-Driven Development (TDD)**:
1. **RED:** Write a failing test proving the feature is missing.
2. **GREEN:** Write the minimal code to pass the test.
3. **REFACTOR:** Clean up the code and check formatting.
4. **COMMIT:** Save the atomic step to git with a clear message.

### Useful Git Commands
```bash
# Check what files are changed or untracked
git status

# View the clean, one-line commit history
git log --oneline

# Stage all files in backend
git add backend/

# Commit with a clear, descriptive message
git commit -m "feat: descriptive commit message"
```

Our commit history for M1:
- `fd2c3ed` — `feat: typed settings with production safety checks` (Task 1)
- `d44f1d5` — `feat: MongoDB replica set, indexes, per-test database and app factory` (Task 2)
- `6caccaa` — `feat: injectable clock` (Task 3)
- `83cca98` — `feat: correlation ids and append-only audit log` (Task 4)
- `a81d5bc` — `feat: argon2 password hashing and HS256 session tokens` (Task 5)
- `a7d2e8b` — `feat: error envelope, auth API with session cookie and login rate limit` (Task 6)
- `4d22e9a` — `feat: AES-256-GCM token encryption` (Task 7)
- `63dd635` — `ci: lint, tests with MongoDB replica set, secret scan` (Task 8)

---

# 3. Python Backend Setup

### Why Python 3.12?
Python is the standard language for AI systems and the official Meta Business SDK. Python 3.12 introduces substantial performance improvements, better error messages, and mature typing support.

### Why FastAPI?
FastAPI is a modern, high-speed asynchronous web framework. It automatically generates OpenAPI documentation (`/docs`), validates request bodies using Pydantic, and handles async database operations natively.

### Package Management with `uv`
Instead of standard `pip`, we use `uv` by Astral. `uv` is an extremely fast package manager written in Rust. It generates a locked, deterministic lockfile ([backend/uv.lock](file:///c:/Users/sreej/OneDrive/Desktop/SYNXA-LEARN/ad_campaign_manager/backend/uv.lock)), guaranteeing that all developers and CI run the exact same versions of every library.

### Dependencies Explained Simply

| Package | Purpose in M1 | Why is this useful? |
|---|---|---|
| `fastapi` | Web API framework | Handles HTTP requests, routes, cookies, and responses |
| `uvicorn[standard]` | ASGI web server | The server that runs FastAPI and listens on a network port |
| `pydantic` | Data validation | Validates incoming JSON bodies (e.g., email format, password length) |
| `pydantic-settings` | Environment variables | Reads and type-checks `.env` variables into a Python class |
| `pymongo` | MongoDB driver | The official async MongoDB driver for database read/write queries |
| `httpx` | Async HTTP client | Used in tests (`AsyncClient`) to send mock HTTP requests to FastAPI |
| `argon2-cffi` | Password hashing | Hashes user passwords with the memory-hard Argon2id algorithm |
| `pyjwt` | JSON Web Tokens | Generates and verifies signed session cookies |
| `cryptography` | Encryption | Provides AES-256-GCM authenticated encryption for sensitive tokens |
| `structlog` | Structured logging | Formats log messages as JSON with correlation IDs |
| `pytest` | Test runner | Automatically discovers and runs our automated tests |
| `pytest-asyncio` | Async test support | Lets test functions use `async def` and `await` |
| `ruff` | Linter and formatter | Enforces clean Python style and code formatting in milliseconds |

---

# 4. Environment Variables and Configuration

### What is `.env`?
Configuration settings (like database passwords, secret keys, API endpoints) change between your laptop, the staging server, and production.
- We **never hard-code secrets** in Python code.
- `.env` holds the real, local values on your computer.
- `.env.example` is a safe template committed to git showing what variables are needed without containing real secrets.
- `.env` is listed in `.gitignore` so your private secrets can never be accidentally pushed to GitHub.

### How `app/config.py` Works
We define a `Settings` class using `pydantic-settings`. When the app starts, it reads environment variables and checks types:
- If a string is expected, it ensures it is a string.
- If a minimum length is required (like `jwt_secret: str = Field(min_length=32)`), it fails if you supply fewer than 32 characters.
- `@lru_cache` ensures that `get_settings()` only reads and parses the environment variables once instead of re-reading the disk on every single web request.

### Implemented Settings Reference

#### `APP_ENV`
- **What:** The environment mode the backend is running in.
- **Why:** Controls security rules, logging format, and allowed modes.
- **Example:** `development` (options: `development`, `test`, `production`).
- **Used by:** `app/config.py`, `app/observability.py`, `app/api/auth.py`.

#### `MONGODB_URI`
- **What:** Connection string to the MongoDB replica set.
- **Why:** Tells the backend where the MongoDB database lives.
- **Example:** `mongodb://localhost:27017/?replicaSet=rs0&directConnection=true`
- **Used by:** `app/db.py`, `tests/conftest.py`.

#### `MONGODB_DB`
- **What:** The name of the database inside MongoDB.
- **Why:** Keeps our data separate from any other project on the same database server.
- **Example:** `acm` (default).
- **Used by:** `app/main.py`.

#### `JWT_SECRET`
- **What:** A long random cryptographic secret string (at least 32 characters).
- **Why:** Signs user login session cookies so users cannot forge their identity.
- **Example:** `change-me-to-32-or-more-random-characters`
- **Used by:** `app/security/jwt.py`, `app/api/auth.py`.

#### `TOKEN_ENCRYPTION_KEY`
- **What:** Base64-encoded string of exactly 32 random bytes (256 bits).
- **Why:** Encrypts external platform OAuth tokens (Meta tokens) stored in the database.
- **Example:** `base64-of-32-random-bytes`
- **Used by:** `app/security/crypto.py`.

#### `META_MODE`
- **What:** Switches between real Meta Graph API calls and in-memory mock calls.
- **Why:** Allows offline development and testing without making external calls or spending money.
- **Example:** `real` (development) or `fake` (tests).
- **Used by:** `app/config.py`, future `meta/gateway.py`.

#### `META_APP_ID` & `META_APP_SECRET`
- **What:** Credentials from the Meta Developer Dashboard for OAuth.
- **Why:** Needed to allow users to connect their Instagram ad accounts.
- **Example:** `1415879818267624`
- **Used by:** Future `app/meta/oauth.py`.

#### `META_API_VERSION`
- **What:** Graph API version string.
- **Why:** Ensures Meta version is controlled by config, never hard-coded in logic.
- **Example:** `v26.0` (default).
- **Used by:** Future `app/meta/sdk_gateway.py`.

#### `META_REDIRECT_URI`
- **What:** OAuth callback URL.
- **Why:** Where Meta redirects the user's browser after granting permissions.
- **Example:** `http://localhost:3000/api/meta/callback`
- **Used by:** Future OAuth flows.

#### `INSTAGRAM_POSITIONS`
- **What:** Comma-separated list of Instagram ad placements.
- **Why:** Defines where ads will appear on Instagram.
- **Example:** `stream,explore`
- **Property:** `Settings.instagram_position_list -> ["stream", "explore"]`.
- **Used by:** Campaign targeting validators.

#### `LLM_PROVIDER`
- **What:** Model provider (`litellm` or `scripted`).
- **Why:** Uses deterministic scripted responses in tests and offline mock mode, and real LLMs in live use.
- **Example:** `litellm` (production) or `scripted` (tests).
- **Used by:** Future agent runner.

#### `LLM_PRIMARY_MODEL` & `LLM_UTILITY_MODEL`
- **What:** Specific AI model names.
- **Why:** Allows upgrading or changing AI models in `.env` without modifying code.
- **Example:** `gpt-6.1-sol`, `gpt-6-luna`.
- **Used by:** Future agent definitions.

#### `MOCK_METRICS`
- **What:** Boolean flag (`True` / `False`).
- **Why:** Generates simulated ad performance metrics when testing with sandbox accounts.
- **Example:** `True`
- **Used by:** Future analytics collector.

#### `FAKE_META_FAIL_AT`
- **What:** Fault-injection flag (e.g., `"ADSET"`, `"CREATIVE"`).
- **Why:** Simulates platform failures during tests to prove the publishing job can recover cleanly.
- **Example:** `""` (empty in normal operation).
- **Used by:** Testing failure-recovery flows.

#### `INSIGHTS_INTERVAL_HOURS`
- **What:** How often the background scheduler fetches performance data.
- **Why:** Controls background analytics refresh cadence.
- **Example:** `6` (hours).
- **Used by:** Future APScheduler worker.

---

# 5. Production Safety Checks

### Why Production Safety Checks?
In development, it is convenient to use fake Meta gateways and mock AI models. However, if a developer accidentally deployed to production with `META_MODE=fake` or `LLM_PROVIDER=scripted`, real ad campaigns would never be published, or fake data would be presented to real paying customers!

To make this impossible, `app/config.py` contains a `@model_validator(mode="after")`:

```python
if self.app_env == "production":
    if self.meta_mode == "fake":
        raise ValueError("META_MODE=fake is not allowed in production")
    if self.llm_provider == "scripted":
        raise ValueError("LLM_PROVIDER=scripted is not allowed in production")
    if self.fake_meta_fail_at:
        raise ValueError("FAKE_META_FAIL_AT is not allowed in production")
```

### What happens if an invalid setting is used?
If `APP_ENV=production` is set while `META_MODE=fake`, the backend **refuses to start**. Pydantic throws a `ValidationError` during startup, crashing immediately before any web traffic can be accepted.

---

# 6. MongoDB

### MongoDB Fundamentals
- **Database:** A container holding our application data (`acm`).
- **Collection:** Similar to a table in relational databases (e.g., `users`, `campaigns`, `audit_log`).
- **Document:** A JSON-like record stored in BSON format inside a collection (e.g., one user record).

### Why a MongoDB Replica Set?
MongoDB transactions (used when creating a campaign version or recording an approval) **only work on a replica set**. We use a single-node replica set named `rs0`. It behaves identically to a multi-node cluster while running easily on a single local machine or container.

### Collections and Indexes in `app/db.py`

| Collection | Indexed Fields | Options | Why this index exists |
|---|---|---|---|
| `users` | `email` (asc) | `unique=True` | Guarantees an email can only register once |
| `meta_connections` | `user_id` (asc) | — | Fast lookup of Meta tokens for a specific user |
| `campaigns` | `user_id`, `status` | — | Fast filtering of a user's active/paused campaigns |
| `campaign_versions` | `campaign_id`, `version` | `unique=True` | Ensures version numbers (v1, v2) are unique per campaign |
| `messages` | `campaign_id`, `created_at` | — | Chronological ordering of campaign chat history |
| `approvals` | `campaign_id`, `action` | — | Fast retrieval of user approvals |
| `publish_runs` | `campaign_id`, `version` | `unique=True` | Prevents publishing the same version twice (no duplicate ads) |
| `insights_daily` | `meta_object_id`, `level`, `day` | `unique=True` | Prevents storing the same day's metrics twice |
| `audit_log` | `campaign_id`, `ts` & `correlation_id` | — | Fast audit searches by campaign or correlation trace |

`ensure_indexes(db)` runs during application startup to automatically create any missing indexes.

---

### How to Access and Inspect MongoDB

#### Option 1 — Using Docker & `mongosh`
If you run MongoDB through Docker:
```bash
# 1. Start MongoDB in background
docker compose up -d mongo

# 2. Check that it is healthy and running
docker compose ps

# 3. Open the interactive MongoDB Shell (mongosh)
docker exec -it ad_campaign_manager-mongo-1 mongosh
```

Inside `mongosh`:
```javascript
// Show all databases
show dbs

// Switch to our project database
use acm

// Show all collections
show collections

// View all registered users
db.users.find().pretty()

// View all audit log entries
db.audit_log.find().pretty()

// Exit mongosh
exit
```

#### Option 2 — Using MongoDB Compass (GUI)
MongoDB Compass is a visual graphical interface for inspecting your database:
1. Open **MongoDB Compass**.
2. In the connection string field, paste:
   ```text
   mongodb://localhost:27017/?replicaSet=rs0&directConnection=true
   ```
3. Click **Connect**.
4. In the left sidebar, click on the **`acm`** database.
5. Click any collection (e.g., `users` or `audit_log`) to inspect documents visually, filter fields, or view created indexes.

### Why Tests Create `acm_test_xxxxx` Databases
When automated tests run, `tests/conftest.py` generates a fresh database for every test (e.g., `acm_test_a1b2c3d4e5`). 
- It creates indexes.
- Runs the test against clean, isolated tables.
- Drops (deletes) the test database completely after the test finishes.
- **Result:** Tests never pollute your real data, and tests cannot interfere with each other.

---

# 7. FastAPI Application

### What is `create_app()`?
In `backend/app/main.py`, instead of creating a global `app = FastAPI()`, we use an **Application Factory** function:

```python
def create_app(settings: Settings | None = None, db=None) -> FastAPI:
    ...
```

### Why use an Application Factory?
1. **Testing:** A test can pass in custom test settings (like `meta_mode="fake"`) and a dedicated test database without modifying global state.
2. **Lifespan Management:** When the app starts up without an existing database connection, its async `lifespan` automatically connects to MongoDB, ensures all indexes are built, and cleanly closes the connection on shutdown.

### Starting the Backend Locally
From the `backend/` directory:
```bash
cd backend
uv run uvicorn app.main:create_app --factory --reload --port 8000
```

### Checking that the Backend is Running
1. **Health Check:**
   Visit: `http://localhost:8000/health`
   Response:
   ```json
   { "status": "ok" }
   ```
2. **Interactive Swagger Documentation:**
   Visit: `http://localhost:8000/docs`
   You can view all available endpoints, schemas, and try them directly in your browser.
3. **OpenAPI JSON Spec:**
   Visit: `http://localhost:8000/openapi.json`

---

# 8. Testing Setup

### Why Test-Driven Development (TDD)?
We write tests **before** code to ensure:
- Every feature has a clear, measurable acceptance criteria.
- We never write dead or redundant code.
- We can refactor fearlessly knowing that regressions will be caught immediately.

### Pytest & Async Testing
- `pytest` discovers and runs tests matching `test_*.py`.
- Because FastAPI and PyMongo are asynchronous (`async`/`await`), `pytest-asyncio` enables tests to run inside an async event loop (`asyncio_mode = "auto"`).
- `httpx.AsyncClient` with `ASGITransport(app=app)` simulates real HTTP requests directly against FastAPI inside the process without needing to open a physical network port.

### Core Fixtures in `tests/conftest.py`
- `settings`: Injects test settings with dummy keys and `meta_mode="fake"`.
- `db`: Connects to MongoDB, creates indexes on a unique temporary test database (`acm_test_*`), yields it to the test, and drops it afterwards.
- `client`: Provides an `AsyncClient` wired to the app factory using the test database.

### Running Tests
```bash
# Run the entire backend test suite
cd backend
uv run pytest -v

# Run only a specific test file
uv run pytest tests/unit/test_config.py -v

# Run with concise output
uv run pytest -q
```

---

# 9. Implemented Tests Overview

### 1. Configuration Tests (`tests/unit/test_config.py`)
- `test_missing_mongodb_uri_is_rejected`: Proves the app will not start without a database URI.
- `test_short_jwt_secret_is_rejected`: Proves JWT secrets under 32 characters raise a `ValidationError`.
- `test_defaults`: Proves default API version is `v26.0`, db is `acm`, and positions are `["stream", "explore"]`.
- `test_production_refuses_fake_meta`: Proves production environment rejects `meta_mode=fake`.
- `test_production_refuses_scripted_llm`: Proves production environment rejects `llm_provider=scripted`.
- `test_production_refuses_fault_injection`: Proves production environment rejects `fake_meta_fail_at`.

### 2. Injectable Clock Tests (`tests/unit/test_clock.py`)
- `test_system_clock_is_timezone_aware`: Proves `SystemClock().now()` and `utcnow()` return timezone-aware UTC datetimes.
- `test_fixed_clock_returns_start_and_advances`: Proves `FixedClock` holds time frozen and advances when `.advance(days=7)` is called.
- `test_fixed_clock_rejects_naive_datetime`: Proves `FixedClock` raises an error if passed a naive datetime without timezone info.

### 3. Observability & Audit Tests (`tests/unit/test_observability.py` & `tests/integration/test_audit.py`)
- `test_processor_adds_correlation_id_when_set`: Proves log records receive the request's correlation ID.
- `test_record_inserts_event_with_correlation_id`: Proves `audit.record()` inserts an event with timestamp and correlation ID.
- `test_record_rejects_unknown_actor`: Proves only `"user"`, `"agent"`, or `"system"` can write audit logs.

### 4. Correlation ID API Tests (`tests/api/test_correlation_id.py`)
- `test_generated_correlation_id_is_returned`: Proves every HTTP response includes a 32-character `X-Correlation-ID` header.
- `test_safe_incoming_correlation_id_is_echoed`: Proves an incoming safe header (e.g., `req-42`) is preserved.
- `test_unsafe_incoming_correlation_id_is_replaced`: Proves invalid/malicious characters in headers are sanitized and replaced.

### 5. Security & Token Tests (`tests/unit/test_passwords.py`, `test_jwt.py`, `test_crypto.py`)
- `test_hash_is_not_the_password_and_verifies`: Proves Argon2id hashes passwords securely and verifies them.
- `test_roundtrip_returns_subject`: Proves JWT session tokens decode correctly to the original user ID.
- `test_expired_token_is_rejected`: Proves expired tokens raise `InvalidToken`.
- `test_roundtrip`: Proves AES-256-GCM recovers original Meta tokens.
- `test_tampered_ciphertext_is_rejected`: Proves tampering with a single byte in an encrypted token raises `InvalidTag`.

### 6. Authentication API Tests (`tests/api/test_auth.py`)
- `test_register_creates_user_with_hashed_password`: Proves registration stores hashed passwords in MongoDB.
- `test_duplicate_email_is_409_with_envelope`: Proves duplicate registration returns 409 `EMAIL_TAKEN`.
- `test_login_sets_httponly_lax_session_cookie`: Proves login sets a secure HttpOnly session cookie.
- `test_me_requires_a_session`: Proves unauthenticated requests to `/auth/me` return 401 `UNAUTHENTICATED`.
- `test_login_is_rate_limited`: Proves making more than 10 failed login attempts within 60 seconds returns 429 `RATE_LIMITED`.
- `test_register_and_login_are_audited`: Proves user registration and login write audit records to MongoDB.

---

# 10. Database Indexes Deep Dive

### What is an index?
Imagine a phonebook with 1,000,000 people. If it wasn't sorted alphabetically, you would have to read every single page from beginning to end to find one person (a **collection scan**). An index is an alphabetical index table that lets MongoDB find the exact document in milliseconds.

### Why Unique Indexes?
Indexes in MongoDB don't just speed up queries; they enforce **business integrity rules**:
- **`users.email (unique)`**: Prevents two accounts from sharing the same email.
- **`publish_runs (campaign_id, version) (unique)`**: Makes it physically impossible for two concurrent server threads to publish the same version of an ad to Instagram twice.

If an index is missing, MongoDB has to scan every single document in the collection, slowing down the entire application as data grows.

---

# 11. Application Lifecycle

Here is what happens from the moment the server boots:

```text
1. Process Starts (Uvicorn)
      ↓
2. Settings Loaded (get_settings reads .env)
      ↓
3. Production Safety Verified (Pydantic validator ensures no fake modes in production)
      ↓
4. Structlog Configured (JSON logs in production, Console in development)
      ↓
5. FastAPI Instance Created (create_app factory)
      ↓
6. Middleware Added (CorrelationIdMiddleware wraps all requests)
      ↓
7. Error Handlers Installed (AppError & RequestValidationError envelope handlers)
      ↓
8. Routers Registered (/health and /auth routes attached)
      ↓
9. Lifespan Startup: Connect to MongoDB replica set & run ensure_indexes()
      ↓
10. Ready to Serve HTTP Requests!
      ↓
11. Lifespan Shutdown: Cleanly close MongoDB client connection
```

---

# 12. Security Basics

Here is the exact security model implemented in M1:

### 1. Password Hashing (Argon2id)
- Implemented in [app/security/passwords.py](file:///c:/Users/sreej/OneDrive/Desktop/SYNXA-LEARN/ad_campaign_manager/backend/app/security/passwords.py).
- Winner of the Password Hashing Competition.
- Memory-hard algorithm resistant to GPU-based brute-force cracking.
- Generates a unique salt automatically for every password.

### 2. Session Cookies (JWT over HttpOnly Cookies)
- Implemented in [app/security/jwt.py](file:///c:/Users/sreej/OneDrive/Desktop/SYNXA-LEARN/ad_campaign_manager/backend/app/security/jwt.py).
- Signed using HMAC-SHA256 (`HS256`).
- Stored in a browser cookie named `session` with flags:
  - `HttpOnly`: Client-side JavaScript cannot read the cookie, preventing XSS token theft.
  - `SameSite=Lax`: Prevents CSRF attacks during cross-site requests.
  - `Secure`: Transmitted only over HTTPS in production.
  - `max_age=43200`: 12-hour expiration.

### 3. Token Encryption at Rest (AES-256-GCM)
- Implemented in [app/security/crypto.py](file:///c:/Users/sreej/OneDrive/Desktop/SYNXA-LEARN/ad_campaign_manager/backend/app/security/crypto.py).
- Encrypts external platform credentials (like Meta user tokens).
- Authenticated encryption (AEAD): if someone alters the encrypted text in MongoDB, decryption fails with `InvalidTag` rather than returning corrupted data.

### 4. Brute-Force Rate Limiting
- Implemented in [app/api/deps.py](file:///c:/Users/sreej/OneDrive/Desktop/SYNXA-LEARN/ad_campaign_manager/backend/app/api/deps.py).
- Enforces a limit of 10 login attempts per minute per IP address. Exceeding this returns HTTP 429 `RATE_LIMITED`.

---

# 13. How Everything Connects

```text
Incoming Request: POST /auth/login
      ↓
[CorrelationIdMiddleware]
- Assigns or reads X-Correlation-ID (e.g., 9f8a7b6c...)
- Binds to async context var for logging
      ↓
[RateLimiter]
- Checks if client IP has made > 10 attempts in the last 60s
      ↓
[Auth Route: login()]
- Queries MongoDB users collection for lowercased email
- Verifies password against Argon2id hash (with dummy hash timing protection)
- Issues signed HS256 JWT containing user ID
      ↓
[Audit Log]
- Records USER_LOGIN event in MongoDB with timestamp & correlation ID
      ↓
[HTTP Response]
- Sets "session" HttpOnly cookie
- Returns X-Correlation-ID header
- Returns public user profile { "id": "...", "email": "..." }
```

---

# 14. How I Can Run the Project

Follow this step-by-step checklist:

### Step 1: Open Terminal & Navigate to Project
```bash
cd "c:\Users\sreej\OneDrive\Desktop\SYNXA-LEARN\ad_campaign_manager"
```

### Step 2: Ensure Environment File Exists
If you don't have a `.env` file yet, copy it from the example:
```bash
cp .env.example .env
```

### Step 3: Start MongoDB
```bash
docker compose up -d mongo
```
Verify it is running:
```bash
docker compose ps
```

### Step 4: Install Dependencies (if not already installed)
```bash
cd backend
uv sync
```

### Step 5: Start the Backend Server
```bash
uv run uvicorn app.main:create_app --factory --reload --port 8000
```

### Step 6: Verify in Your Browser
- Open `http://localhost:8000/health` → Should show `{"status": "ok"}`
- Open `http://localhost:8000/docs` → Interactive Swagger API documentation

---

# 15. How I Can Verify M1 Is Working

Run this checklist to verify that everything is in working order:

- [x] **Git Repository:** `git status` shows clean working tree on `master`.
- [x] **Environment Validation:** `uv run pytest tests/unit/test_config.py` passes all 6 tests.
- [x] **Injectable Clock:** `uv run pytest tests/unit/test_clock.py` passes all 3 tests.
- [x] **Correlation & Observability:** `uv run pytest tests/unit/test_observability.py tests/api/test_correlation_id.py` passes.
- [x] **Password & JWT Security:** `uv run pytest tests/unit/test_passwords.py tests/unit/test_jwt.py` passes.
- [x] **Token Encryption:** `uv run pytest tests/unit/test_crypto.py` passes.
- [x] **Authentication API:** `uv run pytest tests/api/test_auth.py` passes all 11 endpoints and audit checks.
- [x] **Database & Replica Set:** `uv run pytest tests/integration/test_db.py` passes all transaction and unique index checks.
- [x] **Code Quality:** `uv run ruff check .` and `uv run ruff format --check .` report zero errors.
- [x] **Full Suite:** `uv run pytest -q` passes all 52 tests green.

---

# 16. Common Problems and Fixes

### 1. Tests Fail with `ServerSelectionTimeoutError` (Cannot connect to MongoDB)
- **Why:** The MongoDB server is not running on port 27017, or the replica set `rs0` is not initiated.
- **Fix:** Run `docker compose up -d mongo`. If running local Windows `mongod.exe`, ensure it was started with `--replSet rs0 --port 27017` and initialized with `rs.initiate()`.

### 2. `ValidationError: 1 validation error for Settings jwt_secret`
- **Why:** Your `JWT_SECRET` in `.env` is shorter than 32 characters.
- **Fix:** In `.env`, change `JWT_SECRET` to a random string with at least 32 characters (e.g. `12345678901234567890123456789012`).

### 3. `ValueError: META_MODE=fake is not allowed in production`
- **Why:** You have `APP_ENV=production` set while `META_MODE=fake`.
- **Fix:** If you are running locally for testing, set `APP_ENV=development` in your `.env`.

### 4. `Port 8000 is already in use`
- **Why:** Another process is already running on port 8000.
- **Fix:** Start Uvicorn on a different port, e.g.:
  ```bash
  uv run uvicorn app.main:create_app --factory --port 8001
  ```

---

# 17. What M1 Gives Us

With M1 completed, our application has:
1. **A Clean Architecture:** App factory with dependency injection and lifespan management.
2. **Type-Safe Configuration:** Fails fast before errors occur in production.
3. **Enterprise Security:** Argon2id password hashing, AES-256-GCM token encryption, HttpOnly session cookies, and login rate limiting.
4. **Guaranteed Data Integrity:** Real MongoDB replica set support with unique indexes and transactions.
5. **Full Observability:** Distributed correlation IDs and an append-only audit trail.
6. **Time-Independent Testing:** Injectable `Clock` protocol allowing instant simulation of future dates.
7. **Automated CI Pipeline:** GitHub Actions running linter, test suite against MongoDB, and secret scans on every push.

---

# 18. What Comes Next

### Milestone Status

| Milestone | Description | Status |
|---|---|---|
| **M0** | Meta + Instagram Proven by Hand | **DONE** (Manual exploratory payloads recorded; creative blocked due to personal ad account) |
| **M1** | Foundation | **100% DONE** (All 8 tasks completed, 52 tests green) |
| **M2** | Harness Core + ADK Spike | **NOT STARTED** (Next: Domain rules, state machine, approvals, Google ADK) |
| **M3** | Meta Connection + Gateway | **NOT STARTED** (Meta OAuth, AdsReader/AdsWriter, FakeAdsGateway) |
| **M4** | Brief → Proposal (ADK Agents) | **NOT STARTED** (Conversational brief collection, ad variant generation) |
| **M5** | Review + Approval | **NOT STARTED** (Immutable versioning, field diffs, approval gates) |
| **M6** | Publishing | **NOT STARTED** (Checkpoint-resumable publishing to Instagram) |
| **M7** | Monitoring | **NOT STARTED** (Scheduled metrics collection, performance simulator) |
| **M8** | Analysis + Optimization | **NOT STARTED** (Plain-language grounded reports, improvement proposals) |
| **M9** | Evaluation | **NOT STARTED** (Benchmark evaluation suite) |
| **M10** | Ship | **NOT STARTED** (Final deployment & demo) |

---

# 19. Quick Reference Cheat Sheet

```bash
# 1. Start MongoDB (replica set rs0)
docker compose up -d mongo

# 2. Check MongoDB status
docker compose ps

# 3. Sync dependencies
cd backend && uv sync

# 4. Run full test suite (52 tests)
cd backend && uv run pytest -q

# 5. Run lint & formatting checks
cd backend && uv run ruff check . && uv run ruff format --check .

# 6. Start the backend development server
cd backend && uv run uvicorn app.main:create_app --factory --reload --port 8000

# 7. Check Git commits
git log --oneline -n 10
```

- **Health check URL:** `http://localhost:8000/health`
- **Swagger API Docs:** `http://localhost:8000/docs`
- **MongoDB Connection String:** `mongodb://localhost:27017/?replicaSet=rs0&directConnection=true`
- **Config template:** `.env.example`
- **Local config:** `.env`

---

## In One Sentence

> **M1 gives our Ad Campaign Manager a secure, time-controllable, fully tested backend foundation with MongoDB, user authentication, encryption, and audit tracking so that subsequent milestones can build smart AI campaign agents and Meta publishing safely.**
