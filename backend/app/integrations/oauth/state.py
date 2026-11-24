import base64
import hashlib
import secrets

from app.config import Settings
from app.integrations.base.errors import InvalidOAuthState
from app.security.jwt import InvalidToken, decode_token, issue_token

STATE_TTL_MINUTES = 15
DEFAULT_RETURN_TO = "/?section=connections"


def sanitize_return_to(return_to: str | None) -> str:
    """Allow only safe relative app paths for post-OAuth redirects."""
    if not return_to or not isinstance(return_to, str):
        return DEFAULT_RETURN_TO
    candidate = return_to.strip()
    if not candidate.startswith("/") or candidate.startswith("//") or "\\" in candidate:
        return DEFAULT_RETURN_TO
    return candidate


def generate_pkce_pair() -> tuple[str, str]:
    """Generate an RFC 7636 PKCE (code_verifier, code_challenge) pair with S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _state_secret(settings: Settings) -> str:
    return f"{settings.jwt_secret}:social_oauth"


def make_oauth_state(
    settings: Settings,
    *,
    user_id,
    organization_id: str,
    platform: str,
    return_to: str | None = None,
    code_verifier: str | None = None,
) -> str:
    extra = {
        "platform": platform,
        "org": organization_id,
        "ret": sanitize_return_to(return_to),
    }
    if code_verifier:
        extra["cv"] = code_verifier
    return issue_token(str(user_id), _state_secret(settings), ttl_minutes=STATE_TTL_MINUTES, extra=extra)


def check_oauth_state(
    settings: Settings,
    state: str,
    *,
    user_id,
    platform: str,
) -> dict:
    try:
        claims = decode_token(state, _state_secret(settings))
    except InvalidToken as exc:
        raise InvalidOAuthState(
            f"The {platform.title()} login link expired or was tampered with. Try connecting again."
        ) from exc
    if claims.get("sub") != str(user_id):
        raise InvalidOAuthState("This OAuth login was started by a different user.")
    if claims.get("platform") != platform:
        raise InvalidOAuthState("OAuth state platform mismatch.")
    return {
        "user_id": claims["sub"],
        "organization_id": claims.get("org") or "personal",
        "return_to": sanitize_return_to(claims.get("ret")),
        "code_verifier": claims.get("cv"),
    }

