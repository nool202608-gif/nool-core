from fastapi import Header

from shared.auth import AuthenticatedUser
from shared.errors import UnauthorizedError

from src.config.settings import get_settings
from src.services.token_service import TokenService


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise UnauthorizedError("Missing or malformed Authorization header.")
    return token


def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    """FastAPI dependency: extracts and verifies the caller's Firebase ID token."""
    token = _extract_bearer_token(authorization)
    return TokenService(get_settings()).verify(token)
