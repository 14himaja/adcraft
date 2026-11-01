import time

from pydantic import BaseModel, Field, ValidationError

from app.domain.states import CampaignState


class SearchInterestsArgs(BaseModel):
    query: str = Field(min_length=1, max_length=60)


class SearchLocationsArgs(BaseModel):
    query: str = Field(min_length=1, max_length=60)
    country: str = Field(pattern=r"^[A-Z]{2}$")


class EstimateAudienceArgs(BaseModel):
    interest_ids: list[str] = Field(max_length=20)


class NoArgs(BaseModel):
    pass


TOOL_INPUTS: dict[str, type[BaseModel]] = {
    "search_interests": SearchInterestsArgs,
    "search_locations": SearchLocationsArgs,
    "estimate_audience": EstimateAudienceArgs,
    "fetch_landing_page": NoArgs,
}
TOOLS_BY_STATE: dict[CampaignState, frozenset[str]] = {
    CampaignState.PLANNING: frozenset(TOOL_INPUTS),
}


def make_before_tool_guard(deps):
    def guard(tool, args, tool_context):
        allowed = TOOLS_BY_STATE.get(deps.status, frozenset())
        if tool.name not in allowed:
            deps.audit.append(
                (
                    "TOOL_REJECTED",
                    {"tool": tool.name, "reason": f"not allowed in {deps.status}"},
                )
            )
            return {"error": f"Tool '{tool.name}' is not allowed while the campaign is {deps.status}."}
        try:
            TOOL_INPUTS[tool.name].model_validate(args)
        except ValidationError as exc:
            message = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            deps.audit.append(("TOOL_REJECTED", {"tool": tool.name, "reason": message}))
            return {"error": f"Invalid arguments: {message}"}
        deps.audit.append(("TOOL_CALL", {"tool": tool.name, "args": args}))
        return None

    return guard


def make_model_logging_callbacks(deps, prompt_versions: dict[str, str]):
    started: dict[str, float] = {}

    def before_model(callback_context, llm_request):
        started[callback_context.agent_name] = time.monotonic()
        return None

    def after_model(callback_context, llm_response):
        name = callback_context.agent_name
        usage = getattr(llm_response, "usage_metadata", None)
        deps.agent_runs.append(
            {
                "agent": name,
                "prompt_version": prompt_versions.get(name, "unversioned"),
                "input_tokens": getattr(usage, "prompt_token_count", None) or 0,
                "output_tokens": getattr(usage, "candidates_token_count", None) or 0,
                "latency_ms": round((time.monotonic() - started.pop(name, time.monotonic())) * 1000),
            }
        )
        return None

    return before_model, after_model
