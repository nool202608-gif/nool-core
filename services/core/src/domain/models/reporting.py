import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import IdMixin, TimestampMixin


class ReportConfiguration(IdMixin, TimestampMixin, Base):
    """A saved dimension/metric/filter selection - see
    src/services/reporting.py's DIMENSIONS registry for what `dimension`
    and each entry of `metrics` are validated against at save time (not
    just at run time), so a saved report can never silently reference a
    dimension/metric that doesn't exist. `dimension`/`metrics` are plain
    strings rather than a Postgres enum deliberately - the registry is
    expected to grow as new analytics surfaces are added, and a string
    column validated at the application layer doesn't need a migration
    for every new entry the way `ALTER TYPE ... ADD VALUE` would.
    """

    __tablename__ = "report_configurations"

    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    # NULL for a Super Admin's cross-tenant report; set for a School
    # Admin's own-school report - same scoping split as SchoolClass/
    # SchoolGrade's own school_id column.
    school_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=True)
    name: Mapped[str] = mapped_column(String)
    dimension: Mapped[str] = mapped_column(String)
    metrics: Mapped[list[str]] = mapped_column(JSONB)
    filters: Mapped[dict] = mapped_column(JSONB, default=dict)


class ReportShare(IdMixin, TimestampMixin, Base):
    """Grants every School Admin at one school read (or read+export) access
    to one Super-Admin-owned report - see requirements.md's Report Sharing
    section. Targets a school, not a specific user: School Admin accounts
    can be reset/reassigned, and "can this school currently see this
    report" is the durable question that survives that, not "can this one
    login."
    """

    __tablename__ = "report_shares"

    report_configuration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_configurations.id")
    )
    shared_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    shared_with_school_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("schools.id"))
    # "VIEW" or "VIEW_EXPORT" - validated at the schema layer
    # (ReportShareAccessLevel), not a DB enum, same reasoning as
    # ReportConfiguration's dimension/metrics above.
    access_level: Mapped[str] = mapped_column(String, default="VIEW")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
