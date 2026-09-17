"""HTTP client for the kg service (services/kg) - the only thing in Core
that talks to the knowledge graph, and only ever through this module.
Mirrors shared/auth/providers/firebase.py's use of httpx for an external
call (the one existing precedent in this repo), but async - Core's route
handlers are all async, unlike Auth's sync token-verification path.
"""

from __future__ import annotations

import logging

import httpx

from shared.errors import AppError

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class KgServiceUnavailableError(AppError):
    code = "KG_SERVICE_UNAVAILABLE"
    status_code = 503


def _base_url() -> str:
    settings = get_settings()
    if not settings.kg_service_url:
        raise KgServiceUnavailableError("KG_SERVICE_URL is not configured.")
    return settings.kg_service_url.rstrip("/")


async def _post(path: str, json: dict, *, timeout: float) -> dict:
    try:
        async with httpx.AsyncClient(base_url=_base_url(), timeout=timeout) as client:
            response = await client.post(path, json=json)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        logger.warning("kg_service_upstream_error", extra={"path": path, "reason": str(exc)})
        raise KgServiceUnavailableError("Could not reach the knowledge-graph service. Try again.") from exc


async def _get(path: str, params: dict) -> dict:
    try:
        async with httpx.AsyncClient(base_url=_base_url(), timeout=30.0) as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        logger.warning("kg_service_upstream_error", extra={"path": path, "reason": str(exc)})
        raise KgServiceUnavailableError("Could not reach the knowledge-graph service. Try again.") from exc


async def get_curriculum_tree(*, board: str = "CBSE", grade: int = 10, subject: str = "Science") -> dict:
    """Used by POST /admin/curriculum/sync-from-kg (admin_catalog.py)."""
    return await _get("/curriculum/tree", params={"board": board, "grade": grade, "subject": subject})


async def generate_paper_questions(
    *,
    subject: str,
    board: str,
    grade: int,
    chapters: list[dict],
    topic_names: list[str],
    bloom_distribution: dict[str, int],
    difficulty_distribution: dict[str, int],
    question_types: list[str],
    total_questions: int,
) -> list[dict]:
    """Used by POST /question-papers/{id}/generate (question_paper.py).
    Grounded-question generation is not fast (one LLM call per figure-heavy
    chapter set) - a longer timeout than the other calls here.

    `subject`/`board`/`grade` scope which Curriculum root in the kg
    service's Neo4j graph to query - the kg service defaults these to
    CBSE/Grade 10/Science when omitted, so a paper for any other subject
    would otherwise silently generate against the wrong (or a
    coincidentally-named) Curriculum tree with no visible error.
    """
    body = await _post(
        "/question-papers/generate",
        {
            "subject": subject,
            "board": board,
            "grade": grade,
            "chapters": chapters,
            "topic_names": topic_names,
            "bloom_distribution": bloom_distribution,
            "difficulty_distribution": difficulty_distribution,
            "question_types": question_types,
            "total_questions": total_questions,
        },
        timeout=120.0,
    )
    return body["questions"]


async def generate_assessor_content(
    *,
    subject: str,
    board: str,
    grade: int,
    chapters: list[dict],
    topic_names: list[str],
    bloom_levels: list[str],
    num_questions: int,
) -> dict:
    """Used by POST /tests (voice_test.py's create_test) - grounded
    reference questions + a spoken-friendly context summary for the
    colearner pipeline's SessionConfig. See generate_paper_questions'
    docstring for why subject/board/grade must be passed explicitly; same
    reasoning applies here.
    """
    return await _post(
        "/voice-tests/generate",
        {
            "subject": subject,
            "board": board,
            "grade": grade,
            "chapters": chapters,
            "topic_names": topic_names,
            "bloom_levels": bloom_levels,
            "num_questions": num_questions,
        },
        timeout=120.0,
    )


async def generate_replacement_candidates(
    *,
    subject: str,
    board: str,
    grade: int,
    chapters: list[dict],
    topic_names: list[str],
    bloom_level: str,
    exclude_text: str,
    count: int,
) -> list[dict]:
    """Used by GET /question-papers/{id}/questions/{qid}/candidates (the
    Review screen's "Shuffle" picker). See generate_paper_questions'
    docstring for why subject/board/grade must be passed explicitly."""
    body = await _post(
        "/question-papers/replacement-candidates",
        {
            "subject": subject,
            "board": board,
            "grade": grade,
            "chapters": chapters,
            "topic_names": topic_names,
            "bloom_level": bloom_level,
            "exclude_text": exclude_text,
            "count": count,
        },
        timeout=60.0,
    )
    return body["questions"]
