from app.config import Settings
from app.integrations.advertising.models import AdPlatformReadiness
from app.integrations.oauth import list_connections, tenant_scope
from app.meta import connections as meta_connections


async def list_advertising_platforms(db, user: dict, *, settings: Settings) -> dict:
    """Return paid advertising readiness separately from organic social OAuth status."""
    user_id, org_id, _ = tenant_scope(user)
    social_conns = await list_connections(db, user_id=user_id, organization_id=org_id)
    meta_conn = await meta_connections.get_connection(db, user_id)

    meta_active = bool(meta_conn and meta_conn.get("status") == "ACTIVE")
    meta_ad_selected = bool(meta_conn and meta_conn.get("ad_account_id"))
    meta_status = (
        "READY"
        if (meta_active and meta_ad_selected)
        else ("CONNECTED_REQUIRES_SETUP" if meta_active else "NOT_CONNECTED")
    )

    platforms = [
        AdPlatformReadiness(
            id="meta_ads",
            social_platform="facebook",
            name="Meta Ads (Facebook & Instagram)",
            status=meta_status,
            organic_connected=bool(
                meta_active or "facebook" in social_conns or "instagram" in social_conns
            ),
            api_approved=bool(settings.meta_app_id or settings.meta_mode == "fake"),
            billing_supported_india="INR (UPI/Netbanking Prepaid or RBI Card) · 18% GST",
            min_daily_budget="Account- & objective-dependent (~₹90–₹100/day typical)",
            available_features=(
                "ad_account_discovery",
                "campaign_creation",
                "budget_configuration",
                "audience_targeting",
                "ad_creative_creation",
                "campaign_activation_pause",
                "performance_analytics",
            )
            if meta_ad_selected
            else ("ad_account_discovery",),
            gated_features=()
            if meta_ad_selected
            else ("campaign_creation", "campaign_activation_pause"),
            requirements_note="Select a Meta Ad Account with an active payment method in Meta Ads Manager.",
        ),
        AdPlatformReadiness(
            id="linkedin_ads",
            social_platform="linkedin",
            name="LinkedIn Ads",
            status="REQUIRES_API_APPROVAL",
            organic_connected="linkedin" in social_conns and social_conns["linkedin"].get("status") == "ACTIVE",
            api_approved=False,
            billing_supported_india="INR / USD via International Card (No UPI) · 18% GST",
            min_daily_budget="$10 USD/day (~₹850–₹1,000/day) · $100 lifetime min",
            available_features=(),
            gated_features=(
                "ad_account_discovery",
                "campaign_creation",
                "budget_configuration",
                "audience_targeting",
                "campaign_activation_pause",
                "performance_analytics",
            ),
            requirements_note=(
                "Requires separate LinkedIn Advertising API approval, a Company Page, and Campaign Manager billing."
            ),
        ),
    ]

    return {
        "organization_id": org_id,
        "note": "Paid advertising is kept separate from organic OAuth connections and requires Ads API approval + ad account billing.",
        "platforms": [p.to_dict() for p in platforms],
    }

