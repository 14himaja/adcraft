import pytest
import respx
from httpx import Response

from app.services.user_ai import settings_for_user
from tests.api_helpers import login

OPENROUTER_CHECK = "https://openrouter.ai/api/v1/auth/key"


async def save(client, **body):
    response = await client.put("/settings/ai", json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def test_openrouter_is_saved_with_the_model_family(client):
    await login(client)
    view = await save(client, provider="openrouter", api_key="or-test-key-123", model_family="openai")
    assert (view["provider"], view["model_family"], view["configured"], view["key_source"]) == (
        "openrouter",
        "openai",
        True,
        "user",
    )
    assert (await client.get("/settings/ai")).json()["model_family"] == "openai"


async def test_the_family_defaults_to_the_server_setting(make_client):
    async with make_client(openrouter_model_family="openai", openrouter_api_key="server-key-123") as c:
        await login(c)
        view = (await c.get("/settings/ai")).json()
    assert view["model_family"] == "openai"


async def test_server_default_provider_follows_llm_provider(make_client):
    async with make_client(llm_provider="openrouter", openrouter_api_key="server-key-123") as c:
        await login(c)
        view = (await c.get("/settings/ai")).json()
    assert (view["provider"], view["configured"], view["key_source"]) == ("openrouter", True, "workspace")


async def test_a_key_is_required_unless_the_server_has_one(client):
    await login(client)
    response = await client.put("/settings/ai", json={"provider": "openrouter"})
    assert (response.status_code, response.json()["error"]["code"]) == (422, "AI_SETTINGS_INVALID")


async def test_unknown_provider_or_family_is_rejected(client):
    await login(client)
    unknown_provider = {"provider": "other", "api_key": "k" * 12}
    assert (await client.put("/settings/ai", json=unknown_provider)).status_code == 422
    body = {"provider": "openrouter", "api_key": "k" * 12, "model_family": "llama"}
    assert (await client.put("/settings/ai", json=body)).status_code == 422


@respx.mock
async def test_connection_test_calls_openrouters_key_endpoint(client):
    route = respx.get(OPENROUTER_CHECK).mock(return_value=Response(200, json={"data": {"label": "k"}}))
    await login(client)
    await save(client, provider="openrouter", api_key="or-test-key-123")
    result = (await client.post("/settings/ai/test")).json()
    assert result["connection_status"] == "CONNECTED" and result["provider"] == "openrouter"
    assert route.calls[0].request.headers["authorization"] == "Bearer or-test-key-123"


@respx.mock
async def test_connection_test_reports_a_rejected_key(client):
    respx.get(OPENROUTER_CHECK).mock(return_value=Response(401, json={"error": {"message": "No auth"}}))
    await login(client)
    await save(client, provider="openrouter", api_key="or-bad-key-123")
    result = (await client.post("/settings/ai/test")).json()
    assert result["connection_status"] == "ERROR"


@pytest.mark.parametrize("family", ["gemini", "openai"])
async def test_the_users_choice_drives_the_models_that_are_used(client, db, settings, family):
    await login(client)
    await save(client, provider="openrouter", api_key="or-test-key-123", model_family=family)
    user = await db.users.find_one({})
    effective = await settings_for_user(db, user["_id"], settings)
    assert (effective.llm_provider, effective.openrouter_api_key, effective.openrouter_model_family) == (
        "openrouter",
        "or-test-key-123",
        family,
    )


async def test_without_a_saved_choice_the_server_settings_apply(client, db, settings):
    await login(client)
    user = await db.users.find_one({})
    assert await settings_for_user(db, user["_id"], settings) is settings
