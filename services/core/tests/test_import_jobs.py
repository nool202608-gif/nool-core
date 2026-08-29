"""Ingestion visibility - ImportJob rows written by the three bulk .csv/
.xlsx routes (teacher bulk-invite, student bulk-create, custom-question
bulk-import) plus Super Admin's cross-tenant GET /admin/import-jobs. Real
rows against the dev Postgres via db_session, same pattern as
test_reporting.py; the fake-upload/fake-provisioning setup mirrors
test_school_admin_edits.py's own bulk-import tests.
"""

import uuid

import pytest

from src.api.routes import admin, school_admin
from src.domain.models import ImportJobType, Role, School, User, UserStatus
from src.services import user_provisioning


class _FakeUploadFile:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


@pytest.fixture(autouse=True)
def _fake_provisioning(monkeypatch):
    def fake_create(*, email, display_name, role):
        return user_provisioning.ProvisionedUser(firebase_uid=f"uid-{email}", temp_password="TempPass123")

    monkeypatch.setattr(school_admin, "create_firebase_user", fake_create)


async def _seed_school(db_session) -> School:
    school = School(name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email=f"{uuid.uuid4()}@b.com")
    db_session.add(school)
    await db_session.flush()
    return school


async def _seed_school_admin(db_session, school_id) -> User:
    admin_user = User(
        firebase_uid=f"admin-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Admin", role=Role.SCHOOL_ADMIN, school_id=school_id, status=UserStatus.ACTIVE,
    )
    db_session.add(admin_user)
    await db_session.flush()
    return admin_user


async def _seed_super_admin(db_session) -> User:
    su = User(
        firebase_uid=f"super-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Super", role=Role.SUPER_ADMIN, school_id=None, status=UserStatus.ACTIVE,
    )
    db_session.add(su)
    await db_session.flush()
    return su


async def test_teacher_bulk_invite_records_an_import_job(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    super_admin = await _seed_super_admin(db_session)

    csv_content = "displayName,email\nAda Lovelace,ada@example.com\n,missing-name@example.com\n".encode()
    upload = _FakeUploadFile("teachers.csv", csv_content)

    result = await school_admin.bulk_invite_teachers(file=upload, user=admin_user, session=db_session)
    assert result.created_count == 1
    assert result.error_count == 1

    # Scoped by school_id, not left unfiltered - the dev Postgres this runs
    # against is shared with real, previously-committed rows from live UI
    # testing sessions, so an unfiltered list isn't reliably empty/small.
    jobs = await admin.list_import_jobs(job_type=None, school_id=str(school.id), _=super_admin, session=db_session)
    assert jobs.total == 1
    job = jobs.items[0]
    assert job.job_type == ImportJobType.TEACHER_INVITE
    assert job.filename == "teachers.csv"
    assert job.row_count == 2
    assert job.created_count == 1
    assert job.error_count == 1
    assert job.school_name == school.name
    assert job.initiated_by_name == admin_user.display_name


async def test_import_jobs_filter_by_type_and_school(db_session):
    # Baselines captured before this test's own writes, then asserted as
    # deltas - the dev Postgres this runs against is shared with real,
    # previously-committed rows from live UI testing sessions, so an
    # unfiltered/type-wide list isn't reliably empty going in.
    super_admin = await _seed_super_admin(db_session)
    baseline_all = (
        await admin.list_import_jobs(job_type=None, school_id=None, _=super_admin, session=db_session)
    ).total
    baseline_teacher = (
        await admin.list_import_jobs(
            job_type=ImportJobType.TEACHER_INVITE, school_id=None, _=super_admin, session=db_session
        )
    ).total
    baseline_question_ids = {
        j.id
        for j in (
            await admin.list_import_jobs(
                job_type=ImportJobType.CUSTOM_QUESTION, school_id=None, _=super_admin, session=db_session
            )
        ).items
    }

    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_school_admin(db_session, school_a.id)
    admin_b = await _seed_school_admin(db_session, school_b.id)

    await school_admin.bulk_invite_teachers(
        file=_FakeUploadFile("a.csv", b"displayName,email\nA One,a1@example.com\n"),
        user=admin_a, session=db_session,
    )
    await school_admin.bulk_invite_teachers(
        file=_FakeUploadFile("b.csv", b"displayName,email\nB One,b1@example.com\n"),
        user=admin_b, session=db_session,
    )

    all_jobs = await admin.list_import_jobs(job_type=None, school_id=None, _=super_admin, session=db_session)
    assert all_jobs.total == baseline_all + 2

    school_a_jobs = await admin.list_import_jobs(
        job_type=None, school_id=str(school_a.id), _=super_admin, session=db_session
    )
    assert school_a_jobs.total == 1
    assert school_a_jobs.items[0].filename == "a.csv"

    teacher_jobs = await admin.list_import_jobs(
        job_type=ImportJobType.TEACHER_INVITE, school_id=None, _=super_admin, session=db_session
    )
    assert teacher_jobs.total == baseline_teacher + 2

    question_jobs = await admin.list_import_jobs(
        job_type=ImportJobType.CUSTOM_QUESTION, school_id=None, _=super_admin, session=db_session
    )
    assert {j.id for j in question_jobs.items} == baseline_question_ids


async def test_student_bulk_create_records_an_import_job(db_session):
    from src.domain.models import SchoolClass

    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    super_admin = await _seed_super_admin(db_session)
    school_class = SchoolClass(school_id=school.id, grade=5, section="A")
    db_session.add(school_class)
    await db_session.flush()

    csv_content = (
        "displayName,email,classGrade,classSection,rollNumber\n"
        "Row One,r1@example.com,5,A,1\n"
    ).encode()
    upload = _FakeUploadFile("students.csv", csv_content)

    result = await school_admin.bulk_create_students(file=upload, user=admin_user, session=db_session)
    assert result.created_count == 1

    jobs = await admin.list_import_jobs(
        job_type=ImportJobType.STUDENT_CREATE, school_id=None, _=super_admin, session=db_session
    )
    assert jobs.total == 1
    assert jobs.items[0].filename == "students.csv"
    assert jobs.items[0].created_count == 1
