from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from shared.types import ReadinessCheck, ReadinessStatus

from src.config.settings import get_settings

router = APIRouter()


@router.get("/ready")
async def ready() -> JSONResponse:
    """Readiness depends on Firebase being configured (project ID present).

    This does not call out to Firebase - it only confirms the service has
    what it needs to verify tokens when a request arrives.
    """
    settings = get_settings()
    configured = bool(settings.firebase_project_id)
    checks = [
        ReadinessCheck(
            name="firebase_config",
            ok=configured,
            detail=None if configured else "FIREBASE_PROJECT_ID is not set",
        )
    ]
    payload = ReadinessStatus(status="ready" if configured else "not_ready", checks=checks)
    status_code = status.HTTP_200_OK if configured else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=payload.model_dump())
