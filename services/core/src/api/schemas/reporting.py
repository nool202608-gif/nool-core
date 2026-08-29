from datetime import datetime
from typing import Any

from pydantic import field_validator

from .common import CamelModel

VALID_ACCESS_LEVELS = ("VIEW", "VIEW_EXPORT")


class MetricSpecOut(CamelModel):
    key: str
    label: str


class DimensionSpecOut(CamelModel):
    key: str
    label: str
    scope: str
    metrics: list[MetricSpecOut]


class RunReportIn(CamelModel):
    dimension: str
    metrics: list[str]
    filters: dict[str, Any] = {}
    # Ignored server-side for School Admin (their own school_id is always
    # used instead) - only meaningful for a Super Admin drilling into one
    # school's CLASS/SECTION/STUDENT dimensions.
    school_id: str | None = None


class ReportResultOut(CamelModel):
    dimension: str
    metrics: list[str]
    rows: list[dict[str, Any]]


class ReportConfigurationOut(CamelModel):
    id: str
    name: str
    dimension: str
    metrics: list[str]
    filters: dict[str, Any]
    school_id: str | None
    created_at: datetime


class CreateReportConfigurationIn(CamelModel):
    name: str
    dimension: str
    metrics: list[str]
    filters: dict[str, Any] = {}
    school_id: str | None = None


class ReportShareOut(CamelModel):
    id: str
    report_configuration_id: str
    shared_with_school_id: str
    shared_with_school_name: str
    access_level: str
    expires_at: datetime | None
    created_at: datetime


class SharedReportOut(CamelModel):
    """A report as seen from the recipient (School Admin) side - carries
    the config's own shape plus the share's own id/access level, since the
    recipient acts on the share (run/export), not the underlying config
    directly."""

    share_id: str
    name: str
    dimension: str
    metrics: list[str]
    filters: dict[str, Any]
    access_level: str
    shared_by_name: str
    expires_at: datetime | None


class CreateReportShareIn(CamelModel):
    shared_with_school_id: str
    access_level: str = "VIEW"
    expires_at: datetime | None = None

    @field_validator("access_level")
    @classmethod
    def _valid_access_level(cls, value: str) -> str:
        if value not in VALID_ACCESS_LEVELS:
            raise ValueError(f'access_level must be one of {VALID_ACCESS_LEVELS}.')
        return value
