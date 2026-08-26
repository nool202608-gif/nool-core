from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CamelModel(BaseModel):
    """Base for every request/response schema: Python attributes stay
    snake_case (PEP8, matches the rest of this codebase), but the JSON
    wire format is camelCase - matching nool-apps' reference contract
    (displayName, classId, ...) exactly. `populate_by_name` lets code
    construct instances with either the snake_case attribute name or the
    camelCase alias; `from_attributes` lets a response model be built
    directly from an ORM row via `.model_validate(row)`.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ListEnvelope(CamelModel, Generic[T]):
    """The universal "list" response shape used by every list endpoint in
    the reference contract: {"items": [...], "total": N}.
    """

    items: list[T]
    total: int
