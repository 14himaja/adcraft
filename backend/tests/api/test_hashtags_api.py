import pytest
from app.domain.hashtags import (
    MAX_HASHTAGS,
    PREDEFINED_HASHTAGS,
    format_caption_with_hashtags,
    normalize_hashtag,
    recommend_hashtags,
    validate_hashtag_list,
)

AUTH_PAYLOAD = {"email": "hashtag_test@example.com", "password": "password123"}


async def register_and_login(client):
    await client.post("/auth/register", json=AUTH_PAYLOAD)
    res = await client.post("/auth/login", json=AUTH_PAYLOAD)
    assert res.status_code == 200


def test_hashtag_normalization():
    # Accepts with or without '#'
    tag1, err1 = normalize_hashtag("SmallBusiness")
    assert err1 is None
    assert tag1 == "#SmallBusiness"

    tag2, err2 = normalize_hashtag("#Trending")
    assert err2 is None
    assert tag2 == "#Trending"

    # Preserves underscores and alphanumeric
    tag3, err3 = normalize_hashtag("Brand_2026")
    assert err3 is None
    assert tag3 == "#Brand_2026"

    # Rejects empty or only '#'
    _, err_empty = normalize_hashtag("")
    assert err_empty is not None

    _, err_hash = normalize_hashtag("#")
    assert err_hash is not None

    # Rejects spaces
    _, err_spaces = normalize_hashtag("My New Brand")
    assert err_spaces is not None
    assert "spaces" in err_spaces.lower()

    # Rejects invalid characters
    _, err_special = normalize_hashtag("#Brand-Name!")
    assert err_special is not None

    # Rejects excessively long hashtags (>50)
    _, err_long = normalize_hashtag("A" * 55)
    assert err_long is not None


def test_validate_hashtag_list():
    # Valid list with duplicates differing in case
    tags = ["#DigitalMarketing", "digitalmarketing", "DIGITALMARKETING", "#SocialMedia", "Growth"]
    valid, errors = validate_hashtag_list(tags)
    assert errors == []
    assert valid == ["#DigitalMarketing", "#SocialMedia", "#Growth"]

    # Maximum 5 hashtags enforced
    six_tags = ["#One", "#Two", "#Three", "#Four", "#Five", "#Six"]
    valid_six, errors_six = validate_hashtag_list(six_tags)
    assert len(valid_six) == 5
    assert any("maximum of 5" in e.lower() for e in errors_six)


def test_format_caption_with_hashtags():
    caption = "Discover our latest collection! Shop your favorites today."
    hashtags = ["#SmallBusiness", "#Trending", "#ShopNow"]
    formatted = format_caption_with_hashtags(caption, hashtags)
    assert formatted == "Discover our latest collection! Shop your favorites today.\n\n#SmallBusiness #Trending #ShopNow"

    # Does not duplicate hashtags already present in caption
    caption_with_tag = "Visit our #Bakery today!"
    formatted2 = format_caption_with_hashtags(caption_with_tag, ["#Bakery", "#FoodLovers"])
    assert formatted2 == "Visit our #Bakery today!\n\n#FoodLovers"

    # Empty caption only includes hashtags
    formatted_empty = format_caption_with_hashtags("", ["#AI", "#Tech"])
    assert formatted_empty == "#AI #Tech"


def test_recommend_hashtags():
    # Restaurant content recommends food hashtags
    food_recs = recommend_hashtags("Italian restaurant serving fresh pizza and pasta with organic ingredients")
    assert any(tag in PREDEFINED_HASHTAGS["Food & Restaurants"] for tag in food_recs)

    # Fashion content recommends fashion hashtags
    fashion_recs = recommend_hashtags("New summer dress collection, luxury clothing, and skincare beauty tips")
    assert any(tag in PREDEFINED_HASHTAGS["Fashion & Beauty"] for tag in fashion_recs)

    # Technology content recommends tech hashtags
    tech_recs = recommend_hashtags("AI automated marketing software SaaS platform for startups")
    assert any(tag in PREDEFINED_HASHTAGS["Technology & Startups"] for tag in tech_recs)


async def test_hashtags_api_get_and_custom_persistence(client):
    await register_and_login(client)

    # 1. GET /hashtags returns starter library and categories
    res = await client.get("/hashtags")
    assert res.status_code == 200
    data = res.json()
    assert "categories" in data
    assert "Trending & Discovery" in data["categories"]
    assert "Food & Restaurants" in data["categories"]
    assert data["max_limit"] == 5
    assert data["custom"] == []

    # 2. POST /hashtags/custom adds a user custom hashtag
    add_res = await client.post("/hashtags/custom", json={"hashtag": "MyNewBrand"})
    assert add_res.status_code == 200
    add_data = add_res.json()
    assert add_data["hashtag"] == "#MyNewBrand"
    assert "#MyNewBrand" in add_data["custom"]

    # 3. GET /hashtags returns updated custom hashtags for the user
    res2 = await client.get("/hashtags")
    assert "#MyNewBrand" in res2.json()["custom"]

    # 4. Duplicate addition is idempotent
    add_dup = await client.post("/hashtags/custom", json={"hashtag": "#mynewbrand"})
    assert add_dup.status_code == 200

    # 5. Invalid custom hashtag rejected with 422
    add_invalid = await client.post("/hashtags/custom", json={"hashtag": "Invalid Has Space"})
    assert add_invalid.status_code == 422

    # 6. DELETE /hashtags/custom/{tag} removes the custom hashtag
    del_res = await client.delete("/hashtags/custom/MyNewBrand")
    assert del_res.status_code == 200
    assert "#MyNewBrand" not in del_res.json()["custom"]


async def test_hashtags_api_validate(client):
    await register_and_login(client)
    res = await client.post(
        "/hashtags/validate",
        json={"hashtags": ["Trending", "#SmallBusiness", "DigitalMarketing", "#FYP", "#Viral"]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_valid"] is True
    assert len(data["valid"]) == 5
    assert data["valid"][0] == "#Trending"


async def test_campaign_with_hashtags_persistence(client):
    await register_and_login(client)

    payload = {
        "title": "Summer Campaign",
        "objective": "TRAFFIC",
        "landing_url": "https://example.com/summer",
        "daily_budget": 100,
        "selected_hashtags": ["#ShopNow", "#BestDeals", "#Trending"],
        "custom_hashtags": ["#Summer2026"],
    }
    create_res = await client.post("/campaigns", json=payload)
    assert create_res.status_code == 200
    campaign = create_res.json()
    assert campaign["selected_hashtags"] == ["#ShopNow", "#BestDeals", "#Trending"]
    assert campaign["custom_hashtags"] == ["#Summer2026"]

    # Update hashtags
    update_res = await client.put(
        f"/campaigns/{campaign['id']}",
        json={"selected_hashtags": ["#ShopNow", "#NewArrival", "#Viral"]},
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["selected_hashtags"] == ["#ShopNow", "#NewArrival", "#Viral"]

    # Duplicate preserves hashtags
    dup_res = await client.post(f"/campaigns/{campaign['id']}/duplicate")
    assert dup_res.status_code == 200
    duplicated = dup_res.json()
    assert duplicated["selected_hashtags"] == ["#ShopNow", "#NewArrival", "#Viral"]


async def test_campaign_rejects_more_than_five_hashtags(client):
    await register_and_login(client)
    payload = {
        "title": "Too Many Hashtags Campaign",
        "selected_hashtags": ["#1", "#2", "#3", "#4", "#5", "#6"],
    }
    res = await client.post("/campaigns", json=payload)
    assert res.status_code == 422


async def test_dynamic_ai_hashtag_agent_examples():
    """Verify dynamic AI hashtag agent generates distinct, ad-specific hashtags for different ads."""
    from app.agents.hashtag_agent import generate_ad_hashtags

    # Example 1: Burger Advertisement
    burger_ad = {
        "idea": "Delicious Burger limited time offer with crispy fries and cold drink",
        "headline": "Juicy Gourmet Burger",
        "primary_text": "Taste the finest handcrafted burgers delivered fresh to your door.",
        "business_category": "Food & Restaurants",
    }
    burger_tags = await generate_ad_hashtags(burger_ad)
    assert len(burger_tags) == 5
    assert any("burger" in t.lower() or "food" in t.lower() for t in burger_tags)

    # Example 2: Fashion Advertisement
    fashion_ad = {
        "idea": "Luxury autumn fashion collection chic styling and trendy outfits",
        "headline": "New Season Style",
        "primary_text": "Elevate your look with our exclusive designer apparel and boutique collection.",
        "business_category": "Fashion & Beauty",
    }
    fashion_tags = await generate_ad_hashtags(fashion_ad)
    assert len(fashion_tags) == 5
    assert any("fashion" in t.lower() or "style" in t.lower() or "ootd" in t.lower() for t in fashion_tags)
    # Never identical to burger tags
    assert burger_tags != fashion_tags

    # Example 3: AI Product Advertisement
    ai_ad = {
        "idea": "AI automated workflow product for tech startups and software developers",
        "headline": "Smarter Workflows with AI",
        "primary_text": "Boost your team productivity using next-gen deep learning and cloud tools.",
        "business_category": "Technology & Startups",
    }
    ai_tags = await generate_ad_hashtags(ai_ad)
    assert len(ai_tags) == 5
    assert any("ai" in t.lower() or "tech" in t.lower() or "startup" in t.lower() for t in ai_tags)
    # Distinct from both
    assert ai_tags != burger_tags
    assert ai_tags != fashion_tags


async def test_hashtags_recommend_endpoint(client):
    await register_and_login(client)

    # Call /hashtags/recommend with burger context
    res_burger = await client.post(
        "/hashtags/recommend",
        json={
            "headline": "Special Double Cheeseburger",
            "primary_text": "Order online for fast delivery. Fresh patties and soft buns.",
            "business_category": "Restaurant",
        },
    )
    assert res_burger.status_code == 200
    burger_data = res_burger.json()
    assert "ai_recommended" in burger_data
    assert len(burger_data["ai_recommended"]) == 5
    assert any("burger" in t.lower() or "food" in t.lower() for t in burger_data["ai_recommended"])

    # Call /hashtags/recommend with fashion context
    res_fashion = await client.post(
        "/hashtags/recommend",
        json={
            "headline": "Exclusive Spring Collection",
            "primary_text": "Shop new dresses and runway styles today.",
            "business_category": "Fashion",
        },
    )
    assert res_fashion.status_code == 200
    fashion_data = res_fashion.json()
    assert len(fashion_data["ai_recommended"]) == 5
    assert fashion_data["ai_recommended"] != burger_data["ai_recommended"]


async def test_campaign_draft_preselects_ai_hashtags(client):
    """When a new ad is generated from an idea, up to 5 dynamic AI hashtags are recommended and pre-selected."""
    await register_and_login(client)

    idea = "Promote artisan stone-baked pizza restaurant in Bangalore with home delivery"
    draft_res = await client.post("/campaigns/draft", json={"idea": idea})
    assert draft_res.status_code == 200
    campaign = draft_res.json()

    assert "selected_hashtags" in campaign
    assert len(campaign["selected_hashtags"]) <= 5
    assert len(campaign["selected_hashtags"]) > 0
    # Pre-selected tags dynamically generated for the draft
    assert any(
        "pizza" in t.lower()
        or "food" in t.lower()
        or "restaurant" in t.lower()
        or "cafe" in t.lower()
        or "coffee" in t.lower()
        for t in campaign["selected_hashtags"]
    )

