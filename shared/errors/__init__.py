"""Shared error types and the FastAPI exception handlers that render them."""

from .exceptions import (
    AppError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from .handlers import register_exception_handlers

__all__ = [
    "AppError",
    "ForbiddenError",
    "NotFoundError",
    "UnauthorizedError",
    "ValidationError",
    "register_exception_handlers",
]
