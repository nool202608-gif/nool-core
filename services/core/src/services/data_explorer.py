"""The Data Explorer's entity/column registry and safe query execution -
see requirements.md's "Database / Data Explorer" section.

Deliberately NOT a raw-SQL text box: every query is built through
SQLAlchemy Core against a curated, hand-registered set of tables/columns
below (ENTITIES), with filter/sort inputs validated against that registry
before ever touching a query - an unregistered table or column is
unreachable through this module, full stop, regardless of what a client
sends. All values are bound parameters (SQLAlchemy's `column == value`
etc.), never string-interpolated, so this carries the same injection
protection as every other query in this codebase - the registry's job is
narrowing *which* tables/columns are reachable at all, not just escaping.

Every call to run_query is expected to be audit-logged by its caller (see
admin.py's run_explorer_query) - this module itself is agnostic to who's
calling or why, but the security note in NEXT_STEP.md is explicit that a
platform-wide data-browsing tool needs an audit trail, so the route layer
does that consistently rather than leaving it to be forgotten per-call.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from shared.errors import ValidationError

from src.domain.models import (
    AuditLog,
    Dataset,
    Plan,
    School,
    SchoolClass,
    SchoolCurriculum,
    SchoolDataset,
    SchoolGrade,
    StudentProfile,
    Subject,
    Subscription,
    User,
    VoiceTest,
)


@dataclass(frozen=True)
class ColumnSpec:
    key: str
    label: str
    type: str  # "string" | "number" | "boolean" | "datetime" | "uuid"
    column: InstrumentedAttribute


@dataclass(frozen=True)
class EntitySpec:
    key: str
    label: str
    table: Table
    columns: dict[str, ColumnSpec]
    default_sort: str


def _col(column: InstrumentedAttribute, label: str, type_: str) -> ColumnSpec:
    return ColumnSpec(key=column.key, label=label, type=type_, column=column)


def _columns(*specs: ColumnSpec) -> dict[str, ColumnSpec]:
    return {c.key: c for c in specs}


ENTITIES: dict[str, EntitySpec] = {
    "SCHOOLS": EntitySpec(
        key="SCHOOLS", label="Schools", table=School.__table__, default_sort="name",
        columns=_columns(
            _col(School.id, "ID", "uuid"),
            _col(School.name, "Name", "string"),
            _col(School.board, "Board", "string"),
            _col(School.city, "City", "string"),
            _col(School.contact_email, "Contact email", "string"),
            _col(School.status, "Status", "string"),
            _col(School.created_at, "Created", "datetime"),
        ),
    ),
    "USERS": EntitySpec(
        key="USERS", label="Users (all roles)", table=User.__table__, default_sort="display_name",
        columns=_columns(
            _col(User.id, "ID", "uuid"),
            _col(User.display_name, "Name", "string"),
            _col(User.email, "Email", "string"),
            _col(User.role, "Role", "string"),
            _col(User.school_id, "School ID", "uuid"),
            _col(User.status, "Status", "string"),
            _col(User.created_at, "Created", "datetime"),
        ),
    ),
    "CLASSES": EntitySpec(
        key="CLASSES", label="Classes (grade level)", table=SchoolGrade.__table__, default_sort="grade",
        columns=_columns(
            _col(SchoolGrade.id, "ID", "uuid"),
            _col(SchoolGrade.school_id, "School ID", "uuid"),
            _col(SchoolGrade.grade, "Grade", "number"),
            _col(SchoolGrade.status, "Status", "string"),
            _col(SchoolGrade.created_at, "Created", "datetime"),
        ),
    ),
    "SECTIONS": EntitySpec(
        key="SECTIONS", label="Sections", table=SchoolClass.__table__, default_sort="grade",
        columns=_columns(
            _col(SchoolClass.id, "ID", "uuid"),
            _col(SchoolClass.school_id, "School ID", "uuid"),
            _col(SchoolClass.grade_id, "Class ID", "uuid"),
            _col(SchoolClass.grade, "Grade", "number"),
            _col(SchoolClass.section, "Section", "string"),
            _col(SchoolClass.status, "Status", "string"),
            _col(SchoolClass.created_at, "Created", "datetime"),
        ),
    ),
    "STUDENT_PROFILES": EntitySpec(
        key="STUDENT_PROFILES", label="Student profiles", table=StudentProfile.__table__, default_sort="roll_number",
        columns=_columns(
            _col(StudentProfile.user_id, "User ID", "uuid"),
            _col(StudentProfile.class_id, "Section ID", "uuid"),
            _col(StudentProfile.roll_number, "Roll number", "number"),
            _col(StudentProfile.guardian_name, "Guardian name", "string"),
            _col(StudentProfile.guardian_phone, "Guardian phone", "string"),
        ),
    ),
    "SUBJECTS": EntitySpec(
        key="SUBJECTS", label="Subjects (global catalog)", table=Subject.__table__, default_sort="name",
        columns=_columns(
            _col(Subject.id, "ID", "uuid"),
            _col(Subject.name, "Name", "string"),
        ),
    ),
    "SCHOOL_CURRICULUM": EntitySpec(
        key="SCHOOL_CURRICULUM", label="School subject toggles", table=SchoolCurriculum.__table__,
        default_sort="school_id",
        columns=_columns(
            _col(SchoolCurriculum.id, "ID", "uuid"),
            _col(SchoolCurriculum.school_id, "School ID", "uuid"),
            _col(SchoolCurriculum.subject_id, "Subject ID", "uuid"),
            _col(SchoolCurriculum.enabled, "Enabled", "boolean"),
        ),
    ),
    "DATASETS": EntitySpec(
        key="DATASETS", label="Datasets (global catalog)", table=Dataset.__table__, default_sort="name",
        columns=_columns(
            _col(Dataset.id, "ID", "uuid"),
            _col(Dataset.name, "Name", "string"),
            _col(Dataset.question_count, "Question count", "number"),
            _col(Dataset.description, "Description", "string"),
        ),
    ),
    "SCHOOL_DATASETS": EntitySpec(
        key="SCHOOL_DATASETS", label="School dataset toggles", table=SchoolDataset.__table__,
        default_sort="school_id",
        columns=_columns(
            _col(SchoolDataset.id, "ID", "uuid"),
            _col(SchoolDataset.school_id, "School ID", "uuid"),
            _col(SchoolDataset.dataset_id, "Dataset ID", "uuid"),
            _col(SchoolDataset.enabled, "Enabled", "boolean"),
        ),
    ),
    "PLANS": EntitySpec(
        key="PLANS", label="Subscription plans", table=Plan.__table__, default_sort="name",
        columns=_columns(
            _col(Plan.id, "ID", "uuid"),
            _col(Plan.name, "Name", "string"),
            _col(Plan.price_label, "Price", "string"),
            _col(Plan.teacher_limit, "Teacher limit", "number"),
            _col(Plan.student_limit, "Student limit", "number"),
            _col(Plan.active, "Active", "boolean"),
        ),
    ),
    "SUBSCRIPTIONS": EntitySpec(
        key="SUBSCRIPTIONS", label="Subscriptions", table=Subscription.__table__, default_sort="renews_at",
        columns=_columns(
            _col(Subscription.id, "ID", "uuid"),
            _col(Subscription.school_id, "School ID", "uuid"),
            _col(Subscription.plan_id, "Plan ID", "uuid"),
            _col(Subscription.status, "Status", "string"),
            _col(Subscription.renews_at, "Renews", "datetime"),
        ),
    ),
    "VOICE_TESTS": EntitySpec(
        key="VOICE_TESTS", label="Voice tests", table=VoiceTest.__table__, default_sort="created_at",
        columns=_columns(
            _col(VoiceTest.id, "ID", "uuid"),
            _col(VoiceTest.class_id, "Section ID", "uuid"),
            _col(VoiceTest.subject_id, "Subject ID", "uuid"),
            _col(VoiceTest.status, "Status", "string"),
            _col(VoiceTest.duration_minutes, "Duration (min)", "number"),
            _col(VoiceTest.created_at, "Created", "datetime"),
        ),
    ),
    "AUDIT_LOG": EntitySpec(
        key="AUDIT_LOG", label="Audit log", table=AuditLog.__table__, default_sort="created_at",
        columns=_columns(
            _col(AuditLog.id, "ID", "uuid"),
            _col(AuditLog.actor_id, "Actor ID", "uuid"),
            _col(AuditLog.action, "Action", "string"),
            _col(AuditLog.target_type, "Target type", "string"),
            _col(AuditLog.target_id, "Target ID", "string"),
            _col(AuditLog.created_at, "Created", "datetime"),
        ),
    ),
}


def get_entity(entity_key: str) -> EntitySpec:
    spec = ENTITIES.get(entity_key)
    if spec is None:
        raise ValidationError(f'Unknown explorer entity "{entity_key}".')
    return spec


def _apply_filter(query, col_spec: ColumnSpec, operator: str, value: Any):
    column = col_spec.column
    if operator == "is_null":
        return query.where(column.is_(None))
    if operator == "is_not_null":
        return query.where(column.is_not(None))
    if value is None:
        raise ValidationError(f'A value is required for operator "{operator}".')
    if operator == "eq":
        return query.where(column == value)
    if operator == "neq":
        return query.where(column != value)
    if operator == "contains":
        if col_spec.type != "string":
            raise ValidationError(f'"contains" only applies to text columns, not "{col_spec.key}".')
        return query.where(column.ilike(f"%{value}%"))
    if operator == "gt":
        return query.where(column > value)
    if operator == "gte":
        return query.where(column >= value)
    if operator == "lt":
        return query.where(column < value)
    if operator == "lte":
        return query.where(column <= value)
    raise ValidationError(f'Unsupported operator "{operator}".')  # pragma: no cover - schema already validates


async def run_query(
    session: AsyncSession,
    *,
    entity: str,
    filters: list[dict[str, Any]],
    sort: dict[str, Any] | None,
    limit: int,
    offset: int,
) -> tuple[list[str], list[dict[str, Any]], int]:
    """Returns (column_keys, rows, total_matching_before_pagination)."""
    spec = get_entity(entity)

    # Selects only the registry's own Column objects, not the whole table -
    # a table can have columns that aren't registered here (e.g. a
    # sensitive or simply not-yet-curated field), and those must never be
    # reachable through this endpoint regardless of what a client asks for.
    base = select(*[c.column for c in spec.columns.values()])
    for f in filters:
        col_key = f["column"]
        col_spec = spec.columns.get(col_key)
        if col_spec is None:
            raise ValidationError(f'Unknown column "{col_key}" for entity "{entity}".')
        base = _apply_filter(base, col_spec, f["operator"], f.get("value"))

    count_query = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_query)).scalar_one()

    if sort is not None:
        sort_col_spec = spec.columns.get(sort["column"])
        if sort_col_spec is None:
            raise ValidationError(f'Unknown sort column "{sort["column"]}" for entity "{entity}".')
        order_col = sort_col_spec.column
        base = base.order_by(order_col.desc() if sort.get("direction") == "desc" else order_col.asc())
    else:
        default_col = spec.columns[spec.default_sort].column
        base = base.order_by(default_col.asc())

    base = base.limit(limit).offset(offset)
    result = await session.execute(base)
    column_keys = list(spec.columns.keys())
    rows = [
        {key: _serialize(getattr(row, key)) for key in column_keys}
        for row in result.all()
    ]
    return column_keys, rows, total


def _serialize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):  # Enum
        return value.value
    return str(value)
