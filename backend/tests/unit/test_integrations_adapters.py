import pytest

from app.config import Settings
from app.integrations.base.errors import (
    IntegrationApiError,
    IntegrationAuthExpired,
    IntegrationPermissionDenied,
    InvalidOAuthState,
    sanitize_error_message,
    with_integration_retries,
)
from app.integrations.base.models import PublishContent
from app.integrations.oauth.state import (
    DEFAULT_RETURN_TO,
    check_oauth_state,
    generate_pkce_pair,
    make_oauth_state,
    sanitize_return_to,
)
from app.integrations.registry import get_adapter, list_adapters

TEST_SETTINGS = Settings(
    _env_file=None,
    app_env="test",
    mongodb_uri="mongodb://localhost:27017",
    jwt_secret="x" * 32,
    token_encryption_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    meta_mode="fake",
    llm_provider="scripted",
)


def test_registry_returns_all_three_platforms_in_order():
    ids = [a.platform_id for a in list_adapters()]
    assert ids == ["facebook", "instagram", "linkedin"]


def test_pkce_pair_and_oauth_state_validation():
    verifier, challenge = generate_pkce_pair()
    assert verifier and challenge and verifier != challenge

    state = make_oauth_state(
        TEST_SETTINGS,
        user_id="user_1",
        organization_id="personal",
        platform="linkedin",
        return_to="/?section=connections",
        code_verifier=verifier,
    )
    claims = check_oauth_state(TEST_SETTINGS, state, user_id="user_1", platform="linkedin")
    assert claims["organization_id"] == "personal"
    assert claims["code_verifier"] == verifier
    assert claims["return_to"] == "/?section=connections"

    with pytest.raises(InvalidOAuthState):
        check_oauth_state(TEST_SETTINGS, state, user_id="user_2", platform="linkedin")
    with pytest.raises(InvalidOAuthState):
        check_oauth_state(TEST_SETTINGS, state, user_id="user_1", platform="facebook")


def test_sanitize_return_to_blocks_open_redirects():
    assert sanitize_return_to("/settings/connections") == "/settings/connections"
    assert sanitize_return_to("https://evil.example/steal") == DEFAULT_RETURN_TO
    assert sanitize_return_to("//evil.example") == DEFAULT_RETURN_TO
    assert sanitize_return_to(None) == DEFAULT_RETURN_TO


def test_sanitize_error_message_redacts_secrets():
    msg = "failed with access_token=secret123&refresh_token=ref456 Bearer tok789"
    clean = sanitize_error_message(msg)
    assert "secret123" not in clean
    assert "ref456" not in clean
    assert "tok789" not in clean


def test_platform_publish_validators():
    # Facebook requires text, link, or image + target
    fb = get_adapter("facebook")
    assert len(fb.validate_publish(PublishContent(text=""), {})) >= 1
    assert fb.validate_publish(PublishContent(text="Hello FB"), {"selected_target_id": "page_1"}) == []

    # Instagram requires image + target
    ig = get_adapter("instagram")
    assert len(ig.validate_publish(PublishContent(text="hello"), {})) == 2
    assert ig.validate_publish(PublishContent(text="hello", image_id="img1"), {"selected_target_id": "ig_1"}) == []

    # LinkedIn enforces w_organization_social for org targets
    li = get_adapter("linkedin")
    errs = li.validate_publish(
        PublishContent(text="Hello org", target_id="urn:li:organization:123"),
        {"scopes": ["openid", "profile", "w_member_social"]},
    )
    assert any("w_organization_social" in e for e in errs)
    assert (
        li.validate_publish(
            PublishContent(text="Hello org", target_id="urn:li:organization:123"),
            {"scopes": ["w_organization_social"]},
        )
        == []
    )


@pytest.mark.asyncio
async def test_retry_helper_retries_only_transient_errors():
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise IntegrationApiError("upstream 503", platform="linkedin", http_status=503, retryable=True)
        return "ok"

    from tenacity import wait_none

    assert await with_integration_retries(flaky, attempts=3, wait=wait_none()) == "ok"
    assert calls == 3

    auth_calls = 0

    async def auth_fail():
        nonlocal auth_calls
        auth_calls += 1
        raise IntegrationAuthExpired("expired")

    with pytest.raises(IntegrationAuthExpired):
        await with_integration_retries(auth_fail, attempts=3, wait=wait_none())
    assert auth_calls == 1

    perm_calls = 0

    async def perm_fail():
        nonlocal perm_calls
        perm_calls += 1
        raise IntegrationPermissionDenied("denied")

    with pytest.raises(IntegrationPermissionDenied):
        await with_integration_retries(perm_fail, attempts=3, wait=wait_none())
    assert perm_calls == 1
