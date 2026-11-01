import asyncio
from contextlib import asynccontextmanager

# Trigger reload to load updated MONGODB_URI
from fastapi import FastAPI

from app.api import auth, campaigns, dm, hashtags, media, meta_oauth, organic, social_knowledge, webhooks
from app.api import settings as user_settings
from app.api.deps import RateLimiter
from app.config import Settings, get_settings
from app.container import Container, build_container
from app.db import connect, ensure_indexes
from app.errors import install_error_handlers
from app.meta.publisher import recover_interrupted
from app.observability import CorrelationIdMiddleware, configure_logging
from app.services.insights import refresh_all_active


def create_app(
    settings: Settings | None = None,
    db=None,
    container: Container | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        mongo = None
        if app.state.db is None:
            mongo = connect(settings)
            app.state.db = mongo[settings.mongodb_db]
            await ensure_indexes(app.state.db)
        await recover_interrupted(app.state.db, clock=app.state.container.clock)

        async def _insights_loop():
            interval_s = max(60, settings.insights_interval_hours * 3600)
            while True:
                try:
                    await asyncio.sleep(interval_s)
                    await refresh_all_active(app.state.db, app.state.container)
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass

        loop_task = asyncio.create_task(_insights_loop())
        try:
            yield
        finally:
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
            if mongo is not None:
                await mongo.close()

    app = FastAPI(title="Ad Campaign Manager", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.container = container or build_container(settings)

    configure_logging(settings.app_env)
    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)
    app.state.login_limiter = RateLimiter(limit=10, window_s=60)
    app.include_router(auth.router)
    app.include_router(user_settings.router)
    app.include_router(meta_oauth.router)
    app.include_router(campaigns.router)
    app.include_router(media.router)
    app.include_router(dm.router)
    app.include_router(organic.router)
    app.include_router(organic.public_router)
    app.include_router(hashtags.router)
    app.include_router(webhooks.router)
    app.include_router(social_knowledge.router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


def __getattr__(name: str):
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
