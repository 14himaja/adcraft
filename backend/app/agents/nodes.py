from dataclasses import dataclass, field

from google.adk import Event
from pydantic import BaseModel, ValidationError

from app.domain.models import AdVariant, AssetDraft, finalize_assets
from app.domain.rules import REPAIR_MAX


def as_model(schema: type[BaseModel], node_input) -> BaseModel:
    if isinstance(node_input, schema):
        return node_input
    if isinstance(node_input, BaseModel):
        return schema.model_validate(node_input.model_dump())
    if isinstance(node_input, (str, bytes)):
        return schema.model_validate_json(node_input)
    return schema.model_validate(node_input)


def repair_message(errors: list[str]) -> str:
    bullet_list = "\n".join(f"- {e}" for e in errors)
    return f"Fix ONLY these problems and return the complete object again:\n{bullet_list}"


def _problems(exc: Exception) -> list[str]:
    if isinstance(exc, ValidationError):
        return [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
    return str(exc).splitlines()


@dataclass
class RepairState:
    repairs: int = 0
    variants: list[AdVariant] | None = None
    errors: list[str] = field(default_factory=list)
    outcome: str | None = None


def make_validate_assets_node(state: RepairState, *, repair_route: str):
    def validate_assets(node_input):
        try:
            state.variants = finalize_assets(as_model(AssetDraft, node_input))
            state.errors = []
            return Event(route="OK")
        except (ValidationError, ValueError) as exc:
            state.errors = _problems(exc)
            if state.repairs >= REPAIR_MAX:
                return Event(route="FAILED")
            state.repairs += 1
            return Event(route=repair_route, output=repair_message(state.errors))

    return validate_assets
