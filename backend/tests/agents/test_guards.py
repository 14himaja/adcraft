from types import SimpleNamespace

from app.agents.guards import make_before_tool_guard, make_model_logging_callbacks
from app.domain.states import CampaignState as S


def deps(status=S.PLANNING):
    return SimpleNamespace(status=status, audit=[], agent_runs=[])


def tool(name):
    return SimpleNamespace(name=name)


def test_allowed_tool_with_valid_args_runs_and_is_audited():
    d = deps()
    assert make_before_tool_guard(d)(tool("search_interests"), {"query": "python"}, None) is None
    assert d.audit == [("TOOL_CALL", {"tool": "search_interests", "args": {"query": "python"}})]


def test_tool_outside_its_state_is_blocked():
    d = deps(status=S.COLLECTING)
    result = make_before_tool_guard(d)(tool("search_interests"), {"query": "python"}, None)
    assert "not allowed" in result["error"]
    assert d.audit[0][0] == "TOOL_REJECTED"


def test_unknown_tool_is_blocked():
    result = make_before_tool_guard(deps())(tool("publish_campaign"), {}, None)
    assert "not allowed" in result["error"]


def test_invalid_arguments_are_blocked():
    d = deps()
    result = make_before_tool_guard(d)(tool("search_interests"), {"query": "x" * 61}, None)
    assert "query" in result["error"]
    assert d.audit[0][0] == "TOOL_REJECTED"


def test_model_calls_are_logged_with_tokens_and_prompt_version():
    d = deps()
    before, after = make_model_logging_callbacks(d, {"creative_agent": "creative-v1"})
    ctx = SimpleNamespace(agent_name="creative_agent")
    before(ctx, None)
    after(
        ctx,
        SimpleNamespace(usage_metadata=SimpleNamespace(prompt_token_count=120, candidates_token_count=40)),
    )
    run = d.agent_runs[0]
    assert (run["agent"], run["input_tokens"], run["output_tokens"], run["prompt_version"]) == (
        "creative_agent",
        120,
        40,
        "creative-v1",
    )
    assert run["latency_ms"] >= 0
