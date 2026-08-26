"""Resolves the Bloom-level mix a new Question Paper/Homework starts from
when the caller didn't specify one - falls back to the owning school's
default_bloom_distribution (see domain/models/foundation.py's School), the
concrete admin-customizable "teacher app option" this covers.
"""

from src.api.schemas.bloom import BloomTarget
from src.domain.models import BloomLevel, School


def resolve_bloom_targets(school: School, provided: list[BloomTarget] | None) -> list[BloomTarget]:
    if provided:
        return provided
    if not school.default_bloom_distribution:
        return []
    return [
        BloomTarget(level=BloomLevel(level), value=value)
        for level, value in school.default_bloom_distribution.items()
    ]
