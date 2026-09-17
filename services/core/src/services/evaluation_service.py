"""Turns colearner's per-session Bloom's report into a real per-level score
- the replacement for test_completion.py's honest-but-placeholder
completion-rate math (mastery_percent = 100*answered/total), now that a
real grading LLM call exists (see services/colearner/src/services/
chained_service.py's generate_bloom_report / multimodal_service.py's
generate_multimodal_bloom_report - each qa_transcripts entry now carries a
score_percent, added alongside this module).

Deliberately tolerant of a missing/malformed report (an older cached
report shape, a report-generation failure that fell back to colearner's
own empty-qa_transcripts placeholder) - evaluate_colearner_session returns
None in that case, and the caller (ai_assessor.py's stream_session) falls
back to record_test_completion's original completion-rate math, exactly as
it did before this module existed.
"""

from __future__ import annotations

from src.domain.models import BloomLevel

# colearner's report writes Bloom levels as the same gerund words its own
# prompt enumerates ("Understanding", "Applying", "Analyzing",
# "Remembering", "Evaluating", "Creating" - see chained_service.py's
# generate_bloom_report), not Core's BloomLevel enum values. Maps both
# forms (case-insensitively) so either a gerund or a bare enum value
# ("UNDERSTAND") normalizes correctly.
_BLOOM_LABEL_TO_LEVEL: dict[str, BloomLevel] = {
    "remembering": BloomLevel.REMEMBER,
    "remember": BloomLevel.REMEMBER,
    "understanding": BloomLevel.UNDERSTAND,
    "understand": BloomLevel.UNDERSTAND,
    "applying": BloomLevel.APPLY,
    "apply": BloomLevel.APPLY,
    "analyzing": BloomLevel.ANALYZE,
    "analysing": BloomLevel.ANALYZE,
    "analyze": BloomLevel.ANALYZE,
    "analyse": BloomLevel.ANALYZE,
    "evaluating": BloomLevel.EVALUATE,
    "evaluate": BloomLevel.EVALUATE,
    "creating": BloomLevel.CREATE,
    "create": BloomLevel.CREATE,
}


def _normalize_bloom_label(label: object) -> BloomLevel | None:
    if not isinstance(label, str) or not label:
        return None
    return _BLOOM_LABEL_TO_LEVEL.get(label.strip().lower())


def evaluate_colearner_session(
    report: dict | None, bloom_levels: list[BloomLevel]
) -> tuple[int, dict[BloomLevel, int]] | None:
    """Returns (mastery_percent, {bloom_level: percent}) from a colearner
    session's `report` (the value of the WS `session_completed` frame's
    `report` field), or None if the report doesn't carry real scores to
    evaluate from.
    """
    if not report:
        return None
    qa_transcripts = report.get("qa_transcripts")
    if not isinstance(qa_transcripts, list) or not qa_transcripts:
        return None

    scores_by_level: dict[BloomLevel, list[int]] = {}
    all_scores: list[int] = []
    for entry in qa_transcripts:
        if not isinstance(entry, dict):
            continue
        score = entry.get("score_percent")
        if not isinstance(score, (int, float)):
            continue
        score = max(0, min(100, round(score)))
        all_scores.append(score)
        level = _normalize_bloom_label(entry.get("blooms_attribute"))
        if level is not None:
            scores_by_level.setdefault(level, []).append(score)

    if not all_scores:
        return None

    mastery_percent = round(sum(all_scores) / len(all_scores))
    bloom_scores: dict[BloomLevel, int] = {}
    for level in bloom_levels or list(scores_by_level.keys()):
        levels_scores = scores_by_level.get(level)
        bloom_scores[level] = round(sum(levels_scores) / len(levels_scores)) if levels_scores else mastery_percent

    return mastery_percent, bloom_scores
