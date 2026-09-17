import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
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
    # Sequence within its subject - the "Journey" chapter map
    # (src/api/routes/journey.py) orders on this to decide which chapter is
    # DONE/CURRENT/LOCKED. Nullable: existing chapters get one via the
    # migration's data backfill (insertion order); a chapter added later
    # without an explicit order sorts after every ordered one.
    order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Which grade this chapter's content belongs to - Subject itself is
    # deliberately grade-agnostic (e.g. one "Science" row spans 9th and
    # 10th), so grade has to live here instead, one level down. NULL means
    # "applies to any grade" (every chapter created before this column
    # existed, or one entered by hand without picking a grade) - GET
    # /subjects/{id}/chapters?grade= treats NULL as always-matching rather
    # than hiding it. Set from the source Dataset's own `grade` by
    # POST /admin/curriculum/sync-from-kg (see admin_catalog.py) - without
    # this, a second-grade's ingested book would silently merge into the
    # same flat chapter list as the first.
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Stable match key for POST /admin/curriculum/sync-from-kg (see
    # admin_catalog.py) - the kg-service's Chapter node id. NULL for every
    # chapter created by hand through the ordinary admin CRUD below; only
    # sync-written rows carry one. Unique so re-sync upserts, never
    # duplicates.
    kg_ref: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)


class Topic(IdMixin, Base):
    __tablename__ = "topics"

    chapter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chapters.id"))
    name: Mapped[str] = mapped_column(String)
    # Same role as Chapter.kg_ref above, one level down (the KG's Section id).
    kg_ref: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)


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
