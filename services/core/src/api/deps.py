from collections.abc import AsyncIterator

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import AuthenticatedUser, verify_token
from shared.errors import ForbiddenError, UnauthorizedError

from src.domain.models import Role, User
from src.repositories import get_by_firebase_uid, get_session


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise UnauthorizedError("Missing or malformed Authorization header.")
    return token


def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    """Authentication middleware foundation for Core.

    Core verifies tokens independently rather than calling the Auth
    service per-request - tokens are self-contained, so any service can
    verify them via the same shared.auth IdentityProvider seam the Auth
    service uses (see shared/auth/provider.py). The provider itself is
    constructed and registered once, at app startup (src/main.py's
    create_app() - the one place in Core that names FirebaseIdentityProvider
    concretely), not here - see token_service.py's docstring in the Auth
    service for why per-request construction is unsafe.
    """
    token = _extract_bearer_token(authorization)
    return verify_token(token)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-compatible wrapper around repositories.get_session's
    @asynccontextmanager (which is written for plain ``async with`` use,
    not as a raw FastAPI dependency).
    """
    async with get_session() as session:
        yield session


async def get_current_app_user(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Resolves the verified Firebase identity to Core's own `users` row -
    the actual authorization-relevant identity (role, school_id), which a
    bare Firebase custom claim can't carry (no school_id at all). Raises
    UnauthorizedError if the token is valid but no application user exists
    yet - every route except GET /api/v1/me itself requires a resolved
    profile, so this is the right layer to reject at (mirrors the doc's
    "valid token, no profile" state, which only /me surfaces as data).
    """
    app_user = await get_by_firebase_uid(session, user.uid)
    if app_user is None:
        raise UnauthorizedError("No application profile exists for this account yet.")
    return app_user


def require_role(*roles: Role):
    """FastAPI dependency factory: 403s unless the caller's resolved role
    is one of `roles`. Route-level scoping (Teacher -> own school, Student
    -> /me/*, Super Admin -> cross-tenant, School Admin -> own school) is
    layered on top of this in each router, not here - this only answers
    "is this role allowed to call this route at all."
    """

    async def _check(user: User = Depends(get_current_app_user)) -> User:
        if user.role not in roles:
            raise ForbiddenError("Your role does not permit this action.")
        return user

    return _check
