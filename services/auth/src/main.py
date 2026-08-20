from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.errors import register_exception_handlers
from shared.logging import RequestContextMiddleware, configure_logging, get_logger

from src.api.routes import auth, health, ready
from src.config.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.service_name, settings.log_level)
    logger = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("startup_complete")
        yield
        logger.info("shutdown_complete")

    app = FastAPI(title="nool-core Auth Service", lifespan=lifespan)

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(ready.router)
    app.include_router(auth.router)

    return app


app = create_app()
