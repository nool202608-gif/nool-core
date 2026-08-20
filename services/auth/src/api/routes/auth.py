from fastapi import APIRouter, Depends

from src.api.deps import get_current_user
from src.domain.user import AuthenticatedUser

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.get("/me")
async def get_me(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """Returns the authenticated caller's identity as extracted from their
    Firebase ID token. This is the foundation for authenticated-user
    extraction - it does not yet resolve a nool User/role/school profile.
    """
    return {"uid": user.uid, "email": user.email}
