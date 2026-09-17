from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.errors import register_exception_handlers
from shared.logging import RequestContextMiddleware, configure_logging, get_logger
from shared.tracing import configure_tracing

from src.api.routes import curriculum, health, question_paper, ready, voice_test
from src.config.settings import get_settings
from src.services.neo4j_client import dispose_driver, init_driver


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.service_name, settings.log_level)
    logger = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Building the driver does not open a connection - that only
        # happens on first use - so this is safe even if Neo4j/the
        # required env vars aren't ready yet at boot (mirrors Core's
        # init_engine, which has the same property for Postgres).
        if settings.neo4j_uri and settings.neo4j_user and settings.neo4j_password:
            init_driver(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
        logger.info("startup_complete")
        yield
        await dispose_driver()
        logger.info("shutdown_complete")

    app = FastAPI(title="nool-core KG Service", lifespan=lifespan)

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    configure_tracing(app, settings.service_name, settings.otel_exporter_otlp_endpoint)

    app.include_router(health.router)
    app.include_router(ready.router)
    app.include_router(curriculum.router)
    app.include_router(question_paper.router)
    app.include_router(voice_test.router)

    return app


app = create_app()
