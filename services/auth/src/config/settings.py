from shared.config import BaseServiceSettings


class AuthSettings(BaseServiceSettings):
    service_name: str = "auth"

    firebase_project_id: str | None = None
    firebase_credentials_path: str | None = None


def get_settings() -> AuthSettings:
    """Reads settings from the environment on every call so tests can vary
    env vars per-case without dealing with cache invalidation.
    """
    return AuthSettings()
