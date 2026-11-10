"""Workspace resolution logic: single source of truth for workspace_id."""


def resolve_workspace_id(
    campaign: dict | None = None,
    user: dict | None = None,
    default: str = "synxait",
) -> str:
    """Resolves workspace_id prioritizing campaign.workspace_id, then user.active_workspace_id, else default."""
    if campaign and campaign.get("workspace_id"):
        return str(campaign["workspace_id"])
    if user and user.get("active_workspace_id"):
        return str(user["active_workspace_id"])
    return default
