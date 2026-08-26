"""Pluggable content generation - mirrors shared/auth's IdentityProvider
seam (see shared/auth/provider.py). Homework/Question Paper question
generation and the AI Assessor's scripted conversation depend only on the
ContentGenerator Protocol below, never on a concrete implementation.

DeterministicContentGenerator is the only implementation today: there is
no real LLM/STT/TTS vendor integrated anywhere in this repo (see
CLAUDE.md's "Current Goal") - it produces plausible-shaped placeholder
content, same spirit as nool-apps' mocks/services/homework and
mocks/services/voice. A real vendor integration later is a second
implementation of this Protocol plus one call-site swap, nothing else.
"""

from dataclasses import dataclass, field
from typing import Protocol

from src.domain.models import BloomLevel


@dataclass
class GeneratedQuestion:
    bloom_level: BloomLevel
    text: str
    answer: str = ""


@dataclass
class GeneratedAssessorQuestion:
    bloom_level: BloomLevel
    headline: str
    prompt: str


class ContentGenerator(Protocol):
    def generate_questions(
        self, *, topic: str, bloom_levels: list[BloomLevel], count: int
    ) -> list[GeneratedQuestion]: ...

    def generate_replacement_candidates(
        self, *, topic: str, bloom_level: BloomLevel, exclude_text: str, count: int
    ) -> list[str]: ...

    def build_assessor_script(
        self, *, context_label: str, bloom_levels: list[BloomLevel], count: int
    ) -> list[GeneratedAssessorQuestion]: ...


@dataclass
class DeterministicContentGenerator:
    """Cycles bloom levels and produces templated, clearly-placeholder
    text - deterministic so tests and demos are reproducible, honest about
    not being AI-generated content.
    """

    _PROMPT_TEMPLATES: dict[BloomLevel, str] = field(
        default_factory=lambda: {
            BloomLevel.REMEMBER: "State the key fact about {topic}.",
            BloomLevel.UNDERSTAND: "Explain {topic} in your own words.",
            BloomLevel.APPLY: "Apply {topic} to a new example.",
            BloomLevel.ANALYZE: "Break {topic} down into its component parts.",
            BloomLevel.EVALUATE: "Judge the strengths and weaknesses of {topic}.",
            BloomLevel.CREATE: "Design something new using {topic}.",
        }
    )

    def _prompt(self, bloom_level: BloomLevel, topic: str) -> str:
        return self._PROMPT_TEMPLATES[bloom_level].format(topic=topic)

    def generate_questions(
        self, *, topic: str, bloom_levels: list[BloomLevel], count: int
    ) -> list[GeneratedQuestion]:
        levels = bloom_levels or [BloomLevel.UNDERSTAND]
        return [
            GeneratedQuestion(
                bloom_level=levels[i % len(levels)],
                text=self._prompt(levels[i % len(levels)], topic),
                answer=f"Reference answer for: {topic}",
            )
            for i in range(count)
        ]

    def generate_replacement_candidates(
        self, *, topic: str, bloom_level: BloomLevel, exclude_text: str, count: int
    ) -> list[str]:
        base = self._prompt(bloom_level, topic)
        candidates = [f"{base} (alternative phrasing {i + 1})" for i in range(count + 1)]
        return [c for c in candidates if c != exclude_text][:count]

    def build_assessor_script(
        self, *, context_label: str, bloom_levels: list[BloomLevel], count: int
    ) -> list[GeneratedAssessorQuestion]:
        levels = bloom_levels or [BloomLevel.UNDERSTAND]
        return [
            GeneratedAssessorQuestion(
                bloom_level=levels[i % len(levels)],
                headline=f"Question {i + 1}",
                prompt=self._prompt(levels[i % len(levels)], context_label),
            )
            for i in range(count)
        ]


_generator: ContentGenerator = DeterministicContentGenerator()


def get_content_generator() -> ContentGenerator:
    return _generator
