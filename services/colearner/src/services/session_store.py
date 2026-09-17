import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.domain.schemas import SessionConfig


class SessionState:
    def __init__(self, session_id: str, config: SessionConfig):
        self.session_id: str = session_id
        self.config: SessionConfig = config
        self.created_at: datetime = datetime.now()
        self.turn_index: int = 0
        self.is_completed: bool = False
        self.turns: List[Dict[str, str]] = []

        # Provider-specific conversation state (see chained_service.py /
        # multimodal_service.py - each pipeline only ever populates one of
        # these, since the model is now fixed per pipeline).
        self.openai_messages: List[Dict[str, Any]] = []
        self.gemini_chat: Any = None
        self.report: Optional[Dict[str, Any]] = None

        # Token and cost metrics
        self.turn_metrics: List[Dict[str, Any]] = []
        self.cost_report: Optional[Dict[str, Any]] = None
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_audio_seconds: float = 0.0
        self.total_cost_usd: float = 0.0


class SessionStore:
    """In-memory only - v1 limitation: sessions do not survive a container
    restart and are not shared across replicas. Acceptable for now (single
    worker, no --reload multi-process in a real deploy, matching how
    auth/core/kg already run) rather than adding Redis/a DB for this alone
    (see nool-core/claude.md: don't add infra without an actual
    requirement). Revisit if this service needs to scale horizontally or
    survive restarts mid-session.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}

    def create_session(self, config: SessionConfig) -> SessionState:
        session_id = str(uuid.uuid4())
        session = SessionState(session_id=session_id, config=config)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)

    def save_session(self, session: SessionState) -> None:
        self._sessions[session.session_id] = session

    def delete_session(self, session_id: str) -> bool:
        self._sessions.pop(session_id, None)
        return True


session_store = SessionStore()
