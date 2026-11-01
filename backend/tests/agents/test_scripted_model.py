import pytest
from google.adk import Agent, Workflow
from google.adk.models.lite_llm import LiteLlm
from pydantic import BaseModel

from app.agents.errors import ModelUnavailable
from app.agents.models import load_scenario, make_model
from app.agents.scripted_model import ScriptedModel, ScriptExhausted
from tests.agents.adk_helpers import run_root


class Greeting(BaseModel):
    text: str


async def test_text_reply_reaches_the_next_node():
    seen = []
    agent = Agent(
        name="greeter",
        model=ScriptedModel(model="scripted/greeter", responses=[{"text": "hi"}]),
        instruction="Say hi.",
    )

    def capture(node_input):
        seen.append(node_input)

    await run_root(Workflow(name="wf", edges=[("START", agent, capture)]))
    assert "hi" in str(seen[0])


async def test_json_reply_is_parsed_by_output_schema():
    agent = Agent(
        name="greeter",
        model=ScriptedModel(model="scripted/greeter", responses=[{"json": {"text": "hi"}}]),
        instruction="Greet.",
        output_schema=Greeting,
        output_key="greeting",
    )
    _, session = await run_root(agent)
    assert Greeting.model_validate(session.state["greeting"]).text == "hi"


async def test_tool_call_runs_the_tool_then_replies():
    called = []

    def lookup(query: str) -> dict:
        """Look something up."""
        called.append(query)
        return {"result": "found"}

    model = ScriptedModel(
        model="scripted/t",
        responses=[
            {"tool_call": {"name": "lookup", "args": {"query": "python"}}},
            {"text": "done"},
        ],
    )
    await run_root(Agent(name="t", model=model, instruction="Use tools.", tools=[lookup]))
    assert called == ["python"]


async def test_every_request_is_recorded():
    model = ScriptedModel(model="scripted/greeter", responses=[{"text": "hi"}])
    await run_root(Agent(name="greeter", model=model, instruction="Say hi."))
    assert len(model.requests) == 1


async def test_exhausted_script_fails_loudly():
    with pytest.raises(ScriptExhausted):
        await run_root(
            Agent(name="g", model=ScriptedModel(model="scripted/g", responses=[]), instruction="x")
        )


async def test_scripted_outage_raises_model_unavailable():
    model = ScriptedModel(model="scripted/g", responses=[{"error": "unavailable"}])
    with pytest.raises(ModelUnavailable):
        await run_root(Agent(name="g", model=model, instruction="x"))


def test_load_scenario_reads_packaged_json():
    assert load_scenario("smoke") == {"greeter": [{"text": "hello from scenario"}]}


def test_make_model_scripted_uses_the_agents_script(settings):
    model = make_model(settings, role="primary", agent_name="greeter", scenario={"greeter": [{"text": "x"}]})
    assert isinstance(model, ScriptedModel) and model.responses == [{"text": "x"}]


def test_make_model_litellm_uses_configured_openai_model(settings):
    real = settings.model_copy(update={"llm_provider": "litellm"})
    assert isinstance(make_model(real, role="primary", agent_name="a"), LiteLlm)
    assert make_model(real, role="primary", agent_name="a").model == "openai/gpt-5"
    assert make_model(real, role="utility", agent_name="a").model == "openai/gpt-5"


def test_make_model_gemini_uses_gemini_prefix_and_key_from_settings(settings):
    gemini = settings.model_copy(
        update={
            "llm_provider": "gemini",
            "llm_primary_model": "gemini-2.5-flash",
            "gemini_api_key": "test-key",
        }
    )
    model = make_model(gemini, role="primary", agent_name="a")
    assert model.model == "gemini/gemini-2.5-flash"
    assert model._additional_args["api_key"] == "test-key"  # .env values are not in os.environ


def test_gemini_provider_swaps_a_gpt_model_name_for_the_gemini_default(settings):
    gemini = settings.model_copy(update={"llm_provider": "gemini", "gemini_api_key": "k"})
    assert gemini.llm_primary_model.startswith("gpt")
    assert make_model(gemini, role="primary", agent_name="a").model == f"gemini/{gemini.gemini_primary_model}"
    assert make_model(gemini, role="utility", agent_name="a").model == f"gemini/{gemini.gemini_utility_model}"


def openrouter(settings, **changes):
    base = {"llm_provider": "openrouter", "openrouter_api_key": "or-key"}
    return settings.model_copy(update=base | changes)


@pytest.mark.parametrize(
    ("family", "role", "expected"),
    [
        ("gemini", "primary", "openrouter/google/gemini-3.5-flash-lite"),
        ("gemini", "utility", "openrouter/google/gemini-3.5-flash-lite"),
        ("openai", "primary", "openrouter/openai/gpt-5"),
        ("openai", "utility", "openrouter/openai/gpt-5"),
    ],
)
def test_openrouter_picks_the_model_pair_of_the_chosen_family(settings, family, role, expected):
    model = make_model(openrouter(settings, openrouter_model_family=family), role=role, agent_name="a")
    assert model.model == expected
    assert model._additional_args["api_key"] == "or-key"  # one OpenRouter key for every family
    assert model._additional_args["max_tokens"] == 4096  # never let OpenRouter reserve the model maximum


def test_openrouter_model_names_can_be_overridden(settings):
    custom = openrouter(settings, openrouter_gemini_primary_model="google/gemini-2.5-pro")
    assert make_model(custom, role="primary", agent_name="a").model == "openrouter/google/gemini-2.5-pro"


def test_direct_openai_and_gemini_keep_their_own_keys_next_to_openrouter(settings):
    both = settings.model_copy(
        update={"openai_api_key": "oa-key", "gemini_api_key": "gm-key", "openrouter_api_key": "or-key"}
    )
    openai = make_model(both.model_copy(update={"llm_provider": "litellm"}), role="primary", agent_name="a")
    gemini = make_model(both.model_copy(update={"llm_provider": "gemini"}), role="primary", agent_name="a")
    assert (openai._additional_args["api_key"], gemini._additional_args["api_key"]) == ("oa-key", "gm-key")
