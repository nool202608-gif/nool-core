import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import IdMixin, TimestampMixin


class Role(str, Enum):
    """Matches root CLAUDE.md's "Initial roles" exactly."""

    SUPER_ADMIN = "SUPER_ADMIN"
    SCHOOL_ADMIN = "SCHOOL_ADMIN"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"


class UserStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    DEACTIVATED = "DEACTIVATED"


class SchoolStatus(str, Enum):
    ONBOARDING = "ONBOARDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class SubscriptionStatus(str, Enum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELED = "CANCELED"


class Plan(IdMixin, Base):
    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String, unique=True)
    price_label: Mapped[str] = mapped_column(String)
    teacher_limit: Mapped[int] = mapped_column(Integer)
    student_limit: Mapped[int] = mapped_column(Integer)
    # NULL = unlimited. Enforced as a lifetime total count per school, not
    # per billing period - there is no billing-cycle infrastructure in this
    # schema yet (see docs/OBSERVABILITY.md-style judgment-call comments
    # elsewhere in this codebase for the pattern this follows).
    test_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_paper_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Soft-disable so a retired plan doesn't break FK references from
    # schools/subscriptions still on it.
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class School(IdMixin, TimestampMixin, Base):
    __tablename__ = "schools"

    name: Mapped[str] = mapped_column(String)
    board: Mapped[str] = mapped_column(String)
    city: Mapped[str] = mapped_column(String)
    contact_email: Mapped[str] = mapped_column(String)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    principal_name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[SchoolStatus] = mapped_column(
        SAEnum(SchoolStatus, name="school_status"), default=SchoolStatus.ONBOARDING
    )
    # Deprecated as a source of truth - a school's current plan is always
    # resolved via its Subscription row (see
    # src/repositories/subscription_repository.py). Left in place rather
    # than dropped since it costs nothing to keep and dropping a column is
    # a destructive migration for no functional gain.
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id"), nullable=True
    )
    # NULL = use the system default. A mapping of Bloom level name -> target
    # percentage (must sum to 100, enforced in UpdateBloomDistributionIn's
    # validator, not here) - the concrete answer to "customize the
    # teacher-app options from admin," scoped to one option: the Bloom mix
    # Question Paper/Homework generation starts from (see
    # src/services/bloom_defaults.py). School Admin sets their own via
    # PUT /school/curriculum/default-bloom-distribution; Super Admin can
    # set/override any school's via PUT /admin/schools/{id}/default-bloom-distribution.
    default_bloom_distribution: Mapped[dict[str, int] | None] = mapped_column(JSONB, nullable=True)


class Subscription(IdMixin, Base):
    __tablename__ = "subscriptions"

    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), unique=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plans.id"))
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, name="subscription_status"), default=SubscriptionStatus.TRIAL
    )
    renews_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class User(IdMixin, TimestampMixin, Base):
    """Application-level identity. firebase_uid is nullable-until-first-login:
    School Admin's teacher/student invite flow creates this row by email
    before the invitee has ever signed in to Firebase - see root CLAUDE.md's
    Identity section (Firebase UID is an external reference, never the
    primary key).
    """

    __tablename__ = "users"

    firebase_uid: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    display_name: Mapped[str] = mapped_column(String)
    role: Mapped[Role] = mapped_column(SAEnum(Role, name="role"))
    school_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=True
    )
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"), default=UserStatus.ACTIVE
    )
    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
    employee_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # True from account creation until the invitee changes their temp
    # password - see src/services/user_provisioning.py and
    # POST /api/v1/me/acknowledge-password-change. Mirrored onto the
    # Firebase custom claim of the same name for clients that only ever
    # call the claim-only Auth service /me (nool-apps).
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(IdMixin, TimestampMixin, Base):
    """Every state-changing Super Admin action, across every school - see
    GET /api/v1/admin/audit-log.
    """

    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String)
    target_type: Mapped[str] = mapped_column(String)
    target_id: Mapped[str] = mapped_column(String)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
