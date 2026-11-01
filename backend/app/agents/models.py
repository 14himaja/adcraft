import json
from pathlib import Path
from typing import Literal

from google.adk.models.base_llm import BaseLlm
from google.adk.models.lite_llm import LiteLlm

from app.agents.scripted_model import ScriptedModel
from app.config import Settings

SCENARIOS = Path(__file__).parent / "scenarios"


def load_scenario(name: str) -> dict[str, list[dict]]:
    return json.loads((SCENARIOS / f"{name}.json").read_text(encoding="utf-8"))


def make_model(
    settings: Settings,
    *,
    role: Literal["primary", "utility"],
    agent_name: str,
    scenario: dict | None = None,
) -> BaseLlm:
    if settings.llm_provider == "scripted":
        script = scenario if scenario is not None else load_scenario(settings.scripted_scenario)
        return ScriptedModel(model=f"scripted/{agent_name}", responses=list(script.get(agent_name, [])))
    primary = role == "primary"
    if settings.llm_provider == "openrouter":
        pair = "primary" if primary else "utility"
        name = getattr(settings, f"openrouter_{settings.openrouter_model_family}_{pair}_model")
        key = settings.openrouter_api_key
        extra = {"api_key": key} if key else {}
        return LiteLlm(model=f"openrouter/{name}", max_tokens=settings.openrouter_max_tokens, **extra)
    name = settings.llm_primary_model if primary else settings.llm_utility_model
    if settings.llm_provider == "gemini":
        prefix, key = "gemini", settings.gemini_api_key
        if not name.startswith("gemini"):  # provider switched to Gemini while .env still names a GPT model
            name = settings.gemini_primary_model if primary else settings.gemini_utility_model
    else:
        prefix, key = "openai", settings.openai_api_key
    # Keys come from Settings (.env), which LiteLLM can't see in os.environ, so pass them explicitly.
    return LiteLlm(model=f"{prefix}/{name}", **({"api_key": key} if key else {}))
