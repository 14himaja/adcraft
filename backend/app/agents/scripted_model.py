import json
from typing import Any

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field

from app.agents.errors import ModelUnavailable


class ScriptExhausted(AssertionError):
    pass


class ScriptedModel(BaseLlm):
    """Answers from a scripted list. Used by tests and by mock mode; never in production."""

    responses: list[dict] = Field(default_factory=list)
    requests: list[Any] = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream: bool = False):
        self.requests.append(llm_request)
        if not self.responses:
            raise ScriptExhausted(f"{self.model} has no scripted responses left")
        step = self.responses.pop(0)
        if "error" in step:
            raise ModelUnavailable(f"scripted model failure: {step['error']}")
        if "tool_call" in step:
            call = step["tool_call"]
            part = types.Part(function_call=types.FunctionCall(name=call["name"], args=call.get("args", {})))
        elif "json" in step:
            part = types.Part(text=json.dumps(step["json"]))
        else:
            part = types.Part(text=step["text"])
        yield LlmResponse(
            content=types.Content(role="model", parts=[part]),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10, candidates_token_count=5
            ),
        )
