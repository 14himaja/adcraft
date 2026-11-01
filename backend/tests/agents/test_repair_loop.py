from google.adk import Agent, Workflow

from app.agents.nodes import RepairState, make_validate_assets_node
from app.agents.scripted_model import ScriptedModel
from app.domain.models import AssetDraft
from tests.agents.adk_helpers import run_root

GOOD = {
    "headline": "Ship reviews 2x faster",
    "primary_text": "AI code review for busy teams.",
    "description": "Free 14-day trial",
    "call_to_action": "LEARN_MORE",
    "image_concept": "Green CI check",
}
GOOD_DRAFT = {"variants": [GOOD, {**GOOD, "headline": "Fewer bugs in review"}]}
LONG_DRAFT = {"variants": [{**GOOD, "headline": "H" * 46}, GOOD]}
BANNED_DRAFT = {"variants": [{**GOOD, "headline": "Guaranteed results"}, GOOD]}


def build(responses):
    state = RepairState()
    model = ScriptedModel(model="scripted/creative_agent", responses=[{"json": r} for r in responses])
    creative = Agent(
        name="creative_agent",
        model=model,
        instruction="Write Instagram ads.",
        output_schema=AssetDraft,
        output_key="asset_draft",
    )
    validate = make_validate_assets_node(state, repair_route="REPAIR")

    def saved(node_input):
        state.outcome = "saved"

    def failed(node_input):
        state.outcome = "failed"

    workflow = Workflow(
        name="repair_loop",
        edges=[
            ("START", creative, validate),
            (validate, {"OK": saved, "REPAIR": creative, "FAILED": failed}),
        ],
    )
    return workflow, state, model


async def test_valid_first_draft_is_saved_without_repair():
    workflow, state, model = build([GOOD_DRAFT])
    await run_root(workflow)
    assert (state.outcome, state.repairs, len(state.variants), len(model.requests)) == ("saved", 0, 2, 1)


async def test_overlong_headline_is_repaired_with_exact_errors():
    workflow, state, model = build([LONG_DRAFT, GOOD_DRAFT])
    await run_root(workflow)
    assert (state.outcome, state.repairs) == ("saved", 1)
    assert "at most 40 characters" in str(model.requests[1].contents)


async def test_policy_violation_is_repaired():
    workflow, state, _ = build([BANNED_DRAFT, GOOD_DRAFT])
    await run_root(workflow)
    assert state.outcome == "saved"


async def test_gives_up_after_two_repairs():
    workflow, state, model = build([LONG_DRAFT, LONG_DRAFT, LONG_DRAFT])
    await run_root(workflow)
    assert (state.outcome, state.repairs, len(model.requests)) == ("failed", 2, 3)
    assert any("headline" in e for e in state.errors)
