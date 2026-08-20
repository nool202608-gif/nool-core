from fastapi import Header

from shared.auth import AuthenticatedUser, configure_firebase, verify_id_token
from shared.errors import UnauthorizedError

from src.config.settings import get_settings


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise UnauthorizedError("Missing or malformed Authorization header.")
    return token


def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    """Authentication middleware foundation for Core.

    Core verifies Firebase ID tokens independently rather than calling the
    Auth service per-request - Firebase tokens are self-contained JWTs any
    service can verify. Not yet wired to a route: no Core endpoints exist
    to protect until business features land.
    """
    token = _extract_bearer_token(authorization)
    settings = get_settings()
    configure_firebase(settings.firebase_credentials_path, settings.firebase_project_id)
    return verify_id_token(token)
