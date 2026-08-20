from pydantic import BaseModel


class HealthStatus(BaseModel):
    status: str = "ok"


class ReadinessCheck(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class ReadinessStatus(BaseModel):
    status: str
    checks: list[ReadinessCheck]
