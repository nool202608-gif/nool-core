from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from shared.types import ReadinessCheck, ReadinessStatus

from src.repositories.database import check_connection

router = APIRouter()


@router.get("/ready")
async def ready() -> JSONResponse:
    db_ok = await check_connection()
    checks = [
        ReadinessCheck(
            name="database",
            ok=db_ok,
            detail=None if db_ok else "unable to reach PostgreSQL",
        )
    ]
    payload = ReadinessStatus(status="ready" if db_ok else "not_ready", checks=checks)
    status_code = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=payload.model_dump())
