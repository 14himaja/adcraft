"""Learning tests: pin down how ADK 2.x behaves for the features this project relies on."""

import json

from google.adk import Agent, Event, Workflow
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel

from tests.agents.adk_helpers import run_root


class ListModel(BaseLlm):
    """Throwaway model for the spike: replies with the next item of `replies`."""

    replies: list = []

    async def generate_content_async(self, llm_request, stream: bool = False):
        reply = self.replies.pop(0)
        if isinstance(reply, dict) and "call" in reply:
            part = types.Part(
                function_call=types.FunctionCall(name=reply["call"], args=reply.get("args", {}))
            )
        else:
            part = types.Part(text=reply if isinstance(reply, str) else json.dumps(reply))
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def as_dict(value):
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, str):
        return json.loads(value)
    return value


async def test_function_nodes_pass_their_output_to_the_next_node():
    seen = []

    def first(node_input):
        return "hello"

    def second(node_input):
        seen.append(node_input)

    await run_root(Workflow(name="wf", edges=[("START", first, second)]))
    assert seen == ["hello"]


async def test_event_route_selects_the_branch():
    seen = []

    def router(node_input):
        return Event(route="B")

    def a(node_input):
        seen.append("A")

    def b(node_input):
        seen.append("B")

    await run_root(Workflow(name="wf", edges=[("START", router), (router, {"A": a, "B": b})]))
    assert seen == ["B"]


async def test_a_route_can_loop_back_to_an_earlier_node():
    count = {"n": 0}

    def step(node_input):
        count["n"] += 1
        return count["n"]

    def check(node_input):
        return Event(route="AGAIN" if count["n"] < 3 else "DONE")

    def done(node_input):
        count["done"] = True

    await run_root(
        Workflow(name="wf", edges=[("START", step, check), (check, {"AGAIN": step, "DONE": done})])
    )
    assert count == {"n": 3, "done": True}


async def test_event_output_becomes_the_next_nodes_input():
    seen = []

    def router(node_input):
        return Event(route="NEXT", output="carried")

    def target(node_input):
        seen.append(node_input)

    await run_root(Workflow(name="wf", edges=[("START", router), (router, {"NEXT": target})]))
    assert seen == ["carried"]


async def test_agent_output_reaches_the_next_function_node():
    seen = []
    agent = Agent(name="greeter", model=ListModel(model="list", replies=["hi there"]), instruction="Say hi.")

    def capture(node_input):
        seen.append(node_input)

    await run_root(Workflow(name="wf", edges=[("START", agent, capture)]))
    assert "hi there" in str(seen[0])


async def test_output_schema_parses_json_into_state():
    class Greeting(BaseModel):
        text: str

    seen = []
    agent = Agent(
        name="greeter",
        model=ListModel(model="list", replies=[{"text": "hi"}]),
        instruction="Greet.",
        output_schema=Greeting,
        output_key="greeting",
    )

    def capture(node_input):
        seen.append(node_input)

    _, session = await run_root(Workflow(name="wf", edges=[("START", agent, capture)]))
    assert as_dict(session.state["greeting"]) == {"text": "hi"}
    assert as_dict(seen[0]) == {"text": "hi"}


async def test_before_tool_callback_returning_a_dict_blocks_the_tool():
    called = []

    def danger() -> dict:
        """Pretend to do something dangerous."""
        called.append(True)
        return {"ok": True}

    def guard(tool, args, tool_context):
        return {"error": "blocked"} if tool.name == "danger" else None

    agent = Agent(
        name="t",
        model=ListModel(model="list", replies=[{"call": "danger"}, "done"]),
        instruction="Use tools.",
        tools=[danger],
        before_tool_callback=guard,
    )
    await run_root(agent)
    assert called == []


async def test_instruction_placeholders_are_filled_from_state():
    model = ListModel(model="list", replies=["ok"])
    seen_requests = []
    original = model.generate_content_async

    async def spy(llm_request, stream=False):
        seen_requests.append(llm_request)
        async for r in original(llm_request, stream):
            yield r

    object.__setattr__(model, "generate_content_async", spy)
    agent = Agent(name="a", model=model, instruction="State is <s>{campaign_state}</s>.")
    await run_root(agent, state={"campaign_state": "SECRET-123"})
    assert "SECRET-123" in str(seen_requests[0].config.system_instruction)
