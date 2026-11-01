import base64
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient
from tenacity import wait_none

# litellm copies the developer's .env into os.environ on first import (DEV mode); keep tests isolated from it.
os.environ.setdefault("LITELLM_MODE", "PRODUCTION")

from app.clock import FixedClock
from app.config import Settings
from app.container import build_container
from app.db import ensure_indexes
from app.main import create_app
from app.media.images import FakeImageGenerator
from app.meta.fake import FakeAdsGateway

TEST_MONGODB_URI = os.environ.get("TEST_MONGODB_URI", "mongodb://localhost:27017")
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
        allow_real_ad_spend=True,  # publishing starts live delivery; blocked-default tests turn it off
        safe_mode_no_spend=False,
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


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 10, 6, 9, 0, tzinfo=UTC))


@pytest.fixture
def fake_gateway() -> FakeAdsGateway:
    return FakeAdsGateway()


@pytest.fixture
def image_generator() -> FakeImageGenerator:
    return FakeImageGenerator()


async def run_inline(coro) -> None:
    await coro


@pytest.fixture
def container(settings, clock, fake_gateway, image_generator):
    """Fakes everywhere; background jobs run inline and Meta retries don't sleep."""
    return build_container(
        settings,
        clock=clock,
        fake_gateway=fake_gateway,
        image_generator=image_generator,
        spawn=run_inline,
        retry_wait=wait_none(),
    )


@pytest.fixture
def make_client(settings, db, clock, fake_gateway, image_generator):
    """`async with make_client(meta_mode="real") as c:` builds an app with overridden settings."""

    @asynccontextmanager
    async def _make(**setting_overrides):
        app_settings = settings.model_copy(update=setting_overrides)
        container = build_container(
            app_settings,
            clock=clock,
            fake_gateway=fake_gateway,
            image_generator=image_generator,
            spawn=run_inline,
            retry_wait=wait_none(),
        )
        app = create_app(app_settings, db=db, container=container)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            yield c

    return _make


@pytest_asyncio.fixture
async def client(make_client):
    async with make_client() as c:
        yield c
