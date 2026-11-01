from app.container import build_container
from app.media.images import FakeImageGenerator, GeminiImageGenerator
from app.meta.fake import FakeAdsGateway
from app.meta.sdk_gateway import MetaSdkGateway
from app.security.crypto import encrypt_token


def test_fake_mode_uses_one_shared_fake(settings):
    container = build_container(settings)
    reader, writer = container.gateway_for({})
    assert isinstance(reader, FakeAdsGateway) and reader is writer
    assert container.gateway_for({})[0] is reader


def test_fake_mode_uses_the_fake_a_test_passes(settings):
    fake = FakeAdsGateway()
    assert build_container(settings, fake_gateway=fake).gateway_for({})[0] is fake


def test_fail_at_setting_is_applied_to_the_fake(settings):
    container = build_container(settings.model_copy(update={"fake_meta_fail_at": "ADSET:timeout"}))
    assert container.gateway_for({})[0].fail_at == {"ADSET": "timeout"}


def test_real_mode_builds_an_sdk_gateway_from_the_decrypted_token(settings):
    real = settings.model_copy(update={"meta_mode": "real", "meta_app_id": "1", "meta_app_secret": "s"})
    connection = {"token_ciphertext": encrypt_token(real.token_encryption_key, "EAAB")}
    reader, writer = build_container(real).gateway_for(connection)
    assert isinstance(reader, MetaSdkGateway) and reader is writer
    assert reader._api._session.access_token == "EAAB"


def test_image_provider_picks_the_generator(settings):
    assert isinstance(build_container(settings).image_generator, FakeImageGenerator)
    gemini = settings.model_copy(update={"image_provider": "gemini", "gemini_api_key": "k"})
    generator = build_container(gemini).image_generator
    assert isinstance(generator, GeminiImageGenerator) and generator.model == settings.image_model
    openai = settings.model_copy(update={"image_provider": "openai", "openai_api_key": "k"})
    generator = build_container(openai).image_generator
    assert (
        type(generator).__name__ == "OpenAIImageGenerator" and generator.model == settings.openai_image_model
    )


async def test_background_spawn_runs_the_coroutine(settings):
    import asyncio

    done = asyncio.Event()

    async def job():
        done.set()

    await build_container(settings).spawn(job())
    await asyncio.wait_for(done.wait(), timeout=1)
