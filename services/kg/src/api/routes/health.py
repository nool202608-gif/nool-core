from fastapi import APIRouter

from shared.types import HealthStatus

router = APIRouter()


@router.get("/health", response_model=HealthStatus)
async def health() -> HealthStatus:
    """Process health only - no dependency checks. See /ready for those."""
    return HealthStatus()
