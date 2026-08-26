from shared.config import BaseServiceSettings


class AuthSettings(BaseServiceSettings):
    service_name: str = "auth"

    firebase_project_id: str | None = None
    firebase_credentials_path: str | None = None
    # Same Web API key each frontend already carries as
    # NEXT_PUBLIC_FIREBASE_API_KEY (public by design - see .env.example) -
    # needed here too now that the password credential check happens
    # server-side (POST /api/v1/login) instead of client-side.
    firebase_web_api_key: str | None = None


def get_settings() -> AuthSettings:
    """Reads settings from the environment on every call so tests can vary
    env vars per-case without dealing with cache invalidation.
    """
    return AuthSettings()
