"""Domain rules, starter library, validation, and recommendation logic for hashtags."""

import re

MAX_HASHTAGS = 5
MAX_HASHTAG_LEN = 50  # Including the '#'

# Hashtags must start with '#' and contain only alphanumeric characters and underscores
HASHTAG_PATTERN = re.compile(r"^#[A-Za-z0-9_]{1,49}$")

PREDEFINED_HASHTAGS: dict[str, list[str]] = {
    "Trending & Discovery": ["#FYP", "#ForYou", "#Trending", "#Viral"],
    "Business & Branding": ["#SmallBusiness", "#BusinessGrowth", "#BrandAwareness", "#Entrepreneur"],
    "Marketing & Advertising": ["#DigitalMarketing", "#SocialMediaMarketing", "#MarketingTips", "#AdCampaign"],
    "Shopping & Products": ["#ShopNow", "#NewArrival", "#ProductLaunch", "#BestDeals"],
    "Food & Restaurants": ["#FoodLovers", "#Foodie", "#RestaurantMarketing", "#FoodBusiness"],
    "Fashion & Beauty": ["#FashionTrends", "#StyleInspiration", "#BeautyTips", "#FashionBusiness"],
    "Technology & Startups": ["#TechInnovation", "#StartupLife", "#AI", "#TechBusiness"],
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Food & Restaurants": [
        "food", "restaurant", "cafe", "dining", "dish", "recipe", "bake", "cake", "chef",
        "snack", "dessert", "menu", "beverage", "coffee", "catering", "burger", "pizza",
        "meal", "lunch", "dinner", "breakfast", "sweet", "delicious", "kitchen", "bakery"
    ],
    "Fashion & Beauty": [
        "fashion", "clothing", "apparel", "wear", "dress", "beauty", "skincare", "style",
        "outfit", "cosmetics", "makeup", "jewelry", "salon", "hair", "accessories", "wardrobe",
        "model", "glamour", "spa", "fragrance"
    ],
    "Technology & Startups": [
        "tech", "technology", "software", "ai", "artificial intelligence", "app", "startup",
        "saas", "cloud", "innovation", "code", "coding", "automation", "data", "developer",
        "robotics", "digital", "platform", "algorithm", "gadget", "cyber"
    ],
    "Shopping & Products": [
        "shop", "store", "sale", "discount", "product", "deal", "order", "ecommerce",
        "buy", "collection", "arrival", "retail", "offer", "cart", "goods", "merchandise",
        "promo", "price"
    ],
    "Marketing & Advertising": [
        "marketing", "advertising", "agency", "lead", "campaign", "growth", "traffic",
        "conversion", "seo", "content", "social media", "branding", "audience", "strategy",
        "promotional", "sales"
    ],
    "Business & Branding": [
        "business", "brand", "entrepreneur", "small business", "company", "startup",
        "founder", "corporate", "success", "enterprise", "clients", "services"
    ],
}


def normalize_hashtag(raw: str) -> tuple[str | None, str | None]:
    """Normalize a hashtag input into standard `#Tag` format.
    
    Returns (normalized_tag, error_message).
    """
    if not raw or not isinstance(raw, str):
        return None, "Hashtag cannot be empty"

    cleaned = raw.strip()
    if not cleaned or cleaned == "#":
        return None, "Hashtag cannot be empty"

    # Reject spaces within the hashtag
    if any(c.isspace() for c in cleaned):
        return None, "Hashtags cannot contain spaces"

    # Ensure leading '#'
    if not cleaned.startswith("#"):
        cleaned = f"#{cleaned}"

    if len(cleaned) > MAX_HASHTAG_LEN:
        return None, f"Hashtag cannot exceed {MAX_HASHTAG_LEN} characters"

    if not HASHTAG_PATTERN.match(cleaned):
        return (
            None,
            "Hashtags can only contain letters, numbers, and underscores (e.g., #MyBrand_2026)",
        )

    return cleaned, None


def validate_hashtag_list(tags: list[str]) -> tuple[list[str], list[str]]:
    """Validate, normalize, and deduplicate a list of hashtags.
    
    Returns (valid_normalized_tags, list_of_errors).
    Enforces maximum 5 hashtags and case-insensitive deduplication.
    """
    if not tags:
        return [], []

    valid_tags: list[str] = []
    seen_lower: set[str] = set()
    errors: list[str] = []

    for tag in tags:
        normalized, err = normalize_hashtag(tag)
        if err:
            errors.append(f"Invalid hashtag '{tag}': {err}")
            continue

        lower = normalized.lower()
        if lower in seen_lower:
            # Case-insensitive duplicate
            continue

        seen_lower.add(lower)
        valid_tags.append(normalized)

    if len(valid_tags) > MAX_HASHTAGS:
        errors.append(f"A maximum of {MAX_HASHTAGS} hashtags can be selected (got {len(valid_tags)})")

    return valid_tags[:MAX_HASHTAGS], errors


def recommend_hashtags(context_text: str, limit: int = 10) -> list[str]:
    """Recommend starter library hashtags based on content keywords.
    
    Returns recommended hashtags prioritized by match score, falling back to trending/business tags.
    """
    text_lower = (context_text or "").lower()
    category_scores: dict[str, int] = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            category_scores[category] = score

    recommended: list[str] = []
    seen: set[str] = set()

    # Sort matched categories by score descending
    sorted_categories = sorted(category_scores.keys(), key=lambda c: category_scores[c], reverse=True)

    for cat in sorted_categories:
        for tag in PREDEFINED_HASHTAGS.get(cat, []):
            if tag.lower() not in seen:
                seen.add(tag.lower())
                recommended.append(tag)
                if len(recommended) >= limit:
                    return recommended

    # Fill remaining from Business & Branding and Trending & Discovery
    fallback_categories = ["Business & Branding", "Trending & Discovery", "Marketing & Advertising"]
    for cat in fallback_categories:
        for tag in PREDEFINED_HASHTAGS.get(cat, []):
            if tag.lower() not in seen:
                seen.add(tag.lower())
                recommended.append(tag)
                if len(recommended) >= limit:
                    return recommended

    return recommended[:limit]


def format_caption_with_hashtags(
    caption: str, hashtags: list[str], max_hashtags: int = MAX_HASHTAGS
) -> str:
    """Format final caption by appending hashtags with appropriate spacing.
    
    - Preserves existing caption text and formatting.
    - Appends up to max_hashtags valid hashtags.
    - Does not duplicate hashtags already present in the caption text.
    """
    valid_tags, _ = validate_hashtag_list(hashtags)
    if not valid_tags:
        return caption or ""

    clean_caption = (caption or "").strip()
    caption_words = {w.lower() for w in re.findall(r"#?\b\w+\b", clean_caption)}

    # Filter out hashtags that already appear in caption text
    tags_to_add: list[str] = []
    for tag in valid_tags[:max_hashtags]:
        word_without_hash = tag[1:].lower()
        if tag.lower() not in clean_caption.lower() and word_without_hash not in caption_words:
            tags_to_add.append(tag)
        elif tag.lower() in clean_caption.lower():
            # Already in caption, do not re-append
            continue
        else:
            tags_to_add.append(tag)

    if not tags_to_add:
        return clean_caption

    hashtags_block = " ".join(tags_to_add)
    if not clean_caption:
        return hashtags_block

    return f"{clean_caption}\n\n{hashtags_block}"
