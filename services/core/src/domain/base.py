from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every ORM model in Core.

    Importing src.domain.models (which imports every model module below)
    registers all tables on Base.metadata - database/migrations/env.py
    points Alembic's target_metadata at this, so autogenerate sees the
    full schema.
    """
