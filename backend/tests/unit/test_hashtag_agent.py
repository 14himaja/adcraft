"""Comprehensive unit tests for HashtagRecommendationAgent, validation, and publishing logic."""

import pytest
from app.agents.hashtag_agent import (
    HashtagRecommendationAgent,
    HashtagRecommendationResult,
    RecommendedHashtag,
    dynamic_semantic_hashtags,
    generate_ad_hashtags,
    generate_semantic_recommendation,
)
from app.domain.hashtags import (
    MAX_HASHTAGS,
    PREDEFINED_HASHTAGS,
    format_caption_with_hashtags,
    normalize_hashtag,
    recommend_hashtags,
    validate_hashtag_list,
)


# =====================================================================
# 1. Normalization & Validation Tests
# =====================================================================

def test_hashtag_normalization_accepts_with_and_without_hash():
    tag1, err1 = normalize_hashtag("BurgerLovers")
    assert err1 is None
    assert tag1 == "#BurgerLovers"

    tag2, err2 = normalize_hashtag("#Foodie")
    assert err2 is None
    assert tag2 == "#Foodie"

    tag3, err3 = normalize_hashtag("Tech_Startup2026")
    assert err3 is None
    assert tag3 == "#Tech_Startup2026"


def test_hashtag_normalization_rejects_invalid_inputs():
    # Empty or hash only
    assert normalize_hashtag("")[0] is None
    assert normalize_hashtag("   ")[0] is None
    assert normalize_hashtag("#")[0] is None

    # Spaces within tag
    tag_space, err_space = normalize_hashtag("Hashtag With Spaces")
    assert tag_space is None
    assert "spaces" in err_space.lower()

    # Special punctuation/symbols
    tag_sym, err_sym = normalize_hashtag("#Invalid!Tag$")
    assert tag_sym is None

    # Length > 50 chars
    tag_long, err_long = normalize_hashtag("A" * 55)
    assert tag_long is None
    assert "exceed" in err_long.lower()


def test_validate_hashtag_list_deduplicates_and_enforces_limit():
    # Case-insensitive deduplication
    tags = ["#BurgerLovers", "burgerlovers", "BURGERLOVERS", "#Foodie", "FoodDelivery"]
    valid, errors = validate_hashtag_list(tags)
    assert errors == []
    assert valid == ["#BurgerLovers", "#Foodie", "#FoodDelivery"]

    # Limit of 5 strictly enforced
    six_tags = ["#One", "#Two", "#Three", "#Four", "#Five", "#Six"]
    valid_six, errors_six = validate_hashtag_list(six_tags)
    assert len(valid_six) == MAX_HASHTAGS
    assert len(errors_six) > 0
    assert any(f"maximum of {MAX_HASHTAGS}" in e for e in errors_six)


# =====================================================================
# 2. Agent Structured Output & Processing Logic Tests
# =====================================================================

@pytest.mark.asyncio
async def test_agent_structured_output_fields():
    agent = HashtagRecommendationAgent()
    result = await agent.recommend(
        title="Fresh Burger Combo",
        caption="Order gourmet beef and chicken burgers with seasoned fries and cold soda.",
        business_category="Food & Restaurants",
        product_service="Burger meal deal",
        campaign_objective="SALES",
    )

    assert isinstance(result, HashtagRecommendationResult)
    assert result.advertisement_title == "Fresh Burger Combo"
    assert "Food" in result.business_category
    assert isinstance(result.recommended_hashtags, list)
    assert len(result.recommended_hashtags) <= 5
    assert len(result.recommended_hashtags) >= 3

    # Every item has tag and reason
    for item in result.recommended_hashtags:
        assert isinstance(item, RecommendedHashtag)
        assert item.tag.startswith("#")
        assert len(item.reason) > 5

    # Alternatives list
    assert isinstance(result.alternative_hashtags, list)
    assert len(result.alternative_hashtags) >= 1
    # Alternatives do not collide with primary recommendations
    primary_tags = {r.tag.lower() for r in result.recommended_hashtags}
    for alt in result.alternative_hashtags:
        assert alt.lower() not in primary_tags


@pytest.mark.asyncio
async def test_agent_recommends_distinct_hashtags_for_different_domains():
    agent = HashtagRecommendationAgent()

    # 1. Burger / Fast Food
    burger_res = await agent.recommend(
        title="Fresh Burger Combo",
        caption="Try our handcrafted double cheeseburger combo with crispy fries and beverage.",
        business_category="Food & Restaurants",
    )
    burger_tags = [item.tag for item in burger_res.recommended_hashtags]
    assert any("burger" in t.lower() or "food" in t.lower() for t in burger_tags)

    # 2. Fashion & Apparel
    fashion_res = await agent.recommend(
        title="Autumn Elegance Collection",
        caption="Discover trendy dresses, coats, and chic evening outfits in our new lookbook.",
        business_category="Fashion & Beauty",
    )
    fashion_tags = [item.tag for item in fashion_res.recommended_hashtags]
    assert any("fashion" in t.lower() or "style" in t.lower() or "ootd" in t.lower() for t in fashion_tags)

    # 3. AI / Tech Product
    ai_res = await agent.recommend(
        title="Automate Workflows with AI",
        caption="Next-generation AI agents for developer teams, automated data processing, and smart SaaS.",
        business_category="Technology & Startups",
    )
    ai_tags = [item.tag for item in ai_res.recommended_hashtags]
    assert any("ai" in t.lower() or "tech" in t.lower() for t in ai_tags)

    # 4. Coding Course
    coding_res = await agent.recommend(
        title="Fullstack Python Masterclass",
        caption="Learn to code Python in 30 days. Real world backend engineering projects and mentorship.",
        business_category="Education",
    )
    coding_tags = [item.tag for item in coding_res.recommended_hashtags]
    assert any("python" in t.lower() or "code" in t.lower() or "coding" in t.lower() for t in coding_tags)

    # Assert all 4 are distinct
    assert burger_tags != fashion_tags
    assert fashion_tags != ai_tags
    assert ai_tags != coding_tags


@pytest.mark.asyncio
async def test_agent_handles_optional_parameters_gracefully():
    agent = HashtagRecommendationAgent()

    # Only caption provided (no title, category, audience, or platform)
    res_only_caption = await agent.recommend(
        caption="Organic stone-baked sourdough pizza with fresh mozzarella and basil leaves."
    )
    assert len(res_only_caption.recommended_hashtags) >= 3
    assert any("pizza" in r.tag.lower() or "food" in r.tag.lower() for r in res_only_caption.recommended_hashtags)

    # Only title provided
    res_only_title = await agent.recommend(title="Luxury Fitness Studio & Yoga Club")
    assert len(res_only_title.recommended_hashtags) >= 3
    assert any("fitness" in r.tag.lower() or "gym" in r.tag.lower() for r in res_only_title.recommended_hashtags)


@pytest.mark.asyncio
async def test_identical_inputs_produce_valid_unique_tags():
    agent = HashtagRecommendationAgent()
    params = {
        "title": "Artisan Coffee Roasters",
        "caption": "Specialty single-origin espresso and cold brew beans roasted daily in our micro roastery.",
        "business_category": "Food and Beverage",
    }
    res1 = await agent.recommend(**params)
    res2 = await agent.recommend(**params)

    # Both valid
    assert len(res1.recommended_hashtags) == len(res2.recommended_hashtags)
    # Check no duplicate tags in either
    tags1 = [r.tag.lower() for r in res1.recommended_hashtags]
    assert len(tags1) == len(set(tags1))


# =====================================================================
# 3. Caption Formatting & Publishing Integration Tests
# =====================================================================

def test_format_caption_with_hashtags_feed_destination():
    caption = "Taste our newest burger! Handcrafted with organic ingredients."
    tags = ["#BurgerLovers", "#Foodie", "#FoodDelivery"]

    formatted = format_caption_with_hashtags(caption, tags)
    assert formatted == f"{caption}\n\n#BurgerLovers #Foodie #FoodDelivery"


def test_format_caption_does_not_duplicate_existing_caption_tags():
    caption = "Check out our latest #BurgerLovers special offer today!"
    tags = ["#BurgerLovers", "#FoodDelivery", "#Foodie"]

    formatted = format_caption_with_hashtags(caption, tags)
    # #BurgerLovers was already in caption text, so it should not be appended again
    assert formatted == f"{caption}\n\n#FoodDelivery #Foodie"


def test_format_caption_empty_caption_returns_only_hashtags():
    formatted = format_caption_with_hashtags("", ["#SmallBusiness", "#Trending"])
    assert formatted == "#SmallBusiness #Trending"


def test_format_caption_empty_tags_preserves_caption():
    caption = "Original advertisement copy without tags."
    formatted = format_caption_with_hashtags(caption, [])
    assert formatted == caption


# =====================================================================
# 4. Backward Compatibility Helper Tests
# =====================================================================

@pytest.mark.asyncio
async def test_generate_ad_hashtags_backwards_compatible():
    context = {
        "title": "Organic Coffee",
        "primary_text": "Fresh roasted coffee beans with rich aroma.",
        "business_category": "Cafe",
    }
    tags = await generate_ad_hashtags(context)
    assert isinstance(tags, list)
    assert len(tags) == 5
    assert all(t.startswith("#") for t in tags)
    assert any("coffee" in t.lower() or "cafe" in t.lower() for t in tags)


def test_dynamic_semantic_hashtags_returns_five_clean_tags():
    tags = dynamic_semantic_hashtags({"idea": "Handmade leather boots and stylish jackets"})
    assert isinstance(tags, list)
    assert len(tags) == 5
    assert all(t.startswith("#") for t in tags)
    assert any("fashion" in t.lower() or "style" in t.lower() or "boot" in t.lower() or "leather" in t.lower() for t in tags)

