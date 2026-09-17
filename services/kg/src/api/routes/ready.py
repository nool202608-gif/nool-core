from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from shared.types import ReadinessCheck, ReadinessStatus

from src.services.neo4j_client import check_connection

router = APIRouter()


@router.get("/ready")
async def ready() -> JSONResponse:
    neo4j_ok = await check_connection()
    checks = [
        ReadinessCheck(
            name="neo4j",
            ok=neo4j_ok,
            detail=None if neo4j_ok else "unable to reach Neo4j",
        )
    ]
    payload = ReadinessStatus(status="ready" if neo4j_ok else "not_ready", checks=checks)
    status_code = status.HTTP_200_OK if neo4j_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=payload.model_dump())
