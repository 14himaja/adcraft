import pytest
import requests
import responses
from tenacity import wait_none

from app.meta.errors import MetaError
from app.meta.sdk_gateway import GRAPH_URL, MetaSdkGateway
from tests.meta_payloads import M0_ACCOUNT, m0

TOKEN = "EAAB-SECRET-TOKEN"


@pytest.fixture
def real_settings(settings):
    return settings.model_copy(
        update={"meta_mode": "real", "meta_app_id": "123", "meta_app_secret": "s3cret"}
    )


@pytest.fixture
def mock():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as m:
        yield m


def url(settings, path):
    return f"{GRAPH_URL}/{settings.meta_api_version}/{path}"


def gateway(settings):
    return MetaSdkGateway(access_token=TOKEN, settings=settings, wait=wait_none())


async def test_requests_carry_versioned_url_and_appsecret_proof(real_settings, mock):
    mock.add("GET", url(real_settings, "me/accounts"), json=m0("r2_pages.response"))
    await gateway(real_settings).list_pages()
    sent = mock.calls[0].request.url
    assert sent.startswith(f"{GRAPH_URL}/v26.0/me/accounts")
    assert "appsecret_proof=" in sent


async def test_each_gateway_has_its_own_api_object(real_settings):
    a = MetaSdkGateway(access_token="A", settings=real_settings)
    b = MetaSdkGateway(access_token="B", settings=real_settings)
    assert a._api is not b._api


async def test_read_is_retried_on_code_17_then_succeeds(real_settings, mock):
    throttled = {"error": {"code": 17, "message": "User request limit reached"}}
    mock.add("GET", url(real_settings, "me/accounts"), json=throttled, status=400)
    mock.add("GET", url(real_settings, "me/accounts"), json=m0("r2_pages.response"))
    pages = await gateway(real_settings).list_pages()
    assert pages[0]["name"] == "Social Ads Demo"
    assert len(mock.calls) == 2


async def test_create_is_not_retried(real_settings, mock):
    throttled = {"error": {"code": 17, "message": "User request limit reached"}}
    mock.add("POST", url(real_settings, f"{M0_ACCOUNT}/campaigns"), json=throttled, status=400)
    with pytest.raises(MetaError):
        await gateway(real_settings).create(M0_ACCOUNT, "campaigns", {"name": "x"})
    assert len(mock.calls) == 1


async def test_create_sends_bool_as_json(real_settings, mock):
    mock.add("POST", url(real_settings, f"{M0_ACCOUNT}/campaigns"), json=m0("r7_campaign_success.response"))
    params = m0("r7_campaign_success.request")["params"]
    expected_id = m0("r7_campaign_success.response")["id"]
    assert await gateway(real_settings).create(M0_ACCOUNT, "campaigns", params) == expected_id
    assert "is_adset_budget_sharing_enabled=false" in mock.calls[0].request.body


async def test_throttle_header_sets_retry_after(real_settings, mock):
    usage = '{"1": [{"type": "ads_management", "estimated_time_to_regain_access": 2}]}'
    mock.add(
        "POST",
        url(real_settings, f"{M0_ACCOUNT}/campaigns"),
        json={"error": {"code": 80004, "message": "Too many calls"}},
        status=400,
        headers={"X-Business-Use-Case-Usage": usage},
    )
    with pytest.raises(MetaError) as exc:
        await gateway(real_settings).create(M0_ACCOUNT, "campaigns", {"name": "x"})
    assert exc.value.retry_after_s == 120


async def test_timeout_becomes_timeout_error_without_the_token(real_settings, mock):
    mock.add(
        "POST",
        url(real_settings, f"{M0_ACCOUNT}/campaigns"),
        body=requests.Timeout(f"read timed out for ...?access_token={TOKEN}"),
    )
    with pytest.raises(TimeoutError) as exc:
        await gateway(real_settings).create(M0_ACCOUNT, "campaigns", {"name": "x"})
    assert TOKEN not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


async def test_connection_error_becomes_connection_error(real_settings, mock):
    mock.add("GET", url(real_settings, "me/accounts"), body=requests.ConnectionError("boom"))
    with pytest.raises(ConnectionError):
        await gateway(real_settings).list_pages()


async def test_update_is_forced_paused_while_safe_mode_is_on(real_settings, mock):
    allow_but_safe = real_settings.model_copy(
        update={"allow_real_ad_spend": True, "safe_mode_no_spend": True}
    )
    mock.add("POST", url(allow_but_safe, "123"), json={"success": True})
    await gateway(allow_but_safe).update("123", {"status": "ACTIVE"})
    assert "status=PAUSED" in mock.calls[0].request.body


async def test_insights_request_is_campaign_level_over_the_time_range(real_settings, mock):
    from datetime import date

    mock.add("GET", url(real_settings, "120/insights"), json={"data": []})
    await gateway(real_settings).insights("120", date(2026, 10, 7), date(2026, 10, 9))
    sent = mock.calls[0].request.url
    assert "level=campaign" in sent and "fields=impressions%2Creach%2Cclicks%2Cspend%2Cctr%2Ccpc" in sent
    assert "2026-10-07" in sent and "2026-10-09" in sent


async def test_ad_status_asks_for_effective_status_and_review_feedback(real_settings, mock):
    mock.add(
        "GET",
        url(real_settings, "777"),
        json={"id": "777", "effective_status": "WITH_ISSUES", "issues_info": [{"error_message": "No photo"}]},
    )
    status = await gateway(real_settings).ad_status("777")
    assert status == {"effective_status": "WITH_ISSUES", "review_feedback": None, "issues": ["No photo"]}
    assert "fields=effective_status%2Cad_review_feedback%2Cissues_info" in mock.calls[0].request.url


async def test_dm_and_webhook_calls_use_the_page_token_not_the_login_token(real_settings, mock):
    mock.add("GET", url(real_settings, "page1"), json={"access_token": "PAGE-TOKEN", "id": "page1"})
    mock.add("POST", url(real_settings, "page1/subscribed_apps"), json={"success": True})
    mock.add("POST", url(real_settings, "page1/messages"), json={"message_id": "m1"})
    g = gateway(real_settings)
    await g.subscribe_messages("page1")
    assert await g.send_dm("page1", "cust", "hi") == "m1"
    writes = [c.request for c in mock.calls if c.request.method == "POST"]
    assert len(writes) == 2
    for request in writes:
        assert "PAGE-TOKEN" in request.body or "PAGE-TOKEN" in request.url
        assert TOKEN not in (request.body or "") + request.url


async def test_customer_name_tries_instagram_fields_then_messenger_fields(real_settings, mock):
    def add(path, body, status=200):
        mock.add("GET", url(real_settings, path), json=body, status=status)

    add("page1", {"access_token": "PAGE-TOKEN", "id": "page1"})
    add("ig_cust", {"name": "Ravi Kumar", "username": "ravi_k", "id": "ig_cust"})
    add("fb_cust", {"error": {"code": 100, "message": "Unknown field"}}, status=400)
    add("fb_cust", {"first_name": "Asha", "last_name": "Rao", "id": "fb_cust"})
    g = gateway(real_settings)
    assert await g.customer_name("page1", "ig_cust") == "Ravi Kumar"
    assert await g.customer_name("page1", "fb_cust") == "Asha Rao"


async def test_instagram_story_is_published_as_a_stories_container_without_a_caption(real_settings, mock):
    mock.add("POST", url(real_settings, "ig1/media"), json={"id": "c1"})
    mock.add("POST", url(real_settings, "ig1/media_publish"), json={"id": "m1"})
    assert await gateway(real_settings).publish_photo("ig1", "https://x/i.jpg", "ignored", story=True) == "m1"
    body = mock.calls[0].request.body
    assert "media_type=STORIES" in body and "caption" not in body


async def test_facebook_photo_and_story_use_the_page_token(real_settings, mock):
    mock.add("GET", url(real_settings, "page1"), json={"access_token": "PAGE-TOKEN", "id": "page1"})
    mock.add("POST", url(real_settings, "page1/photos"), json={"id": "ph1", "post_id": "page1_ph1"})
    mock.add("POST", url(real_settings, "page1/photo_stories"), json={"success": True, "post_id": "st1"})
    g = gateway(real_settings)
    assert await g.publish_facebook_photo("page1", "https://x/i.jpg", "hello") == "page1_ph1"
    assert await g.publish_facebook_story("page1", "https://x/i.jpg") == "st1"
    posts = [c.request for c in mock.calls if c.request.method == "POST"]
    assert len(posts) == 3  # photo, then the unpublished photo and the story for the story
    assert all("PAGE-TOKEN" in (r.body or "") + r.url and TOKEN not in (r.body or "") + r.url for r in posts)
    assert "published=false" in posts[1].body.lower() and "photo_id=ph1" in posts[2].body
