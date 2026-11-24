import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass

from app.clock import Clock, SystemClock
from app.config import Settings
from app.media.images import FakeImageGenerator, GeminiImageGenerator, ImageGenerator, OpenAIImageGenerator
from app.meta.errors import DEFAULT_WAIT
from app.meta.fake import FakeAdsGateway, parse_fail_at
from app.meta.ports import AdsReader, AdsWriter
from app.meta.sdk_gateway import MetaSdkGateway
from app.security.crypto import decrypt_token

Spawn = Callable[[Coroutine], Awaitable[None]]


def background_spawner() -> Spawn:
    running: set[asyncio.Task] = set()

    async def spawn(coro: Coroutine) -> None:
        task = asyncio.create_task(coro)
        running.add(task)  # keep a reference so the task isn't garbage-collected mid-run
        task.add_done_callback(running.discard)

    return spawn


@dataclass
class Container:
    settings: Settings
    clock: Clock
    gateway_for: Callable[[dict], tuple[AdsReader, AdsWriter]]  # meta connection -> (reader, writer)
    image_generator: ImageGenerator
    spawn: Spawn  # runs background jobs (publishing); tests run them inline
    retry_wait: object = DEFAULT_WAIT  # tenacity wait for Meta write retries; tests use wait_none()


def build_meta_gateway(
    settings: Settings, *, access_token: str, mode: str
) -> tuple[AdsReader, AdsWriter]:
    """Construct a Meta gateway from container.py to keep gateway instantiation centralized."""
    if mode == "fake" or settings.meta_mode == "fake":
        fake = FakeAdsGateway(fail_at=parse_fail_at(settings.fake_meta_fail_at))
        return fake, fake
    gateway = MetaSdkGateway(access_token=access_token, settings=settings)
    return gateway, gateway


def build_container(
    settings: Settings,
    *,
    clock: Clock | None = None,
    fake_gateway: FakeAdsGateway | None = None,
    image_generator: ImageGenerator | None = None,
    spawn: Spawn | None = None,
    retry_wait=DEFAULT_WAIT,
) -> Container:
    clock = clock or SystemClock()
    common = {"spawn": spawn or background_spawner(), "retry_wait": retry_wait}
    if image_generator is None:
        if settings.image_provider == "openai":
            image_generator = OpenAIImageGenerator(
                api_key=settings.openai_api_key,
                model=settings.openai_image_model,
                quality=settings.openai_image_quality,
            )
        elif settings.image_provider in ("gemini", "ai"):
            image_generator = GeminiImageGenerator(
                api_key=settings.gemini_api_key, model=settings.image_model
            )
        else:
            image_generator = FakeImageGenerator()
    if settings.meta_mode == "fake":
        fake = fake_gateway or FakeAdsGateway(fail_at=parse_fail_at(settings.fake_meta_fail_at))
        return Container(
            settings=settings,
            clock=clock,
            gateway_for=lambda connection: (fake, fake),
            image_generator=image_generator,
            **common,
        )

    def real_gateway(connection: dict) -> tuple[AdsReader, AdsWriter]:
        if connection.get("mode") == "fake":
            fake = fake_gateway or FakeAdsGateway(fail_at=parse_fail_at(settings.fake_meta_fail_at))
            return fake, fake
        token = decrypt_token(settings.token_encryption_key, connection["token_ciphertext"])
        gateway = MetaSdkGateway(access_token=token, settings=settings)
        return gateway, gateway

    return Container(
        settings=settings, clock=clock, gateway_for=real_gateway, image_generator=image_generator, **common
    )
