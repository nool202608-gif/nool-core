from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ValidationError

from src.api.deps import get_db_session, require_role
from src.api.schemas.assistant import ChatMessageOut, SendMessageIn
from src.api.schemas.common import ListEnvelope
from src.domain.models import AssistantMessage, ChatRole, Role, User

router = APIRouter(prefix="/api/v1", tags=["assistant"])

_GREETING = (
    "Hi, I'm your Nool assistant. Ask me about Voice Tests, Homework, Question Papers, "
    "or a class's progress."
)

# Deterministic keyword-matcher, not a real LLM integration - see
# CLAUDE.md's "Current Goal" and nool-apps' own MockAssistantService,
# which this mirrors exactly.
_RULES: list[tuple[str, str]] = [
    ("voice test", "To create a Voice Test: Home → Create → Voice Test, then pick a class, subject, chapter, topic and Bloom levels, and schedule it."),
    ("homework", "Homework is generated from a Test's diagnostic gap once results are ready - open the Test's results and choose Generate Homework."),
    ("question paper", "Question Papers are built independently of Voice Tests - go to Question Papers → New, configure the blueprint, then Generate."),
    ("progress", "Check a class's progress from the Improvement tab on a completed Test, or the class-level analytics on your dashboard."),
]


def _reply_for(text: str) -> str:
    lowered = text.lower()
    for keyword, reply in _RULES:
        if keyword in lowered:
            return reply
    return "I'm not sure about that yet - try asking about Voice Tests, Homework, Question Papers, or a class's progress."


async def _ensure_greeting(session: AsyncSession, teacher_id) -> None:
    existing = await session.execute(
        select(AssistantMessage.id).where(AssistantMessage.teacher_id == teacher_id).limit(1)
    )
    if existing.scalar_one_or_none() is None:
        session.add(AssistantMessage(teacher_id=teacher_id, role=ChatRole.ASSISTANT, text=_GREETING))
        await session.commit()


@router.get("/assistant/messages")
async def list_messages(
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[ChatMessageOut]:
    """The full thread, oldest first. Always has at least one message - a
    fixed greeting seeds a new thread.
    """
    await _ensure_greeting(session, user.id)
    result = await session.execute(
        select(AssistantMessage)
        .where(AssistantMessage.teacher_id == user.id)
        .order_by(AssistantMessage.created_at)
    )
    items = [
        ChatMessageOut(id=str(m.id), role=m.role, text=m.text, created_at=m.created_at)
        for m in result.scalars().all()
    ]
    return ListEnvelope(items=items, total=len(items))


@router.post("/assistant/messages", status_code=201, summary="Send a message")
async def send_message(
    body: SendMessageIn,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ChatMessageOut:
    """Appends the teacher's message to the thread server-side, then
    returns only the assistant's reply - not the full thread - so the
    client appends both turns locally instead of re-fetching.
    """
    text = body.text.strip()
    if not text:
        raise ValidationError("text is empty after trimming.")

    await _ensure_greeting(session, user.id)
    session.add(AssistantMessage(teacher_id=user.id, role=ChatRole.USER, text=text))
    reply = AssistantMessage(teacher_id=user.id, role=ChatRole.ASSISTANT, text=_reply_for(text))
    session.add(reply)
    await session.commit()
    await session.refresh(reply)
    return ChatMessageOut(id=str(reply.id), role=reply.role, text=reply.text, created_at=reply.created_at)
