"""Tests the AI Assessor WS turn-taking fix directly against
stream_session as a plain coroutine - a fake WebSocket + monkeypatched
get_current_user/get_session sidesteps needing a real network socket or
real Postgres, while still exercising the exact control-flow bug that was
fixed: the handler used to free-run through every question with no wait
for a student reply.
"""

from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocketDisconnect

from shared.auth import AuthenticatedUser
from src.api.routes import ai_assessor
from src.domain.models import BloomLevel


class FakeWebSocket:
    def __init__(self, incoming: list[dict]):
        self.sent: list[dict] = []
        self._incoming = list(incoming)
        self.closed = False

    async def accept(self) -> None:
        pass

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)

    async def receive_json(self) -> dict:
        if not self._incoming:
            raise WebSocketDisconnect()
        return self._incoming.pop(0)

    async def close(self, code: int = 1000) -> None:
        self.closed = True


class FakeDbSession:
    def __init__(self, ai_session, bloom_levels):
        self._ai_session = ai_session
        self._bloom_levels = bloom_levels
        self.calls = 0

    async def execute(self, _query):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(scalar_one_or_none=lambda: self._ai_session)
        return SimpleNamespace(all=lambda: [(lvl,) for lvl in self._bloom_levels])


class FakeSessionContext:
    def __init__(self, session: FakeDbSession):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _wire(monkeypatch, ai_session, bloom_levels, duration_seconds: int = 60):
    monkeypatch.setattr(
        ai_assessor,
        "get_current_user",
        lambda authorization: AuthenticatedUser(uid="uid-1", email=None, claims={}),
    )
    fake_db = FakeDbSession(ai_session, bloom_levels)
    monkeypatch.setattr(ai_assessor, "get_session", lambda: FakeSessionContext(fake_db))


def _session(duration_seconds: int = 60):
    return SimpleNamespace(id="sess-1", context_label="Science", duration_seconds=duration_seconds)


def _event_types(sent: list[dict]) -> list[str]:
    return [frame["type"] for frame in sent]


async def test_advances_only_after_a_message_frame(monkeypatch):
    ai_session = _session()
    _wire(monkeypatch, ai_session, [BloomLevel.REMEMBER])

    ws = FakeWebSocket([{"type": "message", "text": "answer"} for _ in range(5)])
    await ai_assessor.stream_session(ws, "sess-1", token="good")

    questions = [f for f in ws.sent if f["type"] == "question"]
    assert len(questions) == 5
    assert _event_types(ws.sent)[-1] == "completed"
    assert ws.sent[-1]["summary"]["questionsAnswered"] == 5


async def test_ignores_non_message_frames_while_waiting(monkeypatch):
    ai_session = _session()
    _wire(monkeypatch, ai_session, [BloomLevel.REMEMBER])

    # audio/pause frames shouldn't count as an answer or advance the turn.
    ws = FakeWebSocket(
        [{"type": "audio"}, {"type": "pause"}, {"type": "message", "text": "answer"}]
        + [{"type": "message", "text": "answer"} for _ in range(4)]
    )
    await ai_assessor.stream_session(ws, "sess-1", token="good")

    assert len([f for f in ws.sent if f["type"] == "question"]) == 5
    assert ws.sent[-1]["type"] == "completed"


async def test_stop_frame_ends_the_session_early(monkeypatch):
    ai_session = _session()
    _wire(monkeypatch, ai_session, [BloomLevel.REMEMBER])

    ws = FakeWebSocket([{"type": "message", "text": "answer"}, {"type": "stop"}])
    await ai_assessor.stream_session(ws, "sess-1", token="good")

    assert len([f for f in ws.sent if f["type"] == "question"]) == 2
    assert ws.sent[-1]["type"] == "exited"


async def test_times_out_when_the_student_never_replies(monkeypatch):
    ai_session = _session(duration_seconds=0)
    _wire(monkeypatch, ai_session, [BloomLevel.REMEMBER])

    ws = FakeWebSocket([])  # no client frames at all
    await ai_assessor.stream_session(ws, "sess-1", token="good")

    assert len([f for f in ws.sent if f["type"] == "question"]) == 1
    assert ws.sent[-1]["type"] == "timed_out"
    assert ws.sent[-1]["summary"]["questionsAnswered"] == 0


async def test_unknown_session_id_closes_immediately(monkeypatch):
    _wire(monkeypatch, None, [])

    ws = FakeWebSocket([])
    await ai_assessor.stream_session(ws, "no-such-session", token="good")

    assert ws.closed
    assert ws.sent == []
