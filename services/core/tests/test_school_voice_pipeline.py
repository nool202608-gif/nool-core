"""Per-school colearner pipeline selection (School.voice_pipeline) - Super
Admin only, same precedent/shape as test_school_logo.py's logo tests. No
School Admin self-service endpoint exists for this setting (unlike logo/
default-bloom-distribution) - which pipeline a school uses is a platform
decision, not a school one.
"""

import uuid

from src.api.routes import admin
from src.api.schemas.voice_pipeline import UpdateVoicePipelineIn
from src.domain.models import Role, School, User, UserStatus


async def _seed_school(db_session) -> School:
    school = School(name="Test School", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()
    return school


async def _seed_super_admin(db_session) -> User:
    super_admin = User(
        firebase_uid=f"super-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Super", role=Role.SUPER_ADMIN, school_id=None, status=UserStatus.ACTIVE,
    )
    db_session.add(super_admin)
    await db_session.flush()
    return super_admin


async def test_admin_get_school_voice_pipeline_defaults_to_none(db_session):
    school = await _seed_school(db_session)
    super_admin = await _seed_super_admin(db_session)

    out = await admin.get_school_voice_pipeline(str(school.id), _=super_admin, session=db_session)

    assert out.voice_pipeline is None


async def test_admin_can_set_and_clear_a_schools_voice_pipeline(db_session):
    school = await _seed_school(db_session)
    super_admin = await _seed_super_admin(db_session)

    set_out = await admin.update_school_voice_pipeline(
        str(school.id), UpdateVoicePipelineIn(voice_pipeline="multimodal"), actor=super_admin, session=db_session,
    )
    assert set_out.voice_pipeline == "multimodal"
    await db_session.refresh(school)
    assert school.voice_pipeline == "multimodal"

    clear_out = await admin.update_school_voice_pipeline(
        str(school.id), UpdateVoicePipelineIn(voice_pipeline=None), actor=super_admin, session=db_session,
    )
    assert clear_out.voice_pipeline is None
