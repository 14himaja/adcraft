import pytest

from app.meta.errors import MetaError
from app.meta.fake import FakeAdsGateway, parse_fail_at

ACCOUNT = "act_fake_1"
ADSET = {"name": "acm-000001-v1-ADSET", "status": "PAUSED"}


async def test_fail_at_raises_the_configured_error_once():
    fake = FakeAdsGateway(fail_at={"ADSET": MetaError(meta_code=100)})
    with pytest.raises(MetaError):
        await fake.create(ACCOUNT, "adsets", ADSET)
    assert await fake.create(ACCOUNT, "adsets", ADSET)  # second try succeeds


async def test_timeout_before_create_creates_nothing():
    fake = FakeAdsGateway(fail_at={"ADSET": "timeout"})
    with pytest.raises(TimeoutError):
        await fake.create(ACCOUNT, "adsets", ADSET)
    assert fake.by_edge("adsets") == []


async def test_timeout_after_create_creates_then_raises():
    fake = FakeAdsGateway(fail_at={"ADSET": "timeout_after_create"})
    with pytest.raises(TimeoutError):
        await fake.create(ACCOUNT, "adsets", ADSET)
    assert await fake.find_by_name(ACCOUNT, "adsets", ADSET["name"])


async def test_update_and_delete_of_unknown_object_raise_code_100():
    fake = FakeAdsGateway()
    with pytest.raises(MetaError) as exc:
        await fake.update("nope", {"status": "ACTIVE"})
    assert exc.value.meta_code == 100
    with pytest.raises(MetaError):
        await fake.delete("nope")


async def test_update_changes_status():
    fake = FakeAdsGateway()
    object_id = await fake.create(ACCOUNT, "ads", {"name": "a", "status": "PAUSED"})
    await fake.update(object_id, {"status": "ACTIVE"})
    assert fake.objects[object_id]["status"] == "ACTIVE"


async def test_page_without_instagram_returns_none():
    assert await FakeAdsGateway().instagram_account_for_page("page_fake_2") is None


def test_parse_fail_at():
    parsed = parse_fail_at("ADSET:timeout_after_create, CAMPAIGN:190, AD")
    assert parsed["ADSET"] == "timeout_after_create"
    assert parsed["CAMPAIGN"].meta_code == 190
    assert parsed["AD"].meta_code == 100  # a bare step injects code 100
    assert parse_fail_at("") == {}
