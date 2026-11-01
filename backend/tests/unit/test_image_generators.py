from io import BytesIO
from types import SimpleNamespace

import pytest
from google.genai import types
from PIL import Image

from app.domain.media import ImageRejected, check_instagram_image
from app.media.images import (
    FakeImageGenerator,
    GeminiImageGenerator,
    ImageGenerationFailed,
    build_prompt,
    normalize_square,
)


def image_bytes(width: int, height: int, fmt: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "teal").save(buffer, format=fmt)
    return buffer.getvalue()


async def test_fake_generator_is_deterministic_and_square():
    fake = FakeImageGenerator()
    first, again = await fake.generate("Student coding Python"), await fake.generate("Student coding Python")
    assert first == again and first != await fake.generate("Coffee shop")
    assert check_instagram_image(first) == check_instagram_image(again)
    with Image.open(BytesIO(first)) as img:
        assert (img.size, img.format) == ((1080, 1080), "JPEG")
    assert fake.prompts == ["Student coding Python"] * 2 + ["Coffee shop"]


async def test_fake_generator_can_be_told_to_fail():
    with pytest.raises(ImageGenerationFailed):
        await FakeImageGenerator(fail=True).generate("x")


def test_normalize_square_centre_crops_to_1080_jpeg():
    data = normalize_square(image_bytes(1920, 1080))
    info = check_instagram_image(data)
    assert (info.width, info.height, info.format) == (1080, 1080, "JPEG")


def test_normalize_square_rejects_non_images():
    with pytest.raises(ImageRejected):
        normalize_square(b"not an image")


def test_build_prompt_appends_the_instagram_suffix():
    assert build_prompt("A student coding", "blue tones") == (
        "A student coding blue tones "
        "Square 1:1 Instagram ad creative; quoted text exactly once, no other text or watermarks."
    )


def gemini_with(response=None, error: Exception | None = None):
    calls = []

    async def generate_content(*, model, contents):
        calls.append((model, contents))
        if error:
            raise error
        return response

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    return GeminiImageGenerator(api_key="k", model="gemini-2.5-flash-image", client=client), calls


def response_with(*parts: types.Part) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(parts=list(parts)))]
    )


async def test_gemini_returns_the_first_inline_image():
    png = image_bytes(1024, 1024)
    response = response_with(
        types.Part(text="here you go"), types.Part(inline_data=types.Blob(data=png, mime_type="image/png"))
    )
    generator, calls = gemini_with(response)
    assert await generator.generate("a prompt") == png
    assert calls == [("gemini-2.5-flash-image", "a prompt")]


async def test_gemini_without_an_image_fails_clearly():
    generator, _ = gemini_with(response_with(types.Part(text="I can't draw that")))
    with pytest.raises(ImageGenerationFailed, match="no image"):
        await generator.generate("a prompt")


async def test_gemini_sdk_errors_become_image_generation_failed():
    generator, _ = gemini_with(error=RuntimeError("quota exceeded"))
    with pytest.raises(ImageGenerationFailed, match="quota exceeded"):
        await generator.generate("a prompt")


async def test_gemini_without_a_key_fails_before_calling():
    with pytest.raises(ImageGenerationFailed, match="GEMINI_API_KEY"):
        await GeminiImageGenerator(api_key="", model="m").generate("x")


async def test_ai_generator_keeps_the_full_prompt_and_varies_the_seed():
    import httpx
    import respx

    from app.media.images import AIImageGenerator

    prompt = build_prompt("Recruiter smiling at a shortlist on her laptop " * 10)
    with respx.mock:
        route = respx.get(url__startswith="https://image.pollinations.ai/prompt/").mock(
            return_value=httpx.Response(200, content=image_bytes(1080, 1080))
        )
        await AIImageGenerator().generate(prompt)
        await AIImageGenerator().generate(prompt)
    first, second = (call.request.url for call in route.calls)
    assert first.params["seed"] != second.params["seed"]  # "New image" must give a new picture
    sent = first.path.removeprefix("/prompt/")
    assert sent.endswith(", no text") and len(sent) <= 250  # the free endpoint's limit
    assert sent.startswith("Recruiter smiling at a shortlist")


def openai_with(result=None, error=None):
    from app.media.images import OpenAIImageGenerator

    calls = []

    async def generate(**kwargs):
        calls.append(kwargs)
        if error:
            raise error
        return result

    client = SimpleNamespace(images=SimpleNamespace(generate=generate))
    return OpenAIImageGenerator(api_key="k", model="gpt-image-1", client=client), calls


async def test_openai_returns_the_decoded_image_from_the_full_prompt():
    import base64

    png = image_bytes(1024, 1024)
    generator, calls = openai_with(
        SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(png).decode())])
    )
    prompt = build_prompt("A recruiter smiling at a shortlist " * 20)  # long briefs are not cut
    assert await generator.generate(prompt) == png
    assert calls == [{"model": "gpt-image-1", "prompt": prompt, "size": "1024x1024", "n": 1}]


async def test_openai_errors_and_empty_answers_fail_clearly():
    generator, _ = openai_with(error=RuntimeError("insufficient_quota"))
    with pytest.raises(ImageGenerationFailed, match="insufficient_quota"):
        await generator.generate("x")
    generator, _ = openai_with(SimpleNamespace(data=[]))
    with pytest.raises(ImageGenerationFailed, match="returned no image"):
        await generator.generate("x")
