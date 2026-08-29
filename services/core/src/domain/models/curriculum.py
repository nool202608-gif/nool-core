import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import IdMixin


class Subject(IdMixin, Base):
    """A global catalog, not per-school - SchoolCurriculum below controls
    which subjects a given school has enabled.
    """

    __tablename__ = "subjects"

    name: Mapped[str] = mapped_column(String, unique=True)


class Chapter(IdMixin, Base):
    __tablename__ = "chapters"

    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id"))
    name: Mapped[str] = mapped_column(String)


class Topic(IdMixin, Base):
    __tablename__ = "topics"

    chapter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chapters.id"))
    name: Mapped[str] = mapped_column(String)


class SchoolCurriculum(IdMixin, Base):
    """Which subjects a school has enabled - see PUT /api/v1/school/curriculum.
    Scopes what a Teacher at that school sees in GET /api/v1/subjects.
    """

    __tablename__ = "school_curriculum"
    __table_args__ = (UniqueConstraint("school_id", "subject_id"),)

    school_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("schools.id"))
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class GradeSubject(IdMixin, Base):
    """Which subjects a Class (SchoolGrade) teaches - narrower than the
    school-wide SchoolCurriculum toggle above. An admin picks this
    explicitly per Class; it is not auto-derived from the school's own
    enabled-subjects list (a school could enable Math school-wide but not
    every grade teaches it in every board's curriculum). See
    PUT /school/grades/{gradeId}/subjects.
    """

    __tablename__ = "grade_subjects"
    __table_args__ = (UniqueConstraint("grade_id", "subject_id"),)

    grade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("school_grades.id"))
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
