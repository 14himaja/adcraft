

async def test_instagram_profile_without_photo_is_refused_before_publishing():
    import pytest

    from app.meta.publish_checks import InstagramProfileIncomplete, check_instagram_profile

    class Reader:
        def __init__(self, picture):
            self.picture = picture

        async def instagram_account_for_page(self, page_id):
            return {"id": "1", "username": "brand", "profile_picture_url": self.picture}

    await check_instagram_profile(Reader("https://x/p.jpg"), "page")
    with pytest.raises(InstagramProfileIncomplete, match="@brand has no profile photo"):
        await check_instagram_profile(Reader(None), "page")


async def test_interest_with_a_label_suffix_is_found_by_its_base_name():
    """Meta labels an interest "Restaurants (dining)" but only finds it when searching "Restaurants"."""
    import pytest

    from app.meta.ports import InterestOption
    from app.meta.publish_checks import DraftIncomplete, verify_interests

    class Reader:
        async def search_interests(self, query, limit=5):
            hits = {"Restaurants": [InterestOption(id="6003436950375", name="Restaurants (dining)")]}
            return hits.get(query, [])

    real = {"id": "6003436950375", "name": "Restaurants (dining)"}
    kept, _ = await verify_interests(Reader(), [real])
    assert kept == [real]
    with pytest.raises(DraftIncomplete, match="no longer confirms"):
        await verify_interests(Reader(), [{"id": "1", "name": "Gone (topic)"}])
