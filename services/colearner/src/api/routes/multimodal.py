import json

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from shared.auth import AuthenticatedUser
from shared.errors import UnauthorizedError

from src.api.deps import get_current_user
from src.domain.schemas import CoLearnerRequest, CoLearnerResponse, SessionConfig
from src.services.audio_service import decode_base64_audio
from src.services.multimodal_service import process_multimodal_turn
from src.services.session_store import session_store

router = APIRouter(prefix="/api/v1", tags=["colearner-multimodal"])


@router.post("/colearner/multimodal", response_model=CoLearnerResponse, summary="Multimodal Voice Co-Learner Turn")
async def handle_multimodal_turn(
    payload: CoLearnerRequest,
    _user: AuthenticatedUser = Depends(get_current_user),
) -> CoLearnerResponse:
    """
    Turn-based Multimodal Voice Co-Learner endpoint (direct audio-in to
    Gemini native audio - no STT step).
    - On Turn 0 (init): send JSON config (with textbook_context & reference_questions).
      Returns the initial greeting text + audio.
    - On subsequent turns: send session_id and user_audio_base64 (or user_text).
      Returns student transcript, AI reply, audio base64, and the final report on completion.
    """
    if payload.session_id:
        session = session_store.get_session(payload.session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session '{payload.session_id}' not found or expired.")
    else:
        config = payload.config or SessionConfig()
        session = session_store.create_session(config=config)

    user_bytes = decode_base64_audio(payload.user_audio_base64) if payload.user_audio_base64 else None

    transcript, ai_text, audio_b64, is_completed, report, turn_metrics, cost_report, is_hint_reply = await process_multimodal_turn(
        session=session,
        user_audio_bytes=user_bytes,
        user_text=payload.user_text,
        time_limit_reached=payload.time_limit_reached,
        is_hint_request=payload.is_hint_request,
    )

    session_store.save_session(session)

    return CoLearnerResponse(
        session_id=session.session_id,
        turn_index=session.turn_index,
        student_transcript=transcript,
        co_learner_text=ai_text,
        co_learner_audio_base64=audio_b64,
        audio_mime_type="audio/mpeg",
        is_completed=is_completed,
        report=report,
        turn_metrics=turn_metrics,
        cost_report=cost_report,
        is_hint_reply=is_hint_reply,
    )


@router.websocket("/colearner/multimodal/stream")
async def stream_multimodal_session(websocket: WebSocket, token: str = Query(...)) -> None:
    """
    Live streaming WebSocket connection for the Multimodal Voice Co-Learner.
    Auth: pass the Firebase ID token as the ?token= query param - same
    pattern as services/core/src/api/routes/ai_assessor.py's stream_session
    (and this service's own chained.py stream_chained_session).

    Protocol identical to /colearner/chained/stream (see chained.py), but
    the client sends raw audio bytes straight to Gemini - no STT.
    """
    # accept() must happen before any close() with a custom code - see
    # chained.py's stream_chained_session for why.
    await websocket.accept()
    try:
        get_current_user(authorization=f"Bearer {token}")
    except UnauthorizedError:
        await websocket.close(code=4401)
        return

    try:
        init_data = await websocket.receive_text()
        init_json = json.loads(init_data)
        config = SessionConfig(**init_json.get("config", {}))
        session = session_store.create_session(config=config)

        transcript, ai_text, audio_b64, is_completed, report, turn_metrics, cost_report, is_hint_reply = await process_multimodal_turn(session, None)
        await websocket.send_json({
            "event": "greeting",
            "session_id": session.session_id,
            "turn_index": session.turn_index,
            "co_learner_text": ai_text,
            "co_learner_audio_base64": audio_b64,
            "is_completed": False,
            "turn_metrics": turn_metrics,
            "is_hint_reply": is_hint_reply,
        })

        while not session.is_completed:
            msg_data = json.loads(await websocket.receive_text())
            b64_audio = msg_data.get("user_audio_base64")
            user_text = msg_data.get("user_text")
            user_bytes = decode_base64_audio(b64_audio) if b64_audio else None
            time_limit_reached = bool(msg_data.get("time_limit_reached", False))
            is_hint_request = bool(msg_data.get("is_hint_request", False))

            transcript, ai_text, audio_b64, is_completed, report, turn_metrics, cost_report, is_hint_reply = await process_multimodal_turn(
                session, user_bytes, user_text, time_limit_reached, is_hint_request
            )
            await websocket.send_json({
                "event": "ai_turn" if not is_completed else "session_completed",
                "session_id": session.session_id,
                "turn_index": session.turn_index,
                "student_transcript": transcript,
                "co_learner_text": ai_text,
                "co_learner_audio_base64": audio_b64,
                "is_completed": is_completed,
                "report": report,
                "turn_metrics": turn_metrics,
                "cost_report": cost_report,
                "is_hint_reply": is_hint_reply,
            })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"event": "error", "detail": str(e)})
