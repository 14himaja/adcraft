"""Workspace resolution logic: single source of truth for workspace_id."""


def is_internal_email(email: str | None) -> bool:
    if not email:
        return False
    e = email.lower().strip()
    return e.endswith("@synxait.in") or e.endswith("@synxait.com")


def personal_workspace_id(user: dict | None) -> str:
    if not user:
        return "personal"
    uid = user.get("_id") or user.get("id") or "default"
    return f"personal:{uid}"


def resolve_workspace_id(
    campaign: dict | None = None,
    user: dict | None = None,
    default: str = "synxait",
) -> str:
    """Resolves workspace_id prioritizing campaign.workspace_id, then user.active_workspace_id, else user-specific default."""
    if campaign and campaign.get("workspace_id"):
        return str(campaign["workspace_id"])
    if user and user.get("active_workspace_id"):
        active = str(user["active_workspace_id"])
        if active == "personal":
            return personal_workspace_id(user)
        return active
    if user:
        email = str(user.get("email") or "")
        if not is_internal_email(email):
            return personal_workspace_id(user)
    return default

