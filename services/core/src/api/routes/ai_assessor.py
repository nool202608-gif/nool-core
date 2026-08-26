import asyncio

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import AuthenticatedUser
from shared.errors import UnauthorizedError

from src.api.deps import get_current_user, get_db_session
from src.api.schemas.ai_assessor import (
    CompletedEvent,
    ConnectionEvent,
    ExitedEvent,
    OpenSessionIn,
    OpenSessionOut,
    ProgressEvent,
    QuestionEvent,
    SessionSummary,
    TimedOutEvent,
    TimerEvent,
    TranscriptEvent,
    TurnEvent,
)
from src.domain.models import AiAssessorSession, AiAssessorSessionBloomLevel
from src.repositories import get_by_firebase_uid, get_session
from src.services.content_generator import get_content_generator

router = APIRouter(prefix="/api/v1", tags=["ai-assessor"])


@router.post("/ai-assessor/sessions", status_code=201, summary="Open a session")
async def open_session(
    body: OpenSessionIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> OpenSessionOut:
    app_user = await get_by_firebase_uid(db, user.uid)
    if app_user is None:
        raise UnauthorizedError("No application profile exists for this account yet.")

    ai_session = AiAssessorSession(
        student_id=app_user.id,
        test_id=body.test_id if not body.test_id.startswith("retest-") else None,
        context_label=body.context_label,
        duration_seconds=body.duration_seconds,
    )
    db.add(ai_session)
    await db.flush()
    for level in body.bloom_levels:
        db.add(AiAssessorSessionBloomLevel(session_id=ai_session.id, bloom_level=level))
    await db.commit()

    return OpenSessionOut(
        session_id=str(ai_session.id),
        ws_url=f"/api/v1/ai-assessor/sessions/{ai_session.id}/stream",
    )


@router.websocket("/ai-assessor/sessions/{session_id}/stream")
async def stream_session(websocket: WebSocket, session_id: str, token: str = Query(...)) -> None:
    """One JSON frame per message, both directions - see
    src/api/schemas/ai_assessor.py for the exact event shapes, matching
    services/voice/AiAssessorSession.ts's AiAssessorEvent. Driven by the
    deterministic ContentGenerator, not a real voice/LLM vendor - see
    CLAUDE.md's "Current Goal".
    """
    try:
        get_current_user(authorization=f"Bearer {token}")
    except UnauthorizedError:
        await websocket.close(code=4401)
        return

    async with get_session() as db:
        result = await db.execute(select(AiAssessorSession).where(AiAssessorSession.id == session_id))
        ai_session = result.scalar_one_or_none()
        if ai_session is None:
            await websocket.close(code=4404)
            return

        bloom_result = await db.execute(
            select(AiAssessorSessionBloomLevel.bloom_level).where(
                AiAssessorSessionBloomLevel.session_id == ai_session.id
            )
        )
        bloom_levels = [row[0] for row in bloom_result.all()]

    await websocket.accept()
    await websocket.send_json(ConnectionEvent(state="connecting").model_dump(by_alias=True))
    await websocket.send_json(ConnectionEvent(state="connected").model_dump(by_alias=True))

    generator = get_content_generator()
    questions = generator.build_assessor_script(
        context_label=ai_session.context_label, bloom_levels=bloom_levels, count=5
    )
    answered = 0
    start_time = asyncio.get_event_loop().time()

    def _elapsed() -> int:
        return int(asyncio.get_event_loop().time() - start_time)

    # Bridges the receive loop (below) and the main send loop, which needs
    # to *wait* for a real "message" frame - a student's answer - before
    # advancing to the next question, rather than free-running through the
    # whole script. audio/pause/resume frames are read and discarded (none
    # of those are implemented server-side yet - see CLAUDE.md's "Current
    # Goal") rather than silently counted as an answer.
    inbound: asyncio.Queue = asyncio.Queue()

    async def _receive_loop() -> None:
        try:
            while True:
                frame = await websocket.receive_json()
                await inbound.put(frame)
                if frame.get("type") == "stop":
                    return
        except WebSocketDisconnect:
            await inbound.put({"type": "stop"})

    receiver = asyncio.create_task(_receive_loop())

    async def _await_answer() -> dict | None:
        """Waits for a "message" or "stop" frame, ignoring anything else,
        bounded by the session's overall duration. None means the budget
        ran out before either arrived.
        """
        while True:
            remaining = max(ai_session.duration_seconds - _elapsed(), 0)
            if remaining <= 0:
                return None
            try:
                frame = await asyncio.wait_for(inbound.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return None
            if frame.get("type") in ("message", "stop"):
                return frame

    stopped = False
    timed_out = False
    try:
        for index, q in enumerate(questions):
            await websocket.send_json(TurnEvent(state="speaking").model_dump(by_alias=True))
            await websocket.send_json(
                QuestionEvent(
                    id=f"{session_id}-q{index + 1}",
                    index=index,
                    total=len(questions),
                    bloom_level=q.bloom_level,
                    headline=q.headline,
                    prompt=q.prompt,
                ).model_dump(by_alias=True)
            )
            await websocket.send_json(
                TranscriptEvent(speaker="assessor", text=q.prompt).model_dump(by_alias=True)
            )
            await websocket.send_json(TurnEvent(state="listening").model_dump(by_alias=True))

            frame = await _await_answer()
            if frame is None:
                timed_out = True
                break
            if frame.get("type") == "stop":
                stopped = True
                break

            await websocket.send_json(TurnEvent(state="thinking").model_dump(by_alias=True))
            await websocket.send_json(
                TranscriptEvent(speaker="student", text=frame.get("text", "")).model_dump(by_alias=True)
            )
            answered += 1
            await websocket.send_json(
                ProgressEvent(answered=answered, total=len(questions)).model_dump(by_alias=True)
            )
            await websocket.send_json(
                TimerEvent(
                    remaining_seconds=max(ai_session.duration_seconds - _elapsed(), 0),
                    total_seconds=ai_session.duration_seconds,
                ).model_dump(by_alias=True)
            )

        if stopped:
            await websocket.send_json(ExitedEvent().model_dump(by_alias=True))
        else:
            summary = SessionSummary(
                questions_answered=answered, total_questions=len(questions), elapsed_seconds=_elapsed()
            )
            event = TimedOutEvent(summary=summary) if timed_out else CompletedEvent(summary=summary)
            await websocket.send_json(event.model_dump(by_alias=True))
    except WebSocketDisconnect:
        pass
    finally:
        receiver.cancel()
        try:
            await websocket.close()
        except RuntimeError:
            pass
