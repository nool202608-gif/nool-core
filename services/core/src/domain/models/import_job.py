import uuid
from enum import Enum

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import IdMixin, TimestampMixin


class ImportJobType(str, Enum):
    TEACHER_INVITE = "TEACHER_INVITE"
    STUDENT_CREATE = "STUDENT_CREATE"
    CUSTOM_QUESTION = "CUSTOM_QUESTION"


class ImportJob(IdMixin, TimestampMixin, Base):
    """A durable, queryable record of one bulk .csv/.xlsx upload run - see
    bulk_import.py's parse_rows/BulkRowResult, used by
    bulk_invite_teachers/bulk_create_students/bulk_import_custom_questions.
    Before this, a run's outcome (who, when, how many succeeded/failed)
    only ever existed in the one HTTP response returned to the uploader
    and a single free-text audit-log line - never queryable again
    afterward, and never visible to Super Admin across schools at all.
    Summary counts only, not a per-row detail dump - see requirements.md's
    ingestion-visibility ask ("who ran what, when, success/failure
    counts"), not a full re-playable import log.
    """

    __tablename__ = "import_jobs"

    school_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("schools.id"))
    initiated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    job_type: Mapped[ImportJobType] = mapped_column(SAEnum(ImportJobType, name="import_job_type"))
    filename: Mapped[str] = mapped_column(String)
    row_count: Mapped[int] = mapped_column(Integer)
    created_count: Mapped[int] = mapped_column(Integer)
    error_count: Mapped[int] = mapped_column(Integer)
