# Milestone 1 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Follow superpowers:test-driven-development for every step marked RED/GREEN.

**Goal:** A runnable FastAPI backend on MongoDB with settings, an injectable clock, correlation IDs, an append-only audit log, password + JWT auth with a session cookie, a standard error envelope, token encryption, and CI.

**Architecture:** `create_app(settings, db)` builds the app, so tests inject a per-test MongoDB database. Cross-cutting pieces (`config`, `clock`, `db`, `observability`, `audit`, `errors`, `security/*`) are small single-purpose modules that later milestones reuse unchanged.

**Tech Stack:** Python 3.12, FastAPI, pydantic-settings, PyMongo async, argon2-cffi, PyJWT, cryptography, structlog, pytest + pytest-asyncio, httpx, Docker (MongoDB 8 replica set), uv.

**Spec:** `.claude/plans/lld.md` §1–§3 · `.claude/plans/tech-stack.md` · PRD NFR-1, NFR-2, NFR-6, NFR-8.

## Global Constraints

- Python 3.12; dependencies via `uv`; Ruff for lint and format.
- MongoDB tests use a real replica set and a fresh database per test.
- No `datetime.now(` outside `app/clock.py`.
- Only `app/audit.py` (and the index list in `app/db.py`) mention `audit_log`.
- Error responses: `{"error": {"code", "message", "details"}}`.
- Session cookie: name `session`, HttpOnly, SameSite=Lax, Secure in production, 12 h.
- Secrets only from env vars; `.env` is git-ignored.

## Before You Start: What This Milestone Builds and Why

Every later feature needs the same foundation: configuration that fails fast, a database whose rules (unique indexes, transactions) we can rely on, a way to trace one request through the logs (correlation ID), a permanent record of every important action (audit log), and user accounts. We build these first, test-first, so later milestones only *use* them.

**Why a real MongoDB in tests?** The safety of this product depends on database guarantees: "an email can only register once", "two approvals can't both win", "the same day's metrics can't be stored twice". A fake database would happily pass tests that the real one fails. A fresh database per test keeps tests independent.

**Why a replica set locally?** MongoDB transactions (used for approvals in M2) only work on a replica set. A one-node replica set in Docker gives us that.

## File Map

| File | Responsibility |
|---|---|
| `backend/pyproject.toml` | Dependencies, Ruff, pytest config |
| `docker-compose.yml` | MongoDB single-node replica set |
| `.gitignore`, `.env.example` | Keep secrets out of git; document variables |
| `backend/app/config.py` | `Settings`, `get_settings()` |
| `backend/app/clock.py` | `Clock`, `SystemClock`, `FixedClock`, `utcnow()` |
| `backend/app/db.py` | `connect()`, `INDEXES`, `ensure_indexes()` |
| `backend/app/main.py` | `create_app()` |
| `backend/app/observability.py` | Correlation-ID middleware, structlog setup |
| `backend/app/audit.py` | `record()` |
| `backend/app/errors.py` | `AppError` family, error-envelope handlers |
| `backend/app/security/passwords.py`, `jwt.py`, `crypto.py` | Hashing, tokens, encryption |
| `backend/app/api/deps.py` | `get_db`, `get_settings_dep`, `current_user`, `RateLimiter` |
| `backend/app/api/auth.py` | `/auth/*` routes |
| `backend/tests/conftest.py` | `settings`, `db`, `client` fixtures |
| `.github/workflows/ci.yml` | Lint, tests (with MongoDB), secret scan |

---

### Task 1: Project Tooling and Settings

> **Understand this task:** Settings are read from environment variables into one typed object. If a required secret is missing, the app refuses to start, which is better than failing later in production. The production-safety checks (no fake Meta, no scripted model in production) live here, so they can't be forgotten elsewhere.

**Files:**
- Create: `backend/pyproject.toml`, `.gitignore`, `.env.example`, `backend/app/__init__.py`, `backend/app/config.py`
- Test: `backend/tests/__init__.py`, `backend/tests/unit/__init__.py`, `backend/tests/unit/test_config.py`

**Interfaces:**
- Produces: `Settings` (fields per LLD §2.1), `get_settings() -> Settings`, `Settings.instagram_position_list -> list[str]`

- [ ] **Step 0: Create a dedicated git repository**

This project folder currently sits inside a git repository rooted at the Desktop. Give the project its own repository:

```bash
cd "ad-campaign-manager"   # the project root (the folder that holds backend/ and frontend/)
git init
```

- [ ] **Step 1: Write the config files (no test needed for config)**

`backend/pyproject.toml`:

```toml
[project]
name = "acm-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "pydantic",
    "pydantic-settings",
    "pymongo>=4.13",
    "httpx",
    "argon2-cffi",
    "pyjwt",
    "cryptography",
    "structlog",
]

[dependency-groups]
dev = ["pytest", "pytest-asyncio", "ruff"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
pythonpath = ["."]
testpaths = ["tests"]

[tool.ruff]
line-length = 110

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "ASYNC"]
```

`.gitignore`:

```gitignore
.env
.venv/
__pycache__/
*.pyc
node_modules/
.next/
```

`.env.example`:

```dotenv
APP_ENV=development
MONGODB_URI=mongodb://localhost:27017/?replicaSet=rs0&directConnection=true
MONGODB_DB=acm
JWT_SECRET=change-me-to-32-or-more-random-characters
TOKEN_ENCRYPTION_KEY=base64-of-32-random-bytes
META_MODE=fake
META_APP_ID=
META_APP_SECRET=
META_API_VERSION=v26.0
META_REDIRECT_URI=http://localhost:3000/api/meta/callback
INSTAGRAM_POSITIONS=stream,explore
LLM_PROVIDER=scripted
OPENAI_API_KEY=
LLM_PRIMARY_MODEL=gpt-6.1-sol
LLM_UTILITY_MODEL=gpt-6-luna
MOCK_METRICS=true
FAKE_META_FAIL_AT=
INSIGHTS_INTERVAL_HOURS=6
```

Run: `cd backend && uv sync`
Expected: a virtual environment is created and dependencies install.

- [ ] **Step 2: Write the failing tests**

`backend/tests/unit/test_config.py`:

```python
import pytest
from pydantic import ValidationError

from app.config import Settings

BASE = {
    "mongodb_uri": "mongodb://localhost:27017",
    "jwt_secret": "s" * 32,
    "token_encryption_key": "k",
}


def test_missing_mongodb_uri_is_rejected(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret="s" * 32, token_encryption_key="k")


def test_short_jwt_secret_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**BASE, "jwt_secret": "short"})


def test_defaults():
    s = Settings(_env_file=None, **BASE)
    assert s.meta_api_version == "v26.0"
    assert s.mongodb_db == "acm"
    assert s.instagram_position_list == ["stream", "explore"]
    assert s.mock_metrics is True


def test_production_refuses_fake_meta():
    with pytest.raises(ValidationError, match="fake"):
        Settings(_env_file=None, **BASE, app_env="production", meta_mode="fake")


def test_production_refuses_scripted_llm():
    with pytest.raises(ValidationError, match="scripted"):
        Settings(_env_file=None, **BASE, app_env="production", meta_mode="real", llm_provider="scripted")


def test_production_refuses_fault_injection():
    with pytest.raises(ValidationError, match="fail"):
        Settings(_env_file=None, **BASE, app_env="production", meta_mode="real",
                 llm_provider="litellm", fake_meta_fail_at="ADSET")
```

- [ ] **Step 3: Run the tests and watch them fail**

Run: `cd backend && uv run pytest tests/unit/test_config.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 4: Write the minimal implementation**

`backend/app/__init__.py`: empty file.

`backend/app/config.py`:

```python
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    mongodb_uri: str
    mongodb_db: str = "acm"
    jwt_secret: str = Field(min_length=32)
    token_encryption_key: str
    meta_mode: Literal["real", "fake"] = "real"
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_api_version: str = "v26.0"
    meta_redirect_uri: str = "http://localhost:3000/api/meta/callback"
    instagram_positions: str = "stream,explore"
    llm_provider: Literal["litellm", "scripted"] = "litellm"
    llm_primary_model: str = "gpt-6.1-sol"
    llm_utility_model: str = "gpt-6-luna"
    scripted_scenario: str = "happy_path"
    mock_metrics: bool = True
    fake_meta_fail_at: str = ""
    insights_interval_hours: int = 6

    @property
    def instagram_position_list(self) -> list[str]:
        return [p.strip() for p in self.instagram_positions.split(",") if p.strip()]

    @model_validator(mode="after")
    def _production_safety(self) -> "Settings":
        if self.app_env == "production":
            if self.meta_mode == "fake":
                raise ValueError("META_MODE=fake is not allowed in production")
            if self.llm_provider == "scripted":
                raise ValueError("LLM_PROVIDER=scripted is not allowed in production")
            if self.fake_meta_fail_at:
                raise ValueError("FAKE_META_FAIL_AT is not allowed in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Also create empty `backend/tests/__init__.py` and `backend/tests/unit/__init__.py`.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `cd backend && uv run pytest tests/unit/test_config.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add .gitignore .env.example backend/pyproject.toml backend/uv.lock backend/app backend/tests
git commit -m "feat: typed settings with production safety checks"
```

---

### Task 2: MongoDB, Indexes, Per-Test Database and the App Factory

> **Understand this task:**
> - **Indexes as rules:** a unique index makes MongoDB itself refuse duplicates (two users with one email, two metric rows for one day). Code can have bugs; the index can't be bypassed.
> - **`ensure_indexes()`** runs at startup and is safe to run repeatedly.
> - **The per-test database fixture:** each test gets an empty database and drops it afterwards, so tests never affect each other.
> - **`create_app(settings, db)`:** tests pass their database in; in production the app connects at startup.

**Files:**
- Create: `docker-compose.yml`, `backend/app/db.py`, `backend/app/main.py`, `backend/tests/conftest.py`, `backend/tests/integration/__init__.py`, `backend/tests/api/__init__.py`
- Test: `backend/tests/integration/test_db.py`, `backend/tests/api/test_health.py`

**Interfaces:**
- Consumes: `Settings` (Task 1)
- Produces: `connect(settings) -> AsyncMongoClient`, `INDEXES`, `async ensure_indexes(db)`, `create_app(settings=None, db=None) -> FastAPI`; fixtures `settings`, `db`, `client`

- [ ] **Step 1: Start MongoDB as a replica set (config, no test)**

`docker-compose.yml`:

```yaml
services:
  mongo:
    image: mongo:8
    command: ["--replSet", "rs0", "--bind_ip_all", "--port", "27017"]
    ports: ["27017:27017"]
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval",
             "try { rs.status().ok } catch (e) { rs.initiate({_id: 'rs0', members: [{_id: 0, host: 'localhost:27017'}]}).ok }"]
      interval: 5s
      timeout: 10s
      retries: 30
    volumes: ["mongo-data:/data/db"]
volumes:
  mongo-data:
```

Run: `docker compose up -d mongo && docker compose ps`
Expected: `mongo` becomes `healthy` within about 30 s.

- [ ] **Step 2: Write the test fixtures**

`backend/tests/conftest.py`:

```python
import base64
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient

from app.config import Settings
from app.db import ensure_indexes
from app.main import create_app

TEST_MONGODB_URI = os.environ.get(
    "TEST_MONGODB_URI", "mongodb://localhost:27017/?replicaSet=rs0&directConnection=true"
)
TEST_KEY = base64.b64encode(bytes(range(32))).decode()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        mongodb_uri=TEST_MONGODB_URI,
        jwt_secret="t" * 32,
        token_encryption_key=TEST_KEY,
        meta_mode="fake",
        llm_provider="scripted",
    )


@pytest_asyncio.fixture
async def db():
    mongo = AsyncMongoClient(TEST_MONGODB_URI, tz_aware=True)
    name = f"acm_test_{uuid.uuid4().hex[:10]}"
    database = mongo[name]
    await ensure_indexes(database)
    yield database
    await mongo.drop_database(name)
    await mongo.close()


@pytest_asyncio.fixture
async def client(settings, db):
    app = create_app(settings, db=db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c
```

- [ ] **Step 3: Write the failing tests**

`backend/tests/integration/test_db.py`:

```python
import pytest
from pymongo.errors import DuplicateKeyError

from app.db import ensure_indexes


async def test_user_email_is_unique(db):
    await db.users.insert_one({"email": "a@example.com"})
    with pytest.raises(DuplicateKeyError):
        await db.users.insert_one({"email": "a@example.com"})


async def test_insights_unique_per_object_level_day(db):
    row = {"meta_object_id": "1", "level": "ad", "day": "2026-10-01"}
    await db.insights_daily.insert_one(dict(row))
    with pytest.raises(DuplicateKeyError):
        await db.insights_daily.insert_one(dict(row))


async def test_versions_unique_per_campaign(db):
    await db.campaign_versions.insert_one({"campaign_id": 1, "version": 1})
    with pytest.raises(DuplicateKeyError):
        await db.campaign_versions.insert_one({"campaign_id": 1, "version": 1})


async def test_publish_runs_unique_per_campaign_version(db):
    await db.publish_runs.insert_one({"campaign_id": 1, "version": 1})
    with pytest.raises(DuplicateKeyError):
        await db.publish_runs.insert_one({"campaign_id": 1, "version": 1})


async def test_ensure_indexes_is_idempotent(db):
    await ensure_indexes(db)  # second run must not raise


async def test_replica_set_supports_transactions(db):
    async def txn(session):
        await db.users.insert_one({"email": "t@example.com"}, session=session)

    async with db.client.start_session() as session:
        await session.with_transaction(txn)
    assert await db.users.count_documents({"email": "t@example.com"}) == 1
```

`backend/tests/api/test_health.py`:

```python
async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: Run the tests and watch them fail**

Run: `cd backend && uv run pytest tests/integration/test_db.py tests/api/test_health.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'app.db'`.

- [ ] **Step 5: Write the minimal implementation**

`backend/app/db.py`:

```python
from pymongo import AsyncMongoClient

from app.config import Settings

INDEXES: dict[str, list[tuple[list[tuple[str, int]], dict]]] = {
    "users": [([("email", 1)], {"unique": True})],
    "meta_connections": [([("user_id", 1)], {})],
    "campaigns": [([("user_id", 1), ("status", 1)], {})],
    "campaign_versions": [([("campaign_id", 1), ("version", 1)], {"unique": True})],
    "messages": [([("campaign_id", 1), ("created_at", 1)], {})],
    "approvals": [([("campaign_id", 1), ("action", 1)], {})],
    "publish_runs": [([("campaign_id", 1), ("version", 1)], {"unique": True})],
    "insights_daily": [
        ([("meta_object_id", 1), ("level", 1), ("day", 1)], {"unique": True}),
        ([("campaign_id", 1), ("day", 1)], {}),
    ],
    "analysis_reports": [([("campaign_id", 1), ("created_at", 1)], {})],
    "optimization_proposals": [([("campaign_id", 1), ("status", 1)], {})],
    "agent_runs": [([("campaign_id", 1), ("created_at", 1)], {})],
    "audit_log": [([("campaign_id", 1), ("ts", 1)], {}), ([("correlation_id", 1)], {})],
}


def connect(settings: Settings) -> AsyncMongoClient:
    return AsyncMongoClient(settings.mongodb_uri, tz_aware=True)


async def ensure_indexes(db) -> None:
    for collection, specs in INDEXES.items():
        for keys, options in specs:
            await db[collection].create_index(keys, **options)
```

`backend/app/main.py`:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.db import connect, ensure_indexes


def create_app(settings: Settings | None = None, db=None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        mongo = None
        if app.state.db is None:
            mongo = connect(settings)
            app.state.db = mongo[settings.mongodb_db]
            await ensure_indexes(app.state.db)
        yield
        if mongo is not None:
            await mongo.close()

    app = FastAPI(title="Ad Campaign Manager", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app
```

Create empty `backend/tests/integration/__init__.py` and `backend/tests/api/__init__.py`.

- [ ] **Step 6: Run the tests and watch them pass**

Run: `cd backend && uv run pytest tests/integration/test_db.py tests/api/test_health.py -v`
Expected: 7 passed.

Manual check: `cp .env.example backend/.env`, then `cd backend && uv run uvicorn app.main:create_app --factory --reload`, then open `http://localhost:8000/health`. It should return `{"status":"ok"}`.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml backend/app/db.py backend/app/main.py backend/tests
git commit -m "feat: MongoDB replica set, indexes, per-test database and app factory"
```

---

### Task 3: Injectable Clock

> **Understand this task:** a lot of this product depends on time: campaign start and end dates, "the last 3 days" of metrics, token expiry, "7 days later". If code calls `datetime.now()` directly, tests can't control time. Instead every service receives a `Clock`: the real one in production, a `FixedClock` in tests that we can move forward instantly.

**Files:**
- Create: `backend/app/clock.py`
- Test: `backend/tests/unit/test_clock.py`

**Interfaces:**
- Produces: `Clock` (Protocol with `now()`), `SystemClock`, `FixedClock(start)` with `advance(**timedelta_kwargs)`, `utcnow() -> datetime`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import UTC, datetime, timedelta

import pytest

from app.clock import FixedClock, SystemClock, utcnow


def test_system_clock_is_timezone_aware():
    assert SystemClock().now().tzinfo is not None
    assert utcnow().tzinfo is not None


def test_fixed_clock_returns_start_and_advances():
    start = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)
    clock = FixedClock(start)
    assert clock.now() == start
    clock.advance(days=7, hours=1)
    assert clock.now() == start + timedelta(days=7, hours=1)


def test_fixed_clock_rejects_naive_datetime():
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 10, 6))
```

- [ ] **Step 2: Run and watch it fail**

Run: `uv run pytest tests/unit/test_clock.py -v` → FAIL (`No module named 'app.clock'`).

- [ ] **Step 3: Implement**

```python
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


def utcnow() -> datetime:
    return datetime.now(UTC)


class SystemClock:
    def now(self) -> datetime:
        return utcnow()


class FixedClock:
    def __init__(self, start: datetime):
        if start.tzinfo is None:
            raise ValueError("FixedClock needs a timezone-aware datetime")
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now += timedelta(**kwargs)
```

- [ ] **Step 4: Run and watch it pass** — `uv run pytest tests/unit/test_clock.py -v` → 3 passed.

- [ ] **Step 5: Commit** — `git add backend/app/clock.py backend/tests/unit/test_clock.py && git commit -m "feat: injectable clock"`

---

### Task 4: Correlation IDs and the Audit Log

> **Understand this task:**
> - **Correlation ID:** one random id per HTTP request, put in every log line and every audit entry for that request and returned in the `X-Correlation-ID` header. When something goes wrong, you search one id and see the whole story: the request, the model calls, the Meta calls. Incoming ids are accepted only if they look safe (letters, digits, dashes), so nobody can inject text into our logs.
> - **Audit log:** a permanent, insert-only history of important actions (who, what, when). It is how we *prove* to evaluators that nothing was published without approval. An architecture test makes sure no other module writes to it.

**Files:**
- Create: `backend/app/observability.py`, `backend/app/audit.py`
- Modify: `backend/app/main.py` (add the middleware and logging setup)
- Test: `backend/tests/integration/test_audit.py`, `backend/tests/unit/test_observability.py`, `backend/tests/api/test_correlation_id.py`, `backend/tests/unit/test_architecture.py`

**Interfaces:**
- Consumes: `utcnow()` (Task 3)
- Produces: `correlation_id_var`, `CorrelationIdMiddleware`, `add_correlation_id(logger, method, event)`, `configure_logging(app_env)`, `ACTORS`, `async record(db, *, actor, event_type, payload, user_id=None, campaign_id=None, session=None)`

- [ ] **Step 1: Write the failing tests**

`backend/tests/integration/test_audit.py`:

```python
import pytest

from app.audit import record
from app.observability import correlation_id_var


async def test_record_inserts_event_with_correlation_id(db):
    token = correlation_id_var.set("cid-123")
    try:
        await record(db, actor="system", event_type="TEST_EVENT", payload={"k": 1})
    finally:
        correlation_id_var.reset(token)
    doc = await db.audit_log.find_one({"event_type": "TEST_EVENT"})
    assert doc["actor"] == "system"
    assert doc["payload"] == {"k": 1}
    assert doc["correlation_id"] == "cid-123"
    assert doc["ts"].tzinfo is not None


async def test_record_rejects_unknown_actor(db):
    with pytest.raises(ValueError):
        await record(db, actor="model", event_type="X", payload={})
```

`backend/tests/unit/test_observability.py`:

```python
from app.observability import add_correlation_id, correlation_id_var


def test_processor_adds_correlation_id_when_set():
    token = correlation_id_var.set("abc")
    try:
        assert add_correlation_id(None, "info", {"event": "x"})["correlation_id"] == "abc"
    finally:
        correlation_id_var.reset(token)


def test_processor_leaves_event_alone_when_unset():
    assert "correlation_id" not in add_correlation_id(None, "info", {"event": "x"})
```

`backend/tests/api/test_correlation_id.py`:

```python
async def test_generated_correlation_id_is_returned(client):
    response = await client.get("/health")
    assert len(response.headers["x-correlation-id"]) == 32


async def test_safe_incoming_correlation_id_is_echoed(client):
    response = await client.get("/health", headers={"X-Correlation-ID": "req-42"})
    assert response.headers["x-correlation-id"] == "req-42"


async def test_unsafe_incoming_correlation_id_is_replaced(client):
    response = await client.get("/health", headers={"X-Correlation-ID": "bad id\nINJECTED"})
    assert response.headers["x-correlation-id"] != "bad id\nINJECTED"
    assert len(response.headers["x-correlation-id"]) == 32
```

`backend/tests/unit/test_architecture.py`:

```python
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def _sources():
    return {p: p.read_text(encoding="utf-8") for p in APP.rglob("*.py")}


def test_only_audit_module_touches_audit_log():
    allowed = {APP / "audit.py", APP / "db.py"}
    offenders = [str(p) for p, src in _sources().items() if p not in allowed and "audit_log" in src]
    assert offenders == []


def test_no_direct_datetime_now_outside_clock():
    offenders = [str(p) for p, src in _sources().items() if p.name != "clock.py" and "datetime.now(" in src]
    assert offenders == []
```

- [ ] **Step 2: Run and watch them fail**

Run: `uv run pytest tests/integration/test_audit.py tests/unit/test_observability.py tests/api/test_correlation_id.py tests/unit/test_architecture.py -v`
Expected: import errors for `app.audit` / `app.observability`, and a `KeyError: 'x-correlation-id'`. The architecture tests pass already (that's fine; they guard future code).

- [ ] **Step 3: Implement**

`backend/app/observability.py`:

```python
import logging
import re
import uuid
from contextvars import ContextVar

import structlog

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_SAFE_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


class CorrelationIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        incoming = dict(scope["headers"]).get(b"x-correlation-id", b"").decode("latin-1")
        cid = incoming if _SAFE_ID.fullmatch(incoming) else uuid.uuid4().hex
        token = correlation_id_var.set(cid)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-correlation-id", cid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            correlation_id_var.reset(token)


def add_correlation_id(logger, method, event: dict) -> dict:
    cid = correlation_id_var.get()
    if cid:
        event["correlation_id"] = cid
    return event


def configure_logging(app_env: str) -> None:
    renderer = structlog.dev.ConsoleRenderer() if app_env == "development" else structlog.processors.JSONRenderer()
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            add_correlation_id,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
```

`backend/app/audit.py`:

```python
from app.clock import utcnow
from app.observability import correlation_id_var

ACTORS = ("user", "agent", "system")


async def record(db, *, actor: str, event_type: str, payload: dict,
                 user_id=None, campaign_id=None, session=None) -> None:
    if actor not in ACTORS:
        raise ValueError(f"unknown actor {actor!r}")
    await db.audit_log.insert_one(
        {
            "ts": utcnow(),
            "actor": actor,
            "event_type": event_type,
            "payload": payload,
            "user_id": user_id,
            "campaign_id": campaign_id,
            "correlation_id": correlation_id_var.get(),
        },
        session=session,
    )
```

Modify `backend/app/main.py`: import `CorrelationIdMiddleware` and `configure_logging`; inside `create_app`, after creating `app`, add:

```python
    configure_logging(settings.app_env)
    app.add_middleware(CorrelationIdMiddleware)
```

- [ ] **Step 4: Run and watch them pass** — same command → all passed.

- [ ] **Step 5: Commit** — `git add backend && git commit -m "feat: correlation ids and append-only audit log"`

---

### Task 5: Password Hashing and JWT

> **Understand this task:**
> - **Passwords:** we store an argon2 *hash*, never the password itself. Even if the database leaks, passwords don't. This is our app's own login; we never ask for Instagram or Facebook passwords (NFR-1).
> - **JWT:** after login, the server gives the browser a signed token saying "this is user X, valid for 12 h". The signature means the browser can't change it. It lives in an HttpOnly cookie, so JavaScript (and any injected script) can't read it.

**Files:**
- Create: `backend/app/security/__init__.py`, `backend/app/security/passwords.py`, `backend/app/security/jwt.py`
- Test: `backend/tests/unit/test_passwords.py`, `backend/tests/unit/test_jwt.py`

**Interfaces:**
- Produces: `hash_password(plain) -> str`, `verify_password(hashed, plain) -> bool`, `InvalidToken`, `issue_token(subject, secret, ttl_minutes=720, *, extra=None) -> str`, `decode_token(token, secret) -> dict`

- [ ] **Step 1: Write the failing tests**

`backend/tests/unit/test_passwords.py`:

```python
from app.security.passwords import hash_password, verify_password


def test_hash_is_not_the_password_and_verifies():
    hashed = hash_password("correct horse battery")
    assert hashed != "correct horse battery"
    assert verify_password(hashed, "correct horse battery")


def test_wrong_password_is_false():
    assert not verify_password(hash_password("correct horse battery"), "wrong")


def test_same_password_hashes_differently():
    assert hash_password("same password!") != hash_password("same password!")


def test_garbage_hash_is_false_not_error():
    assert not verify_password("not-a-hash", "anything")
```

`backend/tests/unit/test_jwt.py`:

```python
import pytest

from app.security.jwt import InvalidToken, decode_token, issue_token

SECRET = "x" * 32


def test_roundtrip_returns_subject():
    assert decode_token(issue_token("user-1", SECRET), SECRET)["sub"] == "user-1"


def test_extra_claims_are_kept():
    assert decode_token(issue_token("u", SECRET, extra={"nonce": "n1"}), SECRET)["nonce"] == "n1"


def test_expired_token_is_rejected():
    with pytest.raises(InvalidToken):
        decode_token(issue_token("user-1", SECRET, ttl_minutes=-1), SECRET)


def test_token_signed_with_other_secret_is_rejected():
    with pytest.raises(InvalidToken):
        decode_token(issue_token("user-1", "y" * 32), SECRET)


def test_garbage_token_is_rejected():
    with pytest.raises(InvalidToken):
        decode_token("not.a.jwt", SECRET)
```

- [ ] **Step 2: Run and watch them fail** — `uv run pytest tests/unit/test_passwords.py tests/unit/test_jwt.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`backend/app/security/__init__.py`: empty.

`backend/app/security/passwords.py`:

```python
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(hashed: str, plain: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerificationError, InvalidHashError):
        return False
```

`backend/app/security/jwt.py`:

```python
from datetime import timedelta

import jwt

from app.clock import utcnow


class InvalidToken(Exception):
    pass


def issue_token(subject: str, secret: str, ttl_minutes: int = 720, *, extra: dict | None = None) -> str:
    now = utcnow()
    claims = {"sub": subject, "iat": now, "exp": now + timedelta(minutes=ttl_minutes), **(extra or {})}
    return jwt.encode(claims, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
```

- [ ] **Step 4: Run and watch them pass** → 9 passed.

- [ ] **Step 5: Commit** — `git add backend/app/security backend/tests/unit && git commit -m "feat: argon2 password hashing and HS256 session tokens"`

---

### Task 6: Error Envelope, Auth API and Rate Limiter

> **Understand this task:**
> - **Error envelope:** every error looks the same (`{"error": {"code", "message", "details"}}`), so the frontend has one way to show errors and tests can assert on stable `code`s instead of wording.
> - **`AppError` subclasses** carry their own HTTP status and code. Later milestones add more (`IllegalTransition`, `ApprovalError` …) and they work automatically (Open/Closed).
> - **Login security:** the same message for "no such email" and "wrong password" (don't reveal who has an account), a dummy hash check when the email doesn't exist (so response timing doesn't reveal it either), and a rate limit of 10 attempts per minute per IP.

**Files:**
- Create: `backend/app/errors.py`, `backend/app/api/__init__.py`, `backend/app/api/deps.py`, `backend/app/api/auth.py`
- Modify: `backend/app/main.py` (handlers, router, limiter)
- Test: `backend/tests/unit/test_rate_limiter.py`, `backend/tests/api/test_auth.py`

**Interfaces:**
- Consumes: `record` (Task 4), `hash_password`/`verify_password`/`issue_token`/`decode_token` (Task 5), `utcnow` (Task 3)
- Produces: `AppError(message="", details=None)` with `.status`, `.code`; `NotFound`, `Unauthenticated`, `EmailTaken`, `RateLimited`; `install_error_handlers(app)`; `get_db(request)`, `get_settings_dep(request)`, `async current_user(...) -> dict`; `RateLimiter(limit, window_s, clock=time.monotonic).hit(key)`; `SESSION_COOKIE = "session"`

- [ ] **Step 1: Write the failing tests**

`backend/tests/unit/test_rate_limiter.py`:

```python
import pytest

from app.api.deps import RateLimiter
from app.errors import RateLimited


def test_blocks_after_limit_and_resets_after_window():
    now = [0.0]
    limiter = RateLimiter(limit=2, window_s=60, clock=lambda: now[0])
    limiter.hit("ip")
    limiter.hit("ip")
    with pytest.raises(RateLimited):
        limiter.hit("ip")
    now[0] = 61.0
    limiter.hit("ip")  # new window


def test_keys_are_independent():
    limiter = RateLimiter(limit=1, window_s=60, clock=lambda: 0.0)
    limiter.hit("a")
    limiter.hit("b")
```

`backend/tests/api/test_auth.py`:

```python
async def register(client, email="dev@example.com", password="long-enough-pw"):
    return await client.post("/auth/register", json={"email": email, "password": password})


async def login(client, email="dev@example.com", password="long-enough-pw"):
    return await client.post("/auth/login", json={"email": email, "password": password})


async def test_register_creates_user_with_hashed_password(client, db):
    response = await register(client)
    assert response.status_code == 201
    user = await db.users.find_one({"email": "dev@example.com"})
    assert user["password_hash"] != "long-enough-pw"


async def test_register_lowercases_email(client, db):
    await register(client, email="Dev@Example.com")
    assert await db.users.find_one({"email": "dev@example.com"})


async def test_duplicate_email_is_409_with_envelope(client):
    await register(client)
    response = await register(client)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_short_password_is_422_with_envelope(client):
    response = await register(client, password="short")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_login_sets_httponly_lax_session_cookie(client):
    await register(client)
    response = await login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("session=")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


async def test_wrong_password_and_unknown_email_look_the_same(client):
    await register(client)
    wrong = await login(client, password="wrong-password")
    unknown = await login(client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_me_requires_a_session(client):
    response = await client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_me_returns_user_after_login(client):
    await register(client)
    await login(client)
    response = await client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "dev@example.com"


async def test_logout_clears_session(client):
    await register(client)
    await login(client)
    await client.post("/auth/logout")
    assert (await client.get("/auth/me")).status_code == 401


async def test_login_is_rate_limited(client):
    await register(client)
    for _ in range(10):
        await login(client, password="wrong-password")
    response = await login(client, password="wrong-password")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


async def test_register_and_login_are_audited(client, db):
    await register(client)
    await login(client)
    events = [e["event_type"] async for e in db.audit_log.find({}, {"event_type": 1})]
    assert events == ["USER_REGISTERED", "USER_LOGIN"]
```

- [ ] **Step 2: Run and watch them fail** — `uv run pytest tests/unit/test_rate_limiter.py tests/api/test_auth.py -v` → import errors and 404s.

- [ ] **Step 3: Implement**

`backend/app/errors.py`:

```python
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    status: int = 500
    code: str = "INTERNAL"

    def __init__(self, message: str = "", details: dict | None = None):
        super().__init__(message)
        self.message = message or self.code
        self.details = details or {}


class NotFound(AppError):
    status, code = 404, "NOT_FOUND"


class Unauthenticated(AppError):
    status, code = 401, "UNAUTHENTICATED"


class EmailTaken(AppError):
    status, code = 409, "EMAIL_TAKEN"


class RateLimited(AppError):
    status, code = 429, "RATE_LIMITED"


def _envelope(code: str, message: str, details: dict, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": details}}, status_code=status)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return _envelope(exc.code, exc.message, exc.details, exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _envelope("VALIDATION_FAILED", "Request validation failed", {"errors": errors}, 422)
```

`backend/app/api/__init__.py`: empty.

`backend/app/api/deps.py`:

```python
import time
from collections.abc import Callable

from bson import ObjectId
from fastapi import Depends, Request

from app.config import Settings
from app.errors import RateLimited, Unauthenticated
from app.security.jwt import InvalidToken, decode_token

SESSION_COOKIE = "session"


def get_db(request: Request):
    return request.app.state.db


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


async def current_user(request: Request, db=Depends(get_db),
                       settings: Settings = Depends(get_settings_dep)) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise Unauthenticated("Not logged in")
    try:
        claims = decode_token(token, settings.jwt_secret)
    except InvalidToken as exc:
        raise Unauthenticated("Session expired, please log in again") from exc
    user = await db.users.find_one({"_id": ObjectId(claims["sub"])})
    if user is None:
        raise Unauthenticated("Not logged in")
    return user


class RateLimiter:
    """Fixed window per key.
    ponytail: in-process, single instance only; move to a shared store if the API is scaled out."""

    def __init__(self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window_s, self._clock = limit, window_s, clock
        self._windows: dict[str, tuple[float, int]] = {}

    def hit(self, key: str) -> None:
        now = self._clock()
        start, count = self._windows.get(key, (now, 0))
        if now - start >= self.window_s:
            start, count = now, 0
        if count >= self.limit:
            raise RateLimited("Too many attempts, try again later",
                              {"retry_after_s": round(self.window_s - (now - start))})
        self._windows[key] = (start, count + 1)
```

`backend/app/api/auth.py`:

```python
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app import audit
from app.api.deps import SESSION_COOKIE, current_user, get_db, get_settings_dep
from app.clock import utcnow
from app.config import Settings
from app.errors import EmailTaken, Unauthenticated
from app.security.jwt import issue_token
from app.security.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_DUMMY_HASH = hash_password("dummy-password-for-timing")


class RegisterBody(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    password: str = Field(min_length=10, max_length=128)


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


def _public(user: dict) -> dict:
    return {"id": str(user["_id"]), "email": user["email"]}


@router.post("/register", status_code=201)
async def register(body: RegisterBody, db=Depends(get_db)) -> dict:
    user = {"email": body.email.lower(), "password_hash": hash_password(body.password), "created_at": utcnow()}
    try:
        await db.users.insert_one(user)
    except DuplicateKeyError as exc:
        raise EmailTaken("This email is already registered") from exc
    await audit.record(db, actor="user", event_type="USER_REGISTERED",
                       payload={"email": user["email"]}, user_id=user["_id"])
    return _public(user)


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response, db=Depends(get_db),
                settings: Settings = Depends(get_settings_dep)) -> dict:
    request.app.state.login_limiter.hit(request.client.host if request.client else "unknown")
    user = await db.users.find_one({"email": body.email.lower()})
    password_ok = verify_password(user["password_hash"] if user else _DUMMY_HASH, body.password)
    if user is None or not password_ok:
        raise Unauthenticated("Invalid email or password")
    response.set_cookie(
        SESSION_COOKIE, issue_token(str(user["_id"]), settings.jwt_secret),
        httponly=True, samesite="lax", secure=settings.app_env == "production", max_age=12 * 3600,
    )
    await audit.record(db, actor="user", event_type="USER_LOGIN", payload={"email": user["email"]},
                       user_id=user["_id"])
    return _public(user)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


@router.get("/me")
async def me(user: dict = Depends(current_user)) -> dict:
    return _public(user)
```

Modify `backend/app/main.py` (inside `create_app`, after the middleware):

```python
    install_error_handlers(app)
    app.state.login_limiter = RateLimiter(limit=10, window_s=60)
    app.include_router(auth.router)
```

with imports `from app.api import auth`, `from app.api.deps import RateLimiter`, `from app.errors import install_error_handlers`.

- [ ] **Step 4: Run and watch them pass**

Run: `uv run pytest tests/unit/test_rate_limiter.py tests/api/test_auth.py -v` → all passed. Then `uv run pytest -q` → whole suite green.

- [ ] **Step 5: Commit** — `git add backend && git commit -m "feat: error envelope, auth API with session cookie and login rate limit"`

---

### Task 7: Token Encryption

> **Understand this task:** in M3 we store each user's Meta access token. If the database leaked, plain tokens would let an attacker run ads on that user's account. AES-256-GCM encrypts the token and also detects tampering: a modified ciphertext fails to decrypt instead of producing garbage. The key comes from an environment variable, never from the database.

**Files:**
- Create: `backend/app/security/crypto.py`
- Test: `backend/tests/unit/test_crypto.py`

**Interfaces:**
- Produces: `encrypt_token(key_b64, plaintext) -> bytes`, `decrypt_token(key_b64, blob) -> str`

- [ ] **Step 1: Write the failing tests**

```python
import base64

import pytest
from cryptography.exceptions import InvalidTag

from app.security.crypto import decrypt_token, encrypt_token

KEY = base64.b64encode(bytes(range(32))).decode()
OTHER_KEY = base64.b64encode(bytes(range(1, 33))).decode()


def test_roundtrip():
    assert decrypt_token(KEY, encrypt_token(KEY, "EAABtoken")) == "EAABtoken"


def test_ciphertext_hides_plaintext_and_differs_each_time():
    a, b = encrypt_token(KEY, "EAABtoken"), encrypt_token(KEY, "EAABtoken")
    assert a != b
    assert b"EAABtoken" not in a


def test_tampered_ciphertext_is_rejected():
    blob = bytearray(encrypt_token(KEY, "EAABtoken"))
    blob[-1] ^= 1
    with pytest.raises(InvalidTag):
        decrypt_token(KEY, bytes(blob))


def test_wrong_key_is_rejected():
    with pytest.raises(InvalidTag):
        decrypt_token(OTHER_KEY, encrypt_token(KEY, "EAABtoken"))


def test_key_must_be_32_bytes():
    with pytest.raises(ValueError):
        encrypt_token(base64.b64encode(bytes(16)).decode(), "x")
```

- [ ] **Step 2: Run and watch them fail** → `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12


def _key(key_b64: str) -> bytes:
    key = base64.b64decode(key_b64)
    if len(key) != 32:
        raise ValueError("TOKEN_ENCRYPTION_KEY must be base64 of exactly 32 bytes")
    return key


def encrypt_token(key_b64: str, plaintext: str) -> bytes:
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + AESGCM(_key(key_b64)).encrypt(nonce, plaintext.encode(), None)


def decrypt_token(key_b64: str, blob: bytes) -> str:
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    return AESGCM(_key(key_b64)).decrypt(nonce, ciphertext, None).decode()
```

- [ ] **Step 4: Run and watch them pass** → 5 passed.

- [ ] **Step 5: Commit** — `git add backend/app/security/crypto.py backend/tests/unit/test_crypto.py && git commit -m "feat: AES-256-GCM token encryption"`

---

### Task 8: Continuous Integration

> **Understand this task:** CI runs the same checks on every push: lint, the full test suite against a real MongoDB replica set, and a secret scan that fails the build if a key or token is committed. "Works on my machine" stops being enough.

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow (config, no test)**

```yaml
name: ci
on: [push, pull_request]

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - name: Start MongoDB replica set
        run: |
          docker run -d --name mongo -p 27017:27017 mongo:8 --replSet rs0 --bind_ip_all
          for i in $(seq 1 30); do
            docker exec mongo mongosh --quiet --eval "try { rs.status().ok } catch (e) { rs.initiate({_id:'rs0',members:[{_id:0,host:'localhost:27017'}]}).ok }" && break
            sleep 2
          done
          until docker exec mongo mongosh --quiet --eval "db.hello().isWritablePrimary" | grep -q true; do sleep 1; done
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run ruff check . && uv run ruff format --check .
      - run: uv run pytest -q

  secrets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 2: Verify locally, then push**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
Expected: no lint errors; all tests pass. Push the branch and confirm both CI jobs are green.

- [ ] **Step 3: Commit** — `git add .github && git commit -m "ci: lint, tests with MongoDB replica set, secret scan"`

---

## Self-Review Checklist (run before marking M1 done)

- [ ] LLD §2–§3 covered: settings ✓, clock ✓, db ✓, observability ✓, audit ✓, errors ✓, passwords ✓, JWT ✓, crypto ✓, rate limiter ✓.
- [ ] PRD NFR-1 (no social passwords; tokens encrypted), NFR-6 (correlation IDs), NFR-8 (runs locally from `.env.example` + compose).
- [ ] Architecture tests pass (audit_log ownership, no `datetime.now(`).
- [ ] `uv run pytest -q` green; Ruff clean; CI green.

## Next

Write and start `02-harness-core.plan.md` (domain rules, state machine, approvals, and the ADK spike).
