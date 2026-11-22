from app.integrations.base.adapter import SocialPlatformAdapter
from app.integrations.base.errors import IntegrationValidationError
from app.integrations.base.models import PLATFORMS_ORDER, PlatformId
from app.integrations.facebook import FacebookAdapter
from app.integrations.instagram import InstagramAdapter
from app.integrations.linkedin import LinkedInAdapter

_ADAPTERS: dict[PlatformId, SocialPlatformAdapter] = {
    "facebook": FacebookAdapter(),
    "instagram": InstagramAdapter(),
    "linkedin": LinkedInAdapter(),
}


def get_adapter(platform: str) -> SocialPlatformAdapter:
    adapter = _ADAPTERS.get(platform)  # type: ignore[arg-type]
    if adapter is None:
        raise IntegrationValidationError(
            f"Unsupported platform {platform!r}",
            {"supported_platforms": list(PLATFORMS_ORDER)},
        )
    return adapter


def list_adapters() -> list[SocialPlatformAdapter]:
    return [_ADAPTERS[pid] for pid in PLATFORMS_ORDER]

