from fastapi import Header

from shared.auth import AuthenticatedUser, verify_token
from shared.errors import UnauthorizedError


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise UnauthorizedError("Missing or malformed Authorization header.")
    return token


def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    """FastAPI dependency: extracts and verifies the caller's Firebase ID
    token. No DB/role resolution here (unlike services/core/src/api/deps.py's
    get_current_app_user) - this service only needs "is the caller
    authenticated," not a resolved application profile.
    """
    token = _extract_bearer_token(authorization)
    return verify_token(token)
