"""Real OpenRouter call per model family. Opt in:

    RUN_LIVE_OPENROUTER=1 OPENROUTER_API_KEY=... uv run pytest tests/live/test_openrouter_live.py -s

One key, both families: the same key serves Gemini and OpenAI models.
"""

import os

import pytest

from app.agents.ad_drafter import draft_ad
from app.agents.dm_agent import answer_dm
from app.meta.fake import FakeAdsGateway
from tests.api.test_ad_studio_api import IDEA

KEY = os.environ.get("OPENROUTER_API_KEY", "")
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_OPENROUTER") != "1" or not KEY,
    reason="set RUN_LIVE_OPENROUTER=1 and OPENROUTER_API_KEY",
)
KNOWLEDGE = {
    "business_name": "Priya Bakery",
    "tone": "Warm and short",
    "knowledge": "Open 9am-6pm Mon-Sat. Birthday cakes from Rs 800, order 2 days ahead.",
}


def through_openrouter(settings, family):
    return settings.model_copy(
        update={"llm_provider": "openrouter", "openrouter_api_key": KEY, "openrouter_model_family": family}
    )


@pytest.mark.parametrize("family", ["gemini", "openai"])
async def test_ad_draft_through_openrouter(settings, clock, family):
    """The big prompt on the primary model with strict JSON output: the path most likely to differ."""
    result = await draft_ad(
        IDEA, settings=through_openrouter(settings, family), clock=clock, reader=FakeAdsGateway()
    )
    headlines = [v["headline"] for v in result.fields["variants"]]
    print(f"\nOPENROUTER {family} AD DRAFT:", ascii(result.fields["title"]), ascii(headlines))
    assert len(headlines) >= 2 and result.extra["image_prompt"]


@pytest.mark.parametrize("family", ["gemini", "openai"])
async def test_dm_answer_through_openrouter(settings, family):
    live = settings.model_copy(
        update={"llm_provider": "openrouter", "openrouter_api_key": KEY, "openrouter_model_family": family}
    )
    answer = await answer_dm(
        knowledge=KNOWLEDGE,
        history=[],
        message="What time do you open and how much is a cake?",
        settings=live,
    )
    print(f"\nOPENROUTER {family} REPLY:", ascii(answer.text))
    assert not answer.needs_human and "800" in answer.text
