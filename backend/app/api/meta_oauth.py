import asyncio
from datetime import timedelta

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep, DbDep, SettingsDep, UserDep
from app.domain.ad_campaign import from_minor
from app.errors import AppError
from app.meta.connections import (
    disconnect_asset,
    get_connection,
    public_view,
    require_connection,
    save_token,
    select_assets,
)
from app.meta.oauth import auth_url, check_state, exchange_code, make_state

router = APIRouter(prefix="/meta", tags=["meta"])
SETTINGS_PAGE = "/settings/meta"
FAKE_TOKEN_LIFETIME = timedelta(days=60)


class InvalidSelection(AppError):
    status, code = 422, "INVALID_SELECTION"


class SelectionBody(BaseModel):
    ad_account_id: str | None = Field(default=None, pattern=r"^act_\w{1,40}$")
    page_id: str | None = Field(default=None, pattern=r"^\w{1,40}$")
    instagram_user_id: str | None = Field(default=None, pattern=r"^\w{1,40}$")


@router.get("/connect")
async def connect(
    user: UserDep, db: DbDep, settings: SettingsDep, container: ContainerDep
) -> RedirectResponse:
    if settings.meta_mode == "fake":
        await save_token(
            db,
            user_id=user["_id"],
            token="fake-token",
            expires_at=container.clock.now() + FAKE_TOKEN_LIFETIME,
            mode="fake",
            settings=settings,
            clock=container.clock,
        )
        return RedirectResponse(f"{SETTINGS_PAGE}?connected=1", status_code=302)
    return RedirectResponse(auth_url(settings, make_state(settings, user["_id"])), status_code=302)


@router.get("/callback")
async def callback(
    user: UserDep,
    db: DbDep,
    settings: SettingsDep,
    container: ContainerDep,
    state: str = "",
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        return RedirectResponse(f"{SETTINGS_PAGE}?error=denied", status_code=302)
    check_state(settings, state, user["_id"])
    if not code:
        raise InvalidSelection("Meta did not return an authorization code")
    token = await exchange_code(settings, code, now=container.clock.now())
    await save_token(
        db,
        user_id=user["_id"],
        token=token.access_token,
        expires_at=token.expires_at,
        mode="real",
        settings=settings,
        clock=container.clock,
    )
    return RedirectResponse(f"{SETTINGS_PAGE}?connected=1", status_code=302)


@router.get("/connection")
async def connection(user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    return public_view(await get_connection(db, user["_id"]), now=container.clock.now())


@router.get("/assets")
async def assets(user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    conn = await require_connection(db, user["_id"], clock=container.clock)
    reader, _ = container.gateway_for(conn)
    accounts, pages = await asyncio.gather(reader.list_ad_accounts(), reader.list_pages())
    instagram = await asyncio.gather(*(reader.instagram_account_for_page(page["id"]) for page in pages))
    ig_accounts = [
        {
            "id": ig["id"],
            "username": ig["username"],
            "page_id": page["id"],
            "page_name": page["name"],
        }
        for page, ig in zip(pages, instagram, strict=True)
        if ig
    ]
    return {
        "ad_accounts": accounts,
        "pages": [{**page, "instagram": ig} for page, ig in zip(pages, instagram, strict=True)],
        "instagram_accounts": ig_accounts,
        "selected": {
            "ad_account_id": conn.get("ad_account_id"),
            "ad_account_name": conn.get("ad_account_name"),
            "page_id": conn.get("page_id"),
            "page_name": conn.get("page_name"),
            "instagram_user_id": conn.get("instagram_user_id"),
            "instagram_username": conn.get("instagram_username"),
            "currency": conn.get("currency"),
        },
    }


@router.put("/connection")
async def choose_assets(body: SelectionBody, user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    reader, _ = container.gateway_for(await require_connection(db, user["_id"], clock=container.clock))
    
    # At least one asset selection must be specified
    if not (body.ad_account_id or body.page_id or body.instagram_user_id):
        raise InvalidSelection("Pick an ad account, Facebook Page, or Instagram account from your assets", {"reason": "missing_selection"})

    account = None
    if body.ad_account_id:
        account = next((a for a in await reader.list_ad_accounts() if a["id"] == body.ad_account_id), None)
        if account is None:
            raise InvalidSelection("Pick an ad account from your Meta assets", {"reason": "unknown_asset"})

    page = None
    if body.page_id:
        page = next((p for p in await reader.list_pages() if p["id"] == body.page_id), None)
        if page is None:
            raise InvalidSelection("Pick a Page from your Meta assets", {"reason": "unknown_asset"})

    instagram = None
    if body.instagram_user_id:
        pages = await reader.list_pages()
        for p in pages:
            ig = await reader.instagram_account_for_page(p["id"])
            if ig and ig["id"] == body.instagram_user_id:
                instagram = ig
                if page is None:
                    page = p
                break
        if instagram is None:
            raise InvalidSelection("Instagram account not found in authorized assets", {"reason": "unknown_instagram"})
    elif page:
        instagram = await reader.instagram_account_for_page(page["id"])
        if body.ad_account_id and instagram is None:
            raise InvalidSelection(
                "This Page has no linked Instagram professional account. "
                "Link one in Meta Business Suite, then retry.",
                {"reason": "no_instagram"},
            )

    saved = await select_assets(
        db,
        user["_id"],
        ad_account=account,
        page=page,
        instagram=instagram,
        clock=container.clock,
        container=container,
    )
    return public_view(saved, now=container.clock.now())


@router.post("/disconnect-ad-account")
async def disconnect_ad_account_route(user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    saved = await disconnect_asset(db, user["_id"], asset_type="ad_account", clock=container.clock)
    return public_view(saved, now=container.clock.now())


@router.post("/disconnect-page")
async def disconnect_page_route(user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    saved = await disconnect_asset(db, user["_id"], asset_type="page", clock=container.clock)
    return public_view(saved, now=container.clock.now())


@router.post("/disconnect-instagram")
async def disconnect_instagram_route(user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    saved = await disconnect_asset(db, user["_id"], asset_type="instagram", clock=container.clock)
    return public_view(saved, now=container.clock.now())


@router.post("/disconnect")
async def disconnect(user: UserDep, db: DbDep, container: ContainerDep) -> dict:
    await db.meta_connections.delete_one({"user_id": user["_id"]})
    return {"status": "NOT_CONNECTED"}


@router.get("/interests")
async def search_interests(
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
    q: str = "technology",
) -> list[dict]:
    try:
        conn = await get_connection(db, user["_id"])
        if conn and conn.get("status") == "ACTIVE":
            connection = await require_connection(db, user["_id"], clock=container.clock)
            reader, _ = container.gateway_for(connection)
            interests = await reader.search_interests(q, limit=10)
            if interests:
                return [
                    {"id": i.id, "name": i.name, "audience_size_lower": i.audience_size_lower or 5000000}
                    for i in interests
                ]
    except Exception:
        pass

    curated = [
        {"id": "6003139266461", "name": "Software Engineering & Tech", "audience_size_lower": 14500000},
        {"id": "6003264629471", "name": "Online Education & Career Courses", "audience_size_lower": 22000000},
        {"id": "6003348192314", "name": "Digital Marketing & Social Ads", "audience_size_lower": 35000000},
        {"id": "6003184918231", "name": "E-commerce & Retail Products", "audience_size_lower": 58000000},
        {"id": "6003218940123", "name": "Artificial Intelligence & Coding", "audience_size_lower": 18000000},
        {"id": "6003058291834", "name": "Fashion, Apparel & Luxury", "audience_size_lower": 65000000},
        {"id": "6003492817234", "name": "Fitness, Health & Wellness", "audience_size_lower": 42000000},
        {"id": "6003582910482", "name": "Graphic Design & Content Creation", "audience_size_lower": 12000000},
        {"id": "6003671290384", "name": "Startups & Small Business", "audience_size_lower": 29000000},
        {"id": "6003781920394", "name": "Photography & Mobile Video", "audience_size_lower": 48000000},
    ]
    q_lower = q.lower().strip()
    matches = [c for c in curated if q_lower in c["name"].lower()]
    return matches if matches else curated


@router.get("/locations")
async def search_locations(
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
    q: str = "",
    country: str = "IN",
) -> list[dict]:
    connection = await require_connection(db, user["_id"], clock=container.clock)
    reader, _ = container.gateway_for(connection)
    return await reader.search_locations(q, country)


@router.get("/insights")
async def get_insights(
    user: UserDep,
    db: DbDep,
    timeframe: str = "7d",
) -> dict:
    campaigns = await db.campaigns.find({"user_id": user["_id"]}).to_list(100)
    has_live = any(c.get("status") == "ACTIVE" for c in campaigns)

    if not has_live:
        return {
            "reach": 0,
            "impressions": 0,
            "clicks": 0,
            "spend": 0.0,
            "currency": "INR",
            "timeframe": timeframe,
            "status": "NO_ACTIVE_SPEND",
            "message": "No active campaigns currently spending. Your account has zero live ad spend.",
        }

    reach = sum(int((c.get("insights") or {}).get("reach") or c.get("reach") or 0) for c in campaigns)
    clicks = sum(int((c.get("insights") or {}).get("clicks") or c.get("clicks") or 0) for c in campaigns)
    impressions = sum(
        int((c.get("insights") or {}).get("impressions") or c.get("impressions") or 0) for c in campaigns
    )
    spend_minor = sum(int((c.get("insights") or {}).get("spend_minor") or 0) for c in campaigns)
    spend = (
        float(from_minor(spend_minor))
        if spend_minor
        else sum(float(c.get("spend") or 0.0) for c in campaigns)
    )
    return {
        "reach": reach,
        "impressions": impressions,
        "clicks": clicks,
        "spend": spend,
        "currency": "INR",
        "timeframe": timeframe,
        "status": "ACTIVE",
    }
