from shared.auth import AuthenticatedUser, configure_firebase, verify_id_token

from src.config.settings import AuthSettings


class TokenService:
    """Verifies Firebase ID tokens on behalf of the Auth service's API layer."""

    def __init__(self, settings: AuthSettings) -> None:
        configure_firebase(settings.firebase_credentials_path, settings.firebase_project_id)

    def verify(self, token: str) -> AuthenticatedUser:
        return verify_id_token(token)
