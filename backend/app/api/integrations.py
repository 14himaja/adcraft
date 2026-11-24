from typing import Annotated
from urllib.parse import quote_plus

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import ContainerDep, DbDep, OptionalUserDep, SettingsDep, UserDep
from app.integrations import publishing, service
from app.integrations.advertising import list_advertising_platforms
from app.integrations.base.errors import IntegrationNotConfigured
from app.integrations.base.models import PlatformId
from app.integrations.oauth.state import sanitize_return_to

router = APIRouter(prefix="/integrations", tags=["integrations"])


class SelectAccountBody(BaseModel):
    target_id: str = Field(min_length=1, max_length=200)


class PublishPreviewBody(BaseModel):
    platforms: list[PlatformId] = Field(min_length=1, max_length=10)
    text: Annotated[str, StringConstraints(max_length=65000)] = ""
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None
    link_url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2048)] | None = None
    image_id: str | None = Field(default=None, max_length=64)
    hashtags: list[str] = Field(default_factory=list, max_length=10)
    targets: dict[str, str] = Field(default_factory=dict)
    scheduled_at: str | None = None


@router.get("")
async def list_integrations(user: UserDep, db: DbDep, settings: SettingsDep, container: ContainerDep) -> dict:
    return await service.get_all_connections_status(db, user, settings=settings, clock=container.clock)


@router.get("/advertising/platforms")
async def advertising_platforms(user: UserDep, db: DbDep, settings: SettingsDep) -> dict:
    return await list_advertising_platforms(db, user, settings=settings)


@router.post("/publish/preview")
async def preview_publish(
    body: PublishPreviewBody, user: UserDep, db: DbDep, settings: SettingsDep, container: ContainerDep
) -> dict:
    return await publishing.preview_multi_publish(
        db,
        user,
        platforms=body.platforms,
        text=body.text,
        title=body.title,
        link_url=body.link_url,
        image_id=body.image_id,
        hashtags=body.hashtags,
        targets=body.targets,
        scheduled_at=body.scheduled_at,
        settings=settings,
        clock=container.clock,
    )


@router.post("/publish")
async def multi_publish(
    body: PublishPreviewBody, user: UserDep, db: DbDep, settings: SettingsDep, container: ContainerDep
) -> dict:
    return await publishing.publish_multi_platform(
        db,
        user,
        platforms=body.platforms,
        text=body.text,
        title=body.title,
        link_url=body.link_url,
        image_id=body.image_id,
        hashtags=body.hashtags,
        targets=body.targets,
        scheduled_at=body.scheduled_at,
        settings=settings,
        clock=container.clock,
        container=container,
    )


@router.get("/publish/history")
async def publish_history(user: UserDep, db: DbDep) -> list[dict]:
    return await publishing.list_publish_history(db, user)


@router.get("/{platform}")
async def get_integration(
    platform: str, user: UserDep, db: DbDep, settings: SettingsDep, container: ContainerDep
) -> dict:
    return await service.get_platform_status(db, user, platform, settings=settings, clock=container.clock)


@router.get("/{platform}/connect")
async def connect_platform(
    platform: str,
    request: Request,
    user: OptionalUserDep,
    db: DbDep,
    settings: SettingsDep,
    container: ContainerDep,
    return_to: str | None = Query(default=None),
) -> RedirectResponse:
    safe_return = sanitize_return_to(return_to)
    if user is None:
        full_path = request.url.path
        if request.url.query:
            full_path = f"{full_path}?{request.url.query}"
        return RedirectResponse(f"/login?redirect={quote_plus(full_path)}", status_code=302)

    try:
        url, _ = await service.initiate_connect(
            db,
            user,
            platform,
            settings=settings,
            clock=container.clock,
            return_to=safe_return,
            container=container,
        )
        return RedirectResponse(url, status_code=302)
    except IntegrationNotConfigured:
        sep = "&" if "?" in safe_return else "?"
        return RedirectResponse(f"{safe_return}{sep}error=not_configured&platform={platform}", status_code=302)


@router.get("/{platform}/callback")
async def callback_platform(
    platform: str,
    request: Request,
    user: OptionalUserDep,
    db: DbDep,
    settings: SettingsDep,
    container: ContainerDep,
    state: str = "",
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if user is None:
        safe_return = sanitize_return_to(None)
        return RedirectResponse(f"/login?redirect={quote_plus(safe_return)}&error=session_expired", status_code=302)

    redirect_url = await service.handle_oauth_callback(
        db,
        user,
        platform,
        state=state,
        code=code,
        error=error,
        settings=settings,
        clock=container.clock,
        container=container,
    )
    return RedirectResponse(redirect_url, status_code=302)


@router.get("/{platform}/accounts")
async def accounts_platform(
    platform: str, user: UserDep, db: DbDep, settings: SettingsDep, container: ContainerDep
) -> dict:
    return await service.discover_platform_accounts(
        db, user, platform, settings=settings, clock=container.clock, container=container
    )


@router.put("/{platform}/account")
async def select_account_platform(
    platform: str,
    body: SelectAccountBody,
    user: UserDep,
    db: DbDep,
    settings: SettingsDep,
    container: ContainerDep,
) -> dict:
    return await service.select_platform_account(
        db,
        user,
        platform,
        target_id=body.target_id,
        settings=settings,
        clock=container.clock,
        container=container,
    )


@router.post("/{platform}/refresh")
async def refresh_platform(
    platform: str, user: UserDep, db: DbDep, settings: SettingsDep, container: ContainerDep
) -> dict:
    return await service.refresh_platform_connection(
        db, user, platform, settings=settings, clock=container.clock
    )


@router.post("/{platform}/disconnect")
async def disconnect_platform(
    platform: str, user: UserDep, db: DbDep, settings: SettingsDep, container: ContainerDep
) -> dict:
    return await service.disconnect_platform(
        db, user, platform, settings=settings, clock=container.clock
    )

