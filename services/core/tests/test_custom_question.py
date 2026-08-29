"""Custom questions (requirements.md's custom-question entry) - School
Admin-authored content following the full curriculum hierarchy (Subject
-> Chapter -> Topic, plus Class). Real rows against the dev Postgres via
db_session, same pattern as test_school_oversight.py.
"""

import io
import uuid

import pytest
from openpyxl import Workbook

from shared.errors import NotFoundError

from src.api.routes import custom_question, school_oversight
from src.api.schemas.custom_question import CreateCustomQuestionIn, UpdateCustomQuestionIn
from src.domain.models import BloomLevel, Chapter, QuestionType, Role, School, SchoolClass, Subject, Topic, User, UserStatus


class _FakeUploadFile:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


async def _seed_school(db_session) -> School:
    school = School(name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()
    return school


async def _seed_admin(db_session, school_id) -> User:
    admin = User(
        firebase_uid=f"admin-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Admin", role=Role.SCHOOL_ADMIN, school_id=school_id, status=UserStatus.ACTIVE,
    )
    db_session.add(admin)
    await db_session.flush()
    return admin


async def _seed_hierarchy(db_session, school_id) -> tuple[SchoolClass, Subject, Chapter, Topic]:
    school_class = SchoolClass(school_id=school_id, grade=8, section=str(uuid.uuid4())[:1].upper())
    subject = Subject(name=f"Subject-{uuid.uuid4()}")
    db_session.add_all([school_class, subject])
    await db_session.flush()
    chapter = Chapter(subject_id=subject.id, name="Chapter 1")
    db_session.add(chapter)
    await db_session.flush()
    topic = Topic(chapter_id=chapter.id, name="Topic 1")
    db_session.add(topic)
    await db_session.flush()
    return school_class, subject, chapter, topic


async def test_create_mcq_question_persists_and_audits(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, topic = await _seed_hierarchy(db_session, school.id)

    out = await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
            topic_id=str(topic.id), bloom_level=BloomLevel.UNDERSTAND, question_type=QuestionType.MCQ,
            text="What is the capital of France?", options=["Paris", "London", "Berlin"], answer="Paris",
        ),
        user=admin, session=db_session,
    )

    assert out.text == "What is the capital of France?"
    assert out.answer == "Paris"
    assert out.created_by == str(admin.id)
    assert out.collection_name is None


async def test_create_with_a_named_collection_persists_it(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    out = await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.LONG_ANSWER,
            text="Q", answer="A", collection_name="  Midterm practice  ",
        ),
        user=admin, session=db_session,
    )

    assert out.collection_name == "Midterm practice"


async def test_blank_collection_name_normalizes_to_the_general_bank(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    out = await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.LONG_ANSWER,
            text="Q", answer="A", collection_name="   ",
        ),
        user=admin, session=db_session,
    )

    assert out.collection_name is None


async def test_update_can_set_and_clear_the_collection_name(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    created = await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.LONG_ANSWER, text="Q", answer="A",
        ),
        user=admin, session=db_session,
    )

    named = await custom_question.update_custom_question(
        created.id, UpdateCustomQuestionIn(collection_name="Weak topics"), user=admin, session=db_session,
    )
    assert named.collection_name == "Weak topics"

    cleared = await custom_question.update_custom_question(
        created.id, UpdateCustomQuestionIn(collection_name=None), user=admin, session=db_session,
    )
    assert cleared.collection_name is None


async def test_list_filters_by_collection_name(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.LONG_ANSWER,
            text="In set", answer="A", collection_name="Set A",
        ),
        user=admin, session=db_session,
    )
    await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.LONG_ANSWER,
            text="General", answer="A",
        ),
        user=admin, session=db_session,
    )

    named_only = await custom_question.list_custom_questions(
        class_id=None, grade=None, subject_id=None, chapter_id=None, topic_id=None, bloom_level=None, question_type=None,
        collection_name="Set A", general_bank_only=False, limit=50, offset=0, user=admin, session=db_session,
    )
    assert [q.text for q in named_only.items] == ["In set"]

    general_only = await custom_question.list_custom_questions(
        class_id=None, grade=None, subject_id=None, chapter_id=None, topic_id=None, bloom_level=None, question_type=None,
        collection_name=None, general_bank_only=True, limit=50, offset=0, user=admin, session=db_session,
    )
    assert [q.text for q in general_only.items] == ["General"]


async def test_list_collections_returns_distinct_sorted_names(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    for name in ["Zeta set", "Alpha set", "Alpha set"]:
        await custom_question.create_custom_question(
            CreateCustomQuestionIn(
                class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
                bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.LONG_ANSWER,
                text="Q", answer="A", collection_name=name,
            ),
            user=admin, session=db_session,
        )

    collections = await custom_question.list_custom_question_collections(user=admin, session=db_session)
    assert collections == ["Alpha set", "Zeta set"]


async def test_collections_summary_counts_general_bank_and_named_sets(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    for name in [None, None, "Alpha set", "Zeta set", "Zeta set"]:
        await custom_question.create_custom_question(
            CreateCustomQuestionIn(
                class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
                bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.LONG_ANSWER,
                text="Q", answer="A", collection_name=name,
            ),
            user=admin, session=db_session,
        )

    summary = await custom_question.summarize_custom_question_collections(user=admin, session=db_session)
    by_name = {s.collection_name: s.question_count for s in summary}
    assert by_name == {None: 2, "Alpha set": 1, "Zeta set": 2}
    # General bank (None) sorts first.
    assert summary[0].collection_name is None


async def test_question_bank_filters_custom_rows_by_collection_name(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.LONG_ANSWER,
            text="In set", answer="A", collection_name="Midterm practice",
        ),
        user=admin, session=db_session,
    )
    await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.LONG_ANSWER,
            text="General", answer="A",
        ),
        user=admin, session=db_session,
    )

    general_only = await school_oversight.list_school_question_bank(
        source=None, topic=None, collection_name=None, general_bank_only=True, limit=50, offset=0,
        user=admin, session=db_session,
    )
    assert [e.text for e in general_only.items] == ["General"]

    named_only = await school_oversight.list_school_question_bank(
        source=None, topic=None, collection_name="Midterm practice", general_bank_only=False, limit=50, offset=0,
        user=admin, session=db_session,
    )
    assert [e.text for e in named_only.items] == ["In set"]


async def test_create_mcq_rejects_answer_not_in_options():
    with pytest.raises(Exception):  # pydantic ValidationError
        CreateCustomQuestionIn(
            class_id="x", subject_id="x", chapter_id="x", bloom_level=BloomLevel.REMEMBER,
            question_type=QuestionType.MCQ, text="Q", options=["A", "B"], answer="C",
        )


async def test_create_short_answer_rejects_options():
    with pytest.raises(Exception):  # pydantic ValidationError
        CreateCustomQuestionIn(
            class_id="x", subject_id="x", chapter_id="x", bloom_level=BloomLevel.REMEMBER,
            question_type=QuestionType.SHORT_ANSWER, text="Q", options=["A", "B"], answer="A",
        )


async def test_create_rejects_setting_both_class_id_and_grade():
    with pytest.raises(Exception):  # pydantic ValidationError
        CreateCustomQuestionIn(
            class_id="x", grade=8, subject_id="x", chapter_id="x", bloom_level=BloomLevel.REMEMBER,
            question_type=QuestionType.SHORT_ANSWER, text="Q", answer="A",
        )


async def test_create_rejects_setting_neither_class_id_nor_grade():
    with pytest.raises(Exception):  # pydantic ValidationError
        CreateCustomQuestionIn(
            subject_id="x", chapter_id="x", bloom_level=BloomLevel.REMEMBER,
            question_type=QuestionType.SHORT_ANSWER, text="Q", answer="A",
        )


async def test_create_at_grade_level_applies_to_the_whole_grade(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    out = await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            grade=school_class.grade, subject_id=str(subject.id), chapter_id=str(chapter.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER,
            text="Q", answer="A",
        ),
        user=admin, session=db_session,
    )

    assert out.class_id is None
    assert out.grade == school_class.grade


async def test_create_at_grade_level_rejects_a_grade_with_no_class_in_the_school(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    _, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    with pytest.raises(NotFoundError):
        await custom_question.create_custom_question(
            CreateCustomQuestionIn(
                grade=99, subject_id=str(subject.id), chapter_id=str(chapter.id),
                bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER,
                text="Q", answer="A",
            ),
            user=admin, session=db_session,
        )


async def test_update_can_switch_between_class_and_grade(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    created = await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER, text="Q", answer="A",
        ),
        user=admin, session=db_session,
    )
    assert created.class_id == str(school_class.id)
    assert created.grade is None

    switched = await custom_question.update_custom_question(
        created.id, UpdateCustomQuestionIn(grade=school_class.grade), user=admin, session=db_session,
    )
    assert switched.class_id is None
    assert switched.grade == school_class.grade

    back = await custom_question.update_custom_question(
        created.id, UpdateCustomQuestionIn(class_id=str(school_class.id)), user=admin, session=db_session,
    )
    assert back.class_id == str(school_class.id)
    assert back.grade is None


async def test_update_rejects_setting_both_class_id_and_grade(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    created = await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER, text="Q", answer="A",
        ),
        user=admin, session=db_session,
    )

    with pytest.raises(Exception):  # pydantic ValidationError
        UpdateCustomQuestionIn(class_id=str(school_class.id), grade=school_class.grade)


async def test_question_bank_labels_a_grade_level_question_as_all_sections(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            grade=school_class.grade, subject_id=str(subject.id), chapter_id=str(chapter.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER,
            text="Whole grade Q", answer="A",
        ),
        user=admin, session=db_session,
    )

    bank = await school_oversight.list_school_question_bank(
        source="CUSTOM", topic=None, collection_name=None, general_bank_only=False, limit=50, offset=0,
        user=admin, session=db_session,
    )
    assert bank.total == 1
    assert bank.items[0].source_name == f"Class {school_class.grade} (all sections)"


async def test_bulk_import_blank_section_creates_a_grade_level_question(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        ["grade", "section", "subject", "chapter", "topic", "bloomLevel", "questionType", "text", "options", "answer", "collection"]
    )
    sheet.append([school_class.grade, "", subject.name, chapter.name, "", "REMEMBER", "SHORT_ANSWER", "Q", "", "A", ""])
    buffer = io.BytesIO()
    workbook.save(buffer)

    result = await custom_question.bulk_import_custom_questions(
        file=_FakeUploadFile("import.xlsx", buffer.getvalue()), user=admin, session=db_session,
    )

    assert result.created_count == 1
    assert result.error_count == 0

    listed = await custom_question.list_custom_questions(
        class_id=None, grade=None, subject_id=None, chapter_id=None, topic_id=None, bloom_level=None,
        question_type=None, collection_name=None, general_bank_only=False, limit=50, offset=0,
        user=admin, session=db_session,
    )
    assert listed.items[0].class_id is None
    assert listed.items[0].grade == school_class.grade


async def test_create_rejects_a_class_from_another_school(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_admin(db_session, school_a.id)
    class_b, subject, chapter, _ = await _seed_hierarchy(db_session, school_b.id)

    with pytest.raises(NotFoundError):
        await custom_question.create_custom_question(
            CreateCustomQuestionIn(
                class_id=str(class_b.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
                bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.LONG_ANSWER,
                text="Explain photosynthesis.", answer="...",
            ),
            user=admin_a, session=db_session,
        )


async def test_create_rejects_a_chapter_under_the_wrong_subject(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)
    other_subject = Subject(name=f"Subject-{uuid.uuid4()}")
    db_session.add(other_subject)
    await db_session.flush()

    with pytest.raises(NotFoundError):
        await custom_question.create_custom_question(
            CreateCustomQuestionIn(
                class_id=str(school_class.id), subject_id=str(other_subject.id), chapter_id=str(chapter.id),
                bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.LONG_ANSWER,
                text="Q", answer="A",
            ),
            user=admin, session=db_session,
        )


async def test_get_by_id_scopes_to_the_callers_school(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_admin(db_session, school_a.id)
    admin_b = await _seed_admin(db_session, school_b.id)
    class_a, subject_a, chapter_a, _ = await _seed_hierarchy(db_session, school_a.id)

    created = await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(class_a.id), subject_id=str(subject_a.id), chapter_id=str(chapter_a.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.LONG_ANSWER, text="Q", answer="A",
        ),
        user=admin_a, session=db_session,
    )

    fetched = await custom_question.get_custom_question(created.id, user=admin_a, session=db_session)
    assert fetched.id == created.id

    with pytest.raises(NotFoundError):
        await custom_question.get_custom_question(created.id, user=admin_b, session=db_session)


async def test_update_and_delete_round_trip(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, _ = await _seed_hierarchy(db_session, school.id)

    created = await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER,
            text="Original text", answer="Original answer",
        ),
        user=admin, session=db_session,
    )

    updated = await custom_question.update_custom_question(
        created.id, UpdateCustomQuestionIn(text="Updated text"), user=admin, session=db_session,
    )
    assert updated.text == "Updated text"
    assert updated.answer == "Original answer"

    result = await custom_question.delete_custom_question(created.id, user=admin, session=db_session)
    assert result == {"deleted": True}

    with pytest.raises(NotFoundError):
        await custom_question._get_own_question(db_session, created.id, school.id)


async def test_list_filters_by_school_and_bloom_level(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_admin(db_session, school_a.id)
    class_a, subject_a, chapter_a, _ = await _seed_hierarchy(db_session, school_a.id)
    class_b, subject_b, chapter_b, _ = await _seed_hierarchy(db_session, school_b.id)
    admin_b = await _seed_admin(db_session, school_b.id)

    await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(class_a.id), subject_id=str(subject_a.id), chapter_id=str(chapter_a.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER, text="Q1", answer="A1",
        ),
        user=admin_a, session=db_session,
    )
    await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(class_a.id), subject_id=str(subject_a.id), chapter_id=str(chapter_a.id),
            bloom_level=BloomLevel.ANALYZE, question_type=QuestionType.SHORT_ANSWER, text="Q2", answer="A2",
        ),
        user=admin_a, session=db_session,
    )
    await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(class_b.id), subject_id=str(subject_b.id), chapter_id=str(chapter_b.id),
            bloom_level=BloomLevel.REMEMBER, question_type=QuestionType.SHORT_ANSWER, text="Other school", answer="A",
        ),
        user=admin_b, session=db_session,
    )

    all_for_a = await custom_question.list_custom_questions(
        class_id=None, grade=None, subject_id=None, chapter_id=None, topic_id=None, bloom_level=None, question_type=None,
        collection_name=None, general_bank_only=False, limit=50, offset=0, user=admin_a, session=db_session,
    )
    assert all_for_a.total == 2
    assert all(e.text != "Other school" for e in all_for_a.items)

    filtered = await custom_question.list_custom_questions(
        class_id=None, grade=None, subject_id=None, chapter_id=None, topic_id=None, bloom_level=BloomLevel.REMEMBER,
        question_type=None, collection_name=None, general_bank_only=False, limit=50, offset=0,
        user=admin_a, session=db_session,
    )
    assert filtered.total == 1
    assert filtered.items[0].text == "Q1"


async def test_question_bank_includes_custom_source(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, topic = await _seed_hierarchy(db_session, school.id)

    await custom_question.create_custom_question(
        CreateCustomQuestionIn(
            class_id=str(school_class.id), subject_id=str(subject.id), chapter_id=str(chapter.id),
            topic_id=str(topic.id), bloom_level=BloomLevel.EVALUATE, question_type=QuestionType.TRUE_FALSE,
            text="The sky is blue.", options=["True", "False"], answer="True",
        ),
        user=admin, session=db_session,
    )

    bank = await school_oversight.list_school_question_bank(
        source="CUSTOM", topic=None, collection_name=None, general_bank_only=False, limit=50, offset=0,
        user=admin, session=db_session,
    )

    assert bank.total == 1
    assert bank.items[0].text == "The sky is blue."
    assert bank.items[0].topic_label == "Topic 1"
    assert bank.items[0].source == "CUSTOM"


async def test_bulk_import_creates_valid_rows_and_reports_errors(db_session):
    school = await _seed_school(db_session)
    admin = await _seed_admin(db_session, school.id)
    school_class, subject, chapter, topic = await _seed_hierarchy(db_session, school.id)

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["grade", "section", "subject", "chapter", "topic", "bloomLevel", "questionType", "text", "options", "answer"])
    sheet.append([
        school_class.grade, school_class.section, subject.name, chapter.name, topic.name,
        "REMEMBER", "MCQ", "2+2=?", "3|4|5", "4",
    ])
    sheet.append([
        school_class.grade, school_class.section, subject.name, chapter.name, "", "APPLY", "SHORT_ANSWER",
        "Explain X.", "", "Because Y.",
    ])
    sheet.append([999, "Z", subject.name, chapter.name, "", "REMEMBER", "SHORT_ANSWER", "Bad class row", "", "A"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    upload = _FakeUploadFile("questions.xlsx", buffer.getvalue())
    result = await custom_question.bulk_import_custom_questions(file=upload, user=admin, session=db_session)

    assert result.created_count == 2
    assert result.error_count == 1
    assert "No class" in result.results[2].error
