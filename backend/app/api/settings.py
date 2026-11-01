from typing import Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep, DbDep, SettingsDep, UserDep
from app.errors import AppError
from app.security.crypto import decrypt_token, encrypt_token

router = APIRouter(prefix="/settings", tags=["settings"])
Provider = Literal["openai", "gemini", "openrouter"]
ModelFamily = Literal["gemini", "openai"]  # which models OpenRouter serves


class AISettingsBody(BaseModel):
    provider: Provider
    api_key: str | None = Field(default=None, min_length=8, max_length=512)
    model_family: ModelFamily | None = None  # only used with provider "openrouter"


class AISettingsError(AppError):
    status, code = 422, "AI_SETTINGS_INVALID"


def _provider_default(settings) -> Provider:
    return {"gemini": "gemini", "openrouter": "openrouter"}.get(settings.llm_provider, "openai")


def _configured_server_key(provider: Provider, settings) -> str:
    return {
        "gemini": settings.gemini_api_key,
        "openrouter": settings.openrouter_api_key,
    }.get(provider, settings.openai_api_key)


async def _record(db, user_id):
    return await db.user_ai_settings.find_one({"user_id": user_id})


async def _read_key(db, user_id, settings, provider: Provider | None = None) -> tuple[Provider, str, str]:
    record = await _record(db, user_id)
    provider = provider or (record.get("provider") if record else None) or _provider_default(settings)
    if record and record.get("api_key_ciphertext") and record.get("provider") == provider:
        return provider, decrypt_token(settings.token_encryption_key, record["api_key_ciphertext"]), "user"
    server_key = _configured_server_key(provider, settings)
    if server_key:
        return provider, server_key, "workspace"
    return provider, "", "missing"


async def _view(db, user_id, settings) -> dict:
    record = await _record(db, user_id)
    provider, key, source = await _read_key(db, user_id, settings)
    return {
        "provider": provider,
        "model_family": (record or {}).get("model_family") or settings.openrouter_model_family,
        "configured": bool(key),
        "key_source": source,
        "masked_key": "••••••••" if key else None,
        "connection_status": record.get("connection_status", "NOT_TESTED") if record else "NOT_TESTED",
        "tested_at": record.get("tested_at").isoformat() if record and record.get("tested_at") else None,
    }


@router.get("/ai")
async def get_ai_settings(user: UserDep, db: DbDep, settings: SettingsDep) -> dict:
    return await _view(db, user["_id"], settings)


@router.put("/ai")
async def save_ai_settings(
    body: AISettingsBody, user: UserDep, db: DbDep, settings: SettingsDep, container: ContainerDep
) -> dict:
    record = await _record(db, user["_id"])
    has_user_key = record and record.get("provider") == body.provider and record.get("api_key_ciphertext")
    if not body.api_key and not has_user_key:
        if not _configured_server_key(body.provider, settings):
            raise AISettingsError("Enter an API key for the selected provider.")

    now = container.clock.now()
    fields = {
        "provider": body.provider,
        "connection_status": "NOT_TESTED",
        "tested_at": None,
        "updated_at": now,
    }
    if body.model_family:
        fields["model_family"] = body.model_family
    if body.api_key:
        fields["api_key_ciphertext"] = encrypt_token(settings.token_encryption_key, body.api_key.strip())
    await db.user_ai_settings.update_one(
        {"user_id": user["_id"]},
        {"$set": fields, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return await _view(db, user["_id"], settings)


@router.post("/ai/test")
async def test_ai_connection(
    user: UserDep, db: DbDep, settings: SettingsDep, container: ContainerDep
) -> dict:
    provider, api_key, source = await _read_key(db, user["_id"], settings)
    if not api_key:
        raise AISettingsError("Save an API key before testing the AI connection.")

    endpoint = {
        "gemini": "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
        "openrouter": "https://openrouter.ai/api/v1/auth/key",  # answers 200 only for a valid key
    }.get(provider, "https://api.openai.com/v1/models")
    headers = {"x-goog-api-key": api_key} if provider == "gemini" else {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(endpoint, headers=headers)
        if response.status_code == 200:
            status, message = "CONNECTED", f"{provider.title()} API key verified ({source} key)."
        elif response.status_code in (401, 403):
            status, message = "ERROR", "The provider rejected this API key or its permissions."
        elif response.status_code == 429:
            status, message = "ERROR", "The provider is rate limiting this key or its quota is unavailable."
        else:
            status = "ERROR"
            message = f"The provider returned HTTP {response.status_code} while checking the key."
    except httpx.TimeoutException:
        status, message = "ERROR", "The provider did not respond in time. Try again."
    except httpx.HTTPError:
        status, message = "ERROR", "Could not reach the provider. Check the server network and try again."

    now = container.clock.now()
    await db.user_ai_settings.update_one(
        {"user_id": user["_id"]},
        {
            "$set": {
                "provider": provider,
                "connection_status": status,
                "connection_message": message,
                "tested_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
    )
    return {
        "provider": provider,
        "connection_status": status,
        "message": message,
        "tested_at": now.isoformat(),
    }
