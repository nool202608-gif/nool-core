"""Real, KG-grounded question generation for Homework - the first real
source `content_generator.py`'s docstring anticipated ("a second
implementation of this Protocol plus one call-site swap").

It deliberately does NOT implement the `ContentGenerator` Protocol
directly: that Protocol is synchronous (written before any real vendor
existed), while grounding a question in real curriculum content means an
HTTP call to the `kg` service (see kg_client.py) - inherently async, like
every other FastAPI route/service in this repo. So this is instead a thin
async resolver each Homework call site asks first.

It falls back to `DeterministicContentGenerator` whenever there's nothing
real to ground against (the chapter was never synced from KG - see
`Chapter.order_index`'s docstring) or the KG service call itself fails,
mirroring `voice_test.py`'s `_generate_reference_content` exactly: same
`chapter.order_index is None` guard, same "log a warning and fall back,
never raise" failure handling. Homework generation must never hard-fail
because a grounding service hiccupped.
"""

import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import BloomLevel, Chapter, School, SchoolClass, Subject, Topic
from src.services import kg_client
from src.services.content_generator import GeneratedQuestion, get_content_generator

logger = logging.getLogger(__name__)


async def _kg_scope(
    session: AsyncSession,
    *,
    chapter_id: uuid.UUID,
    subject_id: uuid.UUID,
    class_id: uuid.UUID,
    topic_id: Optional[uuid.UUID],
):
    chapter = await session.get(Chapter, chapter_id)
    if chapter is None or chapter.order_index is None:
        return None  # Never synced from KG - nothing to ground against.

    subject = await session.get(Subject, subject_id)
    school_class = await session.get(SchoolClass, class_id)
    school = await session.get(School, school_class.school_id) if school_class else None
    topic = await session.get(Topic, topic_id) if topic_id else None
    if subject is None or school_class is None or school is None:
        return None
    return chapter, subject, school, school_class, topic


async def generate_questions(
    session: AsyncSession,
    *,
    chapter_id: uuid.UUID,
    subject_id: uuid.UUID,
    class_id: uuid.UUID,
    topic_id: Optional[uuid.UUID],
    topic: str,
    bloom_distribution: dict[BloomLevel, int],
    count: int,
) -> list[GeneratedQuestion]:
    """Real KG-grounded questions for a chapter that has real content,
    otherwise the deterministic placeholder generator - see module
    docstring for why this isn't just a second `ContentGenerator`.
    """
    bloom_levels = list(bloom_distribution.keys())
    scope = await _kg_scope(
        session, chapter_id=chapter_id, subject_id=subject_id, class_id=class_id, topic_id=topic_id
    )
    if scope is None:
        return get_content_generator().generate_questions(
            topic=topic, bloom_levels=bloom_levels, count=count
        )

    chapter, subject, school, school_class, topic_row = scope
    try:
        raw = await kg_client.generate_paper_questions(
            subject=subject.name,
            board=school.board,
            grade=school_class.grade,
            chapters=[{"number": chapter.order_index, "name": chapter.name}],
            topic_names=[topic_row.name] if topic_row else [],
            bloom_distribution={level.value: value for level, value in bloom_distribution.items()}
            or {BloomLevel.UNDERSTAND.value: count},
            difficulty_distribution={"MEDIUM": count},
            question_types=[],
            total_questions=count,
        )
    except Exception:
        logger.warning(
            "homework_kg_question_generation_failed",
            extra={"chapter_id": str(chapter_id)},
        )
        return get_content_generator().generate_questions(
            topic=topic, bloom_levels=bloom_levels, count=count
        )

    return [
        GeneratedQuestion(bloom_level=BloomLevel(q["bloom_level"]), text=q["text"], answer=q["answer"])
        for q in raw
    ]


async def generate_replacement_candidates(
    session: AsyncSession,
    *,
    chapter_id: uuid.UUID,
    subject_id: uuid.UUID,
    class_id: uuid.UUID,
    topic_id: Optional[uuid.UUID],
    topic: str,
    bloom_level: BloomLevel,
    exclude_text: str,
    count: int,
) -> list[str]:
    scope = await _kg_scope(
        session, chapter_id=chapter_id, subject_id=subject_id, class_id=class_id, topic_id=topic_id
    )
    if scope is None:
        return get_content_generator().generate_replacement_candidates(
            topic=topic, bloom_level=bloom_level, exclude_text=exclude_text, count=count
        )

    chapter, subject, school, school_class, topic_row = scope
    try:
        raw = await kg_client.generate_replacement_candidates(
            subject=subject.name,
            board=school.board,
            grade=school_class.grade,
            chapters=[{"number": chapter.order_index, "name": chapter.name}],
            topic_names=[topic_row.name] if topic_row else [],
            bloom_level=bloom_level.value,
            exclude_text=exclude_text,
            count=count,
        )
    except Exception:
        logger.warning(
            "homework_kg_replacement_generation_failed",
            extra={"chapter_id": str(chapter_id)},
        )
        return get_content_generator().generate_replacement_candidates(
            topic=topic, bloom_level=bloom_level, exclude_text=exclude_text, count=count
        )
    return [q["text"] for q in raw]
