from types import SimpleNamespace

import pytest

from app.services import ad_fix

CTA = (
    "Web feed CTA not supported: Your ad won't run on Instagram "
    "because the selected call to action is not supported."
)
CITY = "City targeting isn't supported in the country you selected."
PHOTO = "Instagram media creation cannot be completed: The ad media is not supported for IG."


def test_each_real_meta_error_gets_the_right_plan():
    assert ad_fix.plan([CTA]) == ({"cta"}, [])
    assert ad_fix.plan([CITY]) == ({"cities"}, [])
    auto, manual = ad_fix.plan([PHOTO, "Something new"])
    assert auto == set() and "profile photo" in manual[0] and "Something new" in manual[1]


class Writer:
    def __init__(self):
        self.calls = []

    async def create(self, account, edge, params):
        self.calls.append(
            ("create", edge, params["object_story_spec"]["link_data"]["call_to_action"]["type"])
        )
        return "new_creative"

    async def update(self, object_id, params):
        self.calls.append(("update", object_id, params))


class Campaigns:
    def __init__(self):
        self.set = None

    async def update_one(self, _filter, change):
        self.set = change["$set"]


async def test_button_and_cities_are_fixed_on_meta_and_in_our_record(monkeypatch):
    writer, campaigns = Writer(), Campaigns()
    connection = {"page_id": "p", "instagram_user_id": "ig", "ad_account_id": "act_1"}

    async def selected(*_a, **_k):
        return connection

    async def meta_write(_db, _campaign, _container, fn, *args):
        return await fn(*args)

    async def record(*_a, **_k):
        return None

    monkeypatch.setattr(ad_fix, "require_selected", selected)
    monkeypatch.setattr(ad_fix, "meta_write", meta_write)
    monkeypatch.setattr(ad_fix.audit, "record", record)
    container = SimpleNamespace(
        gateway_for=lambda _c: (None, writer),
        clock=None,
        settings=SimpleNamespace(instagram_position_list=["stream"]),
    )
    campaign = {
        "_id": "abcdef123456",
        "user_id": "u",
        "status": "ACTIVE",
        "landing_url": "https://x.example/",
        "variants": [{"headline": "h", "primary_text": "t", "description": "d", "call_to_action": "SIGN_UP"}],
        "audience": {"countries": [], "cities": [{"key": "1", "name": "Mumbai"}]},
        "meta": {"ad_id": "ad1", "adset_id": "set1", "image_hash": "hash", "issues": [CTA, CITY]},
    }
    db = SimpleNamespace(campaigns=campaigns)

    result = await ad_fix.fix_issues(db, campaign, container=container)

    assert len(result["fixed"]) == 2 and result["manual"] == []
    assert ("create", "adcreatives", "LEARN_MORE") in writer.calls
    assert ("update", "ad1", {"creative": {"creative_id": "new_creative"}}) in writer.calls
    targeting = next(c[2]["targeting"] for c in writer.calls if c[1] == "set1")
    assert targeting["geo_locations"] == {"countries": ["IN"]}
    assert campaigns.set["variants.0.call_to_action"] == "LEARN_MORE" and campaigns.set["meta.issues"] == []


async def test_nothing_is_changed_when_meta_reported_nothing():
    campaign = {"status": "ACTIVE", "meta": {"issues": []}}
    with pytest.raises(ad_fix.NothingToFix):
        await ad_fix.fix_issues(None, campaign, container=None)
