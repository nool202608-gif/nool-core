import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .foundation import UserStatus
from .mixins import IdMixin, TimestampMixin


class SchoolClass(IdMixin, TimestampMixin, Base):
    __tablename__ = "classes"
    __table_args__ = (UniqueConstraint("school_id", "grade", "section"),)

    school_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("schools.id"))
    grade: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String)
    # Reuses the same PENDING/ACTIVE/DEACTIVATED enum as User.status (a
    # class is only ever ACTIVE or DEACTIVATED in practice, but a second
    # near-identical Postgres enum type for one unused value isn't worth
    # it) - see PATCH /school/classes/{id}/status.
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"), default=UserStatus.ACTIVE
    )


class TeacherClassAssignment(IdMixin, Base):
    """Which teacher teaches which subject to which class - backs both a
    Teacher's implicit class scoping and School Admin's
    PUT /api/v1/school/classes/{classId}/assignments.
    """

    __tablename__ = "teacher_class_assignments"
    __table_args__ = (UniqueConstraint("teacher_id", "class_id", "subject_id"),)

    teacher_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("classes.id"))
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id"))


class StudentProfile(Base):
    """The school-specific half of a STUDENT user - roll number and class
    membership. One-to-one with users (role=STUDENT); kept separate so
    `users` stays role-agnostic.
    """

    __tablename__ = "student_profiles"
    __table_args__ = (UniqueConstraint("class_id", "roll_number"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("classes.id"))
    roll_number: Mapped[int] = mapped_column(Integer)
    guardian_name: Mapped[str | None] = mapped_column(String, nullable=True)
    guardian_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
