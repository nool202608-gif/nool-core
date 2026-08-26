from typing import Literal

from src.domain.models import BloomLevel

from .common import CamelModel


class OpenSessionIn(CamelModel):
    test_id: str  # or "retest-{homeworkId}" for a Retest - a fresh script either way
    context_label: str
    bloom_levels: list[BloomLevel]
    duration_seconds: int


class OpenSessionOut(CamelModel):
    session_id: str
    ws_url: str


# ---- WS event payloads - one JSON frame per message, matching
# services/voice/AiAssessorSession.ts's AiAssessorEvent discriminated
# union exactly. Server -> client only; client -> server frames
# (sendMessage/sendAudio/pause/resume/stop) are read as plain dicts in
# the WS route handler, not modeled here, since the handler only branches
# on `type` and never needs to validate/echo them back.


class SessionSummary(CamelModel):
    questions_answered: int
    total_questions: int
    elapsed_seconds: int


class ConnectionEvent(CamelModel):
    type: Literal["connection"] = "connection"
    state: Literal["connecting", "connected", "reconnecting", "disconnected"]


class TurnEvent(CamelModel):
    type: Literal["turn"] = "turn"
    state: Literal["speaking", "listening", "thinking", "paused"]


class QuestionEvent(CamelModel):
    type: Literal["question"] = "question"
    id: str
    index: int
    total: int
    bloom_level: BloomLevel
    headline: str
    prompt: str


class TranscriptEvent(CamelModel):
    type: Literal["transcript"] = "transcript"
    speaker: Literal["assessor", "student"]
    text: str


class ProgressEvent(CamelModel):
    type: Literal["progress"] = "progress"
    answered: int
    total: int


class TimerEvent(CamelModel):
    type: Literal["timer"] = "timer"
    remaining_seconds: int
    total_seconds: int


class CompletedEvent(CamelModel):
    type: Literal["completed"] = "completed"
    summary: SessionSummary


class TimedOutEvent(CamelModel):
    type: Literal["timed_out"] = "timed_out"
    summary: SessionSummary


class ExitedEvent(CamelModel):
    type: Literal["exited"] = "exited"


class ErrorEvent(CamelModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    retryable: bool = False
