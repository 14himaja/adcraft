HEADLINE_MAX = 40
PRIMARY_TEXT_MAX = 125
DESCRIPTION_MAX = 30
VARIANTS_MIN, VARIANTS_MAX = 2, 3
AGE_MIN, AGE_MAX = 18, 65
CTA_ALLOWED = ("LEARN_MORE", "SIGN_UP", "DOWNLOAD", "GET_QUOTE", "CONTACT_US", "SUBSCRIBE")
BANNED_PHRASES = ("guaranteed", "100%", "#1", "risk-free", "best in the world")
PUBLISHER_PLATFORMS = ("instagram",)
DEFAULT_INSTAGRAM_POSITIONS = ("stream",)
IMAGE_MIN_WIDTH = 600
IMAGE_MAX_BYTES = 8 * 1024 * 1024
IMAGE_RATIO_MIN, IMAGE_RATIO_MAX = 0.8, 1.91
IMAGE_FORMATS = ("JPEG", "PNG")
OBJECTIVES = {
    "TRAFFIC": {
        "objective": "OUTCOME_TRAFFIC",
        "optimization_goal": "LINK_CLICKS",
        "billing_event": "IMPRESSIONS",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
    },
    "AWARENESS": {
        "objective": "OUTCOME_AWARENESS",
        "optimization_goal": "REACH",
        "billing_event": "IMPRESSIONS",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
    },
}
REPAIR_MAX = 2
CONTEXT_TURNS = 8
