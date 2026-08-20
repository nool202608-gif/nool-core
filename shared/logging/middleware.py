import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from .context import request_id_ctx_var
from .setup import get_logger

REQUEST_ID_HEADER = "X-Request-ID"

logger = get_logger("access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates a request ID and logs one structured access line per request.

    Reads ``X-Request-ID`` from the incoming request (as forwarded by NGINX)
    or generates a new one, binds it to a contextvar so log records emitted
    anywhere during the request carry it, and echoes it back on the response.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        token = request_id_ctx_var.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "unhandled_exception",
                extra={
                    "route": request.url.path,
                    "method": request.method,
                    "duration_ms": duration_ms,
                },
            )
            raise
        else:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "request_completed",
                extra={
                    "route": request.url.path,
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        finally:
            request_id_ctx_var.reset(token)
