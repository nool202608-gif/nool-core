"""Neo4j driver lifecycle (mirrors services/core/src/repositories/database.py's
init_engine/get_engine/check_connection/dispose_engine shape) plus the read
queries this service needs. Cypher shapes are ported from
nool-data-ingestion/ingestion/retrieve.py, which the KG-building pipeline
already validated against the real graph - not imported directly, since
nool-data-ingestion is a separate, sibling repo/project.
"""

from __future__ import annotations

from neo4j import AsyncDriver, AsyncGraphDatabase

_driver: AsyncDriver | None = None


def init_driver(uri: str, user: str, password: str) -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    return _driver


def get_driver() -> AsyncDriver:
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialized. Call init_driver() first.")
    return _driver


async def check_connection() -> bool:
    """Used by /ready. Never raises - a failed check just means "not ready"."""
    try:
        driver = get_driver()
        async with driver.session() as session:
            result = await session.run("RETURN 1")
            await result.consume()
        return True
    except Exception:
        return False


async def dispose_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
    _driver = None


async def get_curriculum_tree(*, board: str = "CBSE", grade: int = 10, subject: str = "Science") -> dict | None:
    query = """
    MATCH (cur:Curriculum {board: $board, grade: $grade, subject: $subject})-[:HAS_SUBJECT]->(sub:Subject)
    MATCH (sub)-[:HAS_CHAPTER]->(ch:Chapter)
    OPTIONAL MATCH (ch)-[:HAS_SECTION]->(sec:Section)
    WITH sub, ch, sec ORDER BY ch.number, sec.number
    WITH sub, ch, collect(DISTINCT {ref: sec.id, number: sec.number, name: sec.title}) AS topics
    ORDER BY ch.number
    RETURN sub.name AS subject,
           collect({ref: ch.id, number: ch.number, name: ch.title, topics: topics}) AS chapters
    """
    driver = get_driver()
    async with driver.session() as session:
        record = await (await session.run(query, board=board, grade=grade, subject=subject)).single()
        if record is None:
            return None
        return {"board": board, "grade": grade, "subject": record["subject"], "chapters": record["chapters"]}


async def get_concept_context_for_scope(
    *, chapter_numbers: list[int], topic_names: list[str] | None = None, subject: str = "Science"
) -> list[dict]:
    """Concept-level grounding context (definitions/formulas/examples/
    figures) for the requested chapters, optionally narrowed to specific
    topics (Section titles) within them - the input the question generator
    retrieves against before writing anything.
    """
    query = """
    MATCH (sub:Subject {name: $subject})-[:HAS_CHAPTER]->(ch:Chapter)
    WHERE ch.number IN $chapter_numbers
    MATCH (ch)-[:HAS_SECTION]->(sec:Section)-[:HAS_CONCEPT]->(c:Concept)
    WHERE $topic_names IS NULL OR size($topic_names) = 0 OR sec.title IN $topic_names
    OPTIONAL MATCH (c)-[:DEFINED_BY]->(d:Definition)
    OPTIONAL MATCH (c)-[:HAS_FORMULA]->(f:Formula)
    OPTIONAL MATCH (c)-[:ILLUSTRATED_BY]->(ex:Example)
    OPTIONAL MATCH (c)-[:HAS_FIGURE]->(fig:Figure)
    RETURN ch.number AS chapter_number, ch.title AS chapter_title,
           sec.title AS topic, c.id AS concept_id, c.name AS concept_name,
           c.summary AS summary, c.bloom_levels AS bloom_levels,
           collect(DISTINCT d.text) AS definitions,
           collect(DISTINCT f.expression) AS formulas,
           collect(DISTINCT ex.text) AS examples,
           collect(DISTINCT fig.description) AS figure_descriptions
    ORDER BY chapter_number, topic
    """
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            query, subject=subject, chapter_numbers=chapter_numbers, topic_names=topic_names
        )
        return [record.data() async for record in result]
