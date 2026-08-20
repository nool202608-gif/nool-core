from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Common environment-driven configuration every service inherits.

    Subclasses set their own ``service_name`` default and add
    service-specific fields (database credentials, Firebase config, ...).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
