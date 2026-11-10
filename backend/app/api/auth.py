from app.domain.workspaces import resolve_workspace_id
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app import audit
from app.api.deps import SESSION_COOKIE, current_user, get_db, get_settings_dep
from app.clock import utcnow
from app.config import Settings
from app.errors import EmailTaken, Unauthenticated
from app.security.jwt import issue_token
from app.security.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_DUMMY_HASH = hash_password("dummy-password-for-timing")


class RegisterBody(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    password: str = Field(min_length=6, max_length=128)
    name: str | None = Field(default=None, max_length=100)
    workspace_name: str | None = Field(default=None, max_length=100)


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class SwitchWorkspaceBody(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=60)


def _workspaces_for_user(user: dict) -> list[dict]:
    name = user.get("name") or user["email"].split("@")[0].title()
    custom_name = user.get("workspace_name") or f"{name}'s Brand"
    return [
        {
            "id": "synxait",
            "name": "Synxait",
            "label": "Synxait (Dev/Test)",
            "type": "development",
            "description": "Default development and testing workspace with Synxait test assets",
            "is_default": True,
        },
        {
            "id": "personal",
            "name": custom_name,
            "label": custom_name,
            "type": "customer",
            "description": "Primary customer workspace",
            "is_default": False,
        },
    ]


def _public(user: dict) -> dict:
    name = user.get("name") or user["email"].split("@")[0].title()
    workspaces = _workspaces_for_user(user)
    active_ws_id = resolve_workspace_id(user=user)
    active_ws = next((w for w in workspaces if w["id"] == active_ws_id), workspaces[0])
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": name,
        "workspace": active_ws["name"],
        "workspace_id": active_ws["id"],
        "workspaces": workspaces,
        "is_dev_workspace": active_ws["type"] == "development",
    }


@router.post("/register", status_code=201)
async def register(
    body: RegisterBody,
    response: Response,
    db: Annotated[Any, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> dict:
    name = body.name.strip() if body.name else body.email.split("@")[0].title()
    workspace = body.workspace_name.strip() if body.workspace_name else f"{name}'s Brand"
    user = {
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "name": name,
        "workspace_name": workspace,
        "created_at": utcnow(),
    }
    try:
        await db.users.insert_one(user)
    except DuplicateKeyError as exc:
        raise EmailTaken("This email is already registered") from exc

    await audit.record(
        db,
        actor="user",
        event_type="USER_REGISTERED",
        payload={"email": user["email"], "name": name},
        user_id=user["_id"],
    )
    return _public(user)


@router.post("/login")
async def login(
    body: LoginBody,
    request: Request,
    response: Response,
    db: Annotated[Any, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> dict:
    request.app.state.login_limiter.hit(request.client.host if request.client else "unknown")
    user = await db.users.find_one({"email": body.email.lower()})
    print("LOGIN DEBUG - User found:", user is not None)
    print(
    "LOGIN DEBUG - Password hash exists:",
    bool(user and user.get("password_hash")),
)
    password_ok = verify_password(user["password_hash"] if user else _DUMMY_HASH, body.password)
    print("LOGIN DEBUG - Password verified:", password_ok)
    if user is None or not password_ok:
        raise Unauthenticated("Invalid email or password")
    response.set_cookie(
        SESSION_COOKIE,
        issue_token(str(user["_id"]), settings.jwt_secret),
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        max_age=12 * 3600,
    )
    await audit.record(
        db,
        actor="user",
        event_type="USER_LOGIN",
        payload={"email": user["email"]},
        user_id=user["_id"],
    )
    return _public(user)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


@router.get("/me")
async def me(user: Annotated[dict, Depends(current_user)]) -> dict:
    return _public(user)


@router.put("/password", status_code=204)
async def change_password(
    body: ChangePasswordBody,
    user: Annotated[dict, Depends(current_user)],
    db: Annotated[Any, Depends(get_db)],
) -> Response:
    if not verify_password(user["password_hash"], body.current_password):
        raise Unauthenticated("Current password is incorrect")
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hash_password(body.new_password), "password_changed_at": utcnow()}},
    )
    return Response(status_code=204)


@router.post("/workspace/switch")
async def switch_workspace(
    body: SwitchWorkspaceBody,
    user: Annotated[dict, Depends(current_user)],
    db: Annotated[Any, Depends(get_db)],
) -> dict:
    valid_ids = {"synxait", "personal"}
    if body.workspace_id not in valid_ids:
        raise Unauthenticated("Invalid workspace ID")
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"active_workspace_id": body.workspace_id, "updated_at": utcnow()}},
    )
    user["active_workspace_id"] = body.workspace_id
    await audit.record(
        db,
        actor="user",
        event_type="WORKSPACE_SWITCHED",
        payload={"workspace_id": body.workspace_id},
        user_id=user["_id"],
    )
    return _public(user)
