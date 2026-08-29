from typing import Any

from pydantic import field_validator

from .common import CamelModel

VALID_OPERATORS = ("eq", "neq", "contains", "gt", "gte", "lt", "lte", "is_null", "is_not_null")


class ColumnSpecOut(CamelModel):
    key: str
    label: str
    type: str  # "string" | "number" | "boolean" | "datetime" | "uuid"


class EntitySpecOut(CamelModel):
    key: str
    label: str
    columns: list[ColumnSpecOut]


class FilterIn(CamelModel):
    column: str
    operator: str
    value: Any = None

    @field_validator("operator")
    @classmethod
    def _valid_operator(cls, value: str) -> str:
        if value not in VALID_OPERATORS:
            raise ValueError(f'operator must be one of {VALID_OPERATORS}.')
        return value


class SortIn(CamelModel):
    column: str
    direction: str = "asc"

    @field_validator("direction")
    @classmethod
    def _valid_direction(cls, value: str) -> str:
        if value not in ("asc", "desc"):
            raise ValueError('direction must be "asc" or "desc".')
        return value


class ExplorerQueryIn(CamelModel):
    entity: str
    filters: list[FilterIn] = []
    sort: SortIn | None = None
    limit: int = 50
    offset: int = 0

    @field_validator("limit")
    @classmethod
    def _limit_in_range(cls, value: int) -> int:
        if not (1 <= value <= 200):
            raise ValueError("limit must be between 1 and 200.")
        return value

    @field_validator("offset")
    @classmethod
    def _offset_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("offset must be non-negative.")
        return value


class ExplorerQueryOut(CamelModel):
    entity: str
    columns: list[str]
    rows: list[dict[str, Any]]
    total: int
