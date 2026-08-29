"""A Dataset's real question-bank content (DatasetQuestion) - previously
`question_count` was a manually-typed integer with no linkage to actual
question rows (see requirements.md's flagged gap). Also covers Dataset's
new subject_id link. Real rows against the dev Postgres via db_session,
same pattern as test_admin_curriculum_datasets.py.
"""

import uuid

import pytest
from sqlalchemy import select

from shared.errors import NotFoundError, ValidationError

from src.api.routes import admin_catalog
from src.api.schemas.admin_catalog import (
    CreateDatasetIn,
    CreateDatasetQuestionIn,
    UpdateDatasetIn,
    UpdateDatasetQuestionIn,
)
from src.domain.models import BloomLevel, Chapter, Dataset, DatasetQuestion, QuestionType, Role, Subject, User, UserStatus


async def _seed_super_admin(db_session) -> User:
    super_admin = User(
        firebase_uid=f"super-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Super", role=Role.SUPER_ADMIN, school_id=None, status=UserStatus.ACTIVE,
    )
    db_session.add(super_admin)
    await db_session.flush()
    return super_admin


async def _seed_subject(db_session) -> Subject:
    subject = Subject(name=f"Subject-{uuid.uuid4()}")
    db_session.add(subject)
    await db_session.flush()
    return subject


async def _seed_chapter(db_session, subject_id) -> Chapter:
    chapter = Chapter(subject_id=subject_id, name="Chapter 1")
    db_session.add(chapter)
    await db_session.flush()
    return chapter


async def _seed_dataset(db_session, *, subject_id=None, question_count=10) -> Dataset:
    dataset = Dataset(
        name=f"Dataset-{uuid.uuid4()}", question_count=question_count, description="A dataset",
        subject_id=subject_id,
    )
    db_session.add(dataset)
    await db_session.flush()
    return dataset


# --- Dataset <-> Subject link ------------------------------------------------


async def test_create_dataset_with_subject(db_session):
    super_admin = await _seed_super_admin(db_session)
    subject = await _seed_subject(db_session)

    result = await admin_catalog.create_dataset(
        CreateDatasetIn(name="Algebra Bank", question_count=0, description="d", subject_id=str(subject.id)),
        actor=super_admin, session=db_session,
    )
    assert result.subject_id == str(subject.id)


async def test_update_dataset_subject(db_session):
    super_admin = await _seed_super_admin(db_session)
    subject_a = await _seed_subject(db_session)
    subject_b = await _seed_subject(db_session)
    dataset = await _seed_dataset(db_session, subject_id=subject_a.id)

    result = await admin_catalog.update_dataset(
        str(dataset.id), UpdateDatasetIn(subject_id=str(subject_b.id)), actor=super_admin, session=db_session,
    )
    assert result.subject_id == str(subject_b.id)


async def test_update_dataset_can_clear_subject(db_session):
    super_admin = await _seed_super_admin(db_session)
    subject = await _seed_subject(db_session)
    dataset = await _seed_dataset(db_session, subject_id=subject.id)

    result = await admin_catalog.update_dataset(
        str(dataset.id), UpdateDatasetIn(subject_id=None), actor=super_admin, session=db_session,
    )
    assert result.subject_id is None


# --- question_count resolution: real rows win over the manual value --------


async def test_dataset_question_count_falls_back_to_manual_value_when_no_real_rows(db_session):
    super_admin = await _seed_super_admin(db_session)
    dataset = await _seed_dataset(db_session, question_count=50)

    listed = await admin_catalog.list_datasets(_=super_admin, session=db_session)
    row = next(d for d in listed.items if d.id == str(dataset.id))
    assert row.question_count == 50


async def test_dataset_question_count_uses_real_rows_once_any_exist(db_session):
    super_admin = await _seed_super_admin(db_session)
    dataset = await _seed_dataset(db_session, question_count=50)

    await admin_catalog.create_dataset_question(
        str(dataset.id),
        CreateDatasetQuestionIn(
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER,
            text="What is 2+2?", answer="4",
        ),
        actor=super_admin, session=db_session,
    )

    listed = await admin_catalog.list_datasets(_=super_admin, session=db_session)
    row = next(d for d in listed.items if d.id == str(dataset.id))
    assert row.question_count == 1  # real count (1), not the stale manual 50


# --- CRUD -------------------------------------------------------------------


async def test_create_and_list_dataset_question(db_session):
    super_admin = await _seed_super_admin(db_session)
    dataset = await _seed_dataset(db_session)

    created = await admin_catalog.create_dataset_question(
        str(dataset.id),
        CreateDatasetQuestionIn(
            bloom_level=BloomLevel.UNDERSTAND, question_type=QuestionType.SHORT_ANSWER,
            text="Explain photosynthesis.", answer="Plants convert light to energy.",
        ),
        actor=super_admin, session=db_session,
    )
    assert created.dataset_id == str(dataset.id)
    assert created.text == "Explain photosynthesis."

    listed = await admin_catalog.list_dataset_questions(str(dataset.id), _=super_admin, session=db_session)
    assert listed.total == 1
    assert listed.items[0].id == created.id


async def test_create_dataset_question_with_chapter_and_topic(db_session):
    super_admin = await _seed_super_admin(db_session)
    subject = await _seed_subject(db_session)
    chapter = await _seed_chapter(db_session, subject.id)
    dataset = await _seed_dataset(db_session, subject_id=subject.id)

    created = await admin_catalog.create_dataset_question(
        str(dataset.id),
        CreateDatasetQuestionIn(
            chapter_id=str(chapter.id), bloom_level=BloomLevel.APPLY, question_type=QuestionType.LONG_ANSWER,
            text="Apply Newton's second law.", answer="F=ma",
        ),
        actor=super_admin, session=db_session,
    )
    assert created.chapter_id == str(chapter.id)


async def test_create_mcq_dataset_question_requires_options_matching_answer(db_session):
    with pytest.raises(ValueError):
        CreateDatasetQuestionIn(
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.MCQ,
            text="Pick one", answer="C", options=["A", "B"],
        )


async def test_create_mcq_dataset_question_valid_options(db_session):
    super_admin = await _seed_super_admin(db_session)
    dataset = await _seed_dataset(db_session)

    created = await admin_catalog.create_dataset_question(
        str(dataset.id),
        CreateDatasetQuestionIn(
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.MCQ,
            text="Pick one", answer="B", options=["A", "B", "C"],
        ),
        actor=super_admin, session=db_session,
    )
    assert created.answer == "B"
    assert created.options == ["A", "B", "C"]


async def test_create_dataset_question_unknown_dataset_404s(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(NotFoundError):
        await admin_catalog.create_dataset_question(
            str(uuid.uuid4()),
            CreateDatasetQuestionIn(
                bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER,
                text="x", answer="y",
            ),
            actor=super_admin, session=db_session,
        )


async def test_update_dataset_question_text_and_answer(db_session):
    super_admin = await _seed_super_admin(db_session)
    dataset = await _seed_dataset(db_session)
    created = await admin_catalog.create_dataset_question(
        str(dataset.id),
        CreateDatasetQuestionIn(
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER,
            text="Old text", answer="Old answer",
        ),
        actor=super_admin, session=db_session,
    )

    updated = await admin_catalog.update_dataset_question(
        str(dataset.id), created.id,
        UpdateDatasetQuestionIn(text="New text", answer="New answer"),
        actor=super_admin, session=db_session,
    )
    assert updated.text == "New text"
    assert updated.answer == "New answer"


async def test_update_dataset_question_switch_to_mcq_requires_options(db_session):
    super_admin = await _seed_super_admin(db_session)
    dataset = await _seed_dataset(db_session)
    created = await admin_catalog.create_dataset_question(
        str(dataset.id),
        CreateDatasetQuestionIn(
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER,
            text="text", answer="answer",
        ),
        actor=super_admin, session=db_session,
    )

    with pytest.raises(ValidationError):
        await admin_catalog.update_dataset_question(
            str(dataset.id), created.id,
            UpdateDatasetQuestionIn(question_type=QuestionType.MCQ),
            actor=super_admin, session=db_session,
        )


async def test_update_dataset_question_unknown_id_404s(db_session):
    super_admin = await _seed_super_admin(db_session)
    dataset = await _seed_dataset(db_session)
    with pytest.raises(NotFoundError):
        await admin_catalog.update_dataset_question(
            str(dataset.id), str(uuid.uuid4()), UpdateDatasetQuestionIn(text="x"),
            actor=super_admin, session=db_session,
        )


async def test_update_dataset_question_wrong_dataset_404s(db_session):
    """A question_id that's real but belongs to a *different* dataset must
    404, not silently update - the route filters by both ids together."""
    super_admin = await _seed_super_admin(db_session)
    dataset_a = await _seed_dataset(db_session)
    dataset_b = await _seed_dataset(db_session)
    created = await admin_catalog.create_dataset_question(
        str(dataset_a.id),
        CreateDatasetQuestionIn(
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER,
            text="text", answer="answer",
        ),
        actor=super_admin, session=db_session,
    )
    with pytest.raises(NotFoundError):
        await admin_catalog.update_dataset_question(
            str(dataset_b.id), created.id, UpdateDatasetQuestionIn(text="hijacked"),
            actor=super_admin, session=db_session,
        )


async def test_delete_dataset_question_removes_it_and_is_idempotent(db_session):
    super_admin = await _seed_super_admin(db_session)
    dataset = await _seed_dataset(db_session)
    created = await admin_catalog.create_dataset_question(
        str(dataset.id),
        CreateDatasetQuestionIn(
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER,
            text="text", answer="answer",
        ),
        actor=super_admin, session=db_session,
    )

    result = await admin_catalog.delete_dataset_question(
        str(dataset.id), created.id, actor=super_admin, session=db_session,
    )
    assert result == {"deleted": True}

    remaining = await db_session.execute(select(DatasetQuestion).where(DatasetQuestion.id == created.id))
    assert remaining.scalar_one_or_none() is None

    # Idempotent: deleting again is still a clean 'deleted': True.
    result2 = await admin_catalog.delete_dataset_question(
        str(dataset.id), created.id, actor=super_admin, session=db_session,
    )
    assert result2 == {"deleted": True}


async def test_delete_dataset_question_unknown_id_is_idempotent(db_session):
    super_admin = await _seed_super_admin(db_session)
    dataset = await _seed_dataset(db_session)
    result = await admin_catalog.delete_dataset_question(
        str(dataset.id), str(uuid.uuid4()), actor=super_admin, session=db_session,
    )
    assert result == {"deleted": True}


async def test_list_dataset_questions_unknown_dataset_404s(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(NotFoundError):
        await admin_catalog.list_dataset_questions(str(uuid.uuid4()), _=super_admin, session=db_session)


async def test_dataset_questions_scoped_to_own_dataset(db_session):
    super_admin = await _seed_super_admin(db_session)
    dataset_a = await _seed_dataset(db_session)
    dataset_b = await _seed_dataset(db_session)
    await admin_catalog.create_dataset_question(
        str(dataset_a.id),
        CreateDatasetQuestionIn(
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER,
            text="only in A", answer="a",
        ),
        actor=super_admin, session=db_session,
    )

    listed_b = await admin_catalog.list_dataset_questions(str(dataset_b.id), _=super_admin, session=db_session)
    assert listed_b.total == 0
