from fastapi import APIRouter

from shared.errors import NotFoundError

from src.api.schemas import ChapterTreeOut, CurriculumTreeOut, TopicTreeOut
from src.services.neo4j_client import get_curriculum_tree

router = APIRouter(tags=["curriculum"])


@router.get("/curriculum/tree", response_model=CurriculumTreeOut)
async def curriculum_tree(board: str = "CBSE", grade: int = 10, subject: str = "Science") -> CurriculumTreeOut:
    """Read by nool-core's Core service (POST /admin/curriculum/sync-from-kg,
    Super-Admin-triggered) to upsert Subject/Chapter/Topic in Postgres.
    """
    tree = await get_curriculum_tree(board=board, grade=grade, subject=subject)
    if tree is None:
        raise NotFoundError(f'No curriculum in the graph for {board} grade {grade} {subject}.')
    return CurriculumTreeOut(
        board=tree["board"],
        grade=tree["grade"],
        subject=tree["subject"],
        chapters=[
            ChapterTreeOut(
                ref=ch["ref"],
                number=ch["number"],
                name=ch["name"],
                topics=[
                    TopicTreeOut(ref=t["ref"], number=t["number"], name=t["name"])
                    for t in ch["topics"]
                    if t.get("ref") is not None
                ],
            )
            for ch in tree["chapters"]
        ],
    )
