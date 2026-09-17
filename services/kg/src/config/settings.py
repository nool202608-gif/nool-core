from shared.config import BaseServiceSettings


class KgSettings(BaseServiceSettings):
    service_name: str = "kg"

    # Same Neo4j the nool-data-ingestion pipeline populates - this service
    # is the only thing in nool-core that talks to it directly (see
    # services/core/src/services/kg_client.py for the HTTP seam everything
    # else goes through instead). Blank-safe: the service boots without
    # these, only /ready and the routes that need Neo4j fail until set.
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None

    # Question generation grounded in the KG - see src/services/generator.py.
    openai_api_key: str | None = None


def get_settings() -> KgSettings:
    """Reads settings from the environment on every call so tests can vary
    env vars per-case without dealing with cache invalidation.
    """
    return KgSettings()
