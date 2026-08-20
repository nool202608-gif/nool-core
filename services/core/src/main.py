from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.errors import register_exception_handlers
from shared.logging import RequestContextMiddleware, configure_logging, get_logger

from src.api.routes import health, ready
from src.config.settings import get_settings
from src.repositories.database import dispose_engine, init_engine


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.service_name, settings.log_level)
    logger = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_engine(settings.database_url)
        logger.info("startup_complete")
        yield
        await dispose_engine()
        logger.info("shutdown_complete")

    app = FastAPI(title="nool-core Core Service", lifespan=lifespan)

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(ready.router)

    return app


app = create_app()
