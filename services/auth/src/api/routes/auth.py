from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.domain.user import AuthenticatedUser
from src.services.token_service import TokenService

router = APIRouter(prefix="/api/v1", tags=["auth"])


class LoginIn(BaseModel):
    # Plain str, not EmailStr: real validation is "does Firebase accept
    # these credentials," not client-side format-checking, and EmailStr
    # would pull in the email-validator package for no real benefit here.
    email: str
    password: str


@router.post("/login")
async def login(body: LoginIn) -> dict:
    """Credential check moved server-side: the client sends email/password
    here (never straight to Firebase - see shared/auth/providers/firebase.py's
    authenticate_with_password) and gets back a short-lived custom token to
    exchange for its own Firebase session via signInWithCustomToken. Bad
    credentials raise UnauthorizedError (401), handled by the standard
    error envelope - see shared/errors/handlers.py.
    """
    custom_token = TokenService().authenticate(body.email, body.password)
    return {"customToken": custom_token}


@router.get("/me")
async def get_me(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """Returns the authenticated caller's identity as extracted from their
    Firebase ID token, including their application role if one has been
    assigned (see scripts/set_role.py - `role` is a custom claim, not set
    by any other means). `role` is null for an account with no role
    assigned yet - a real, expected state, not an error. This is still the
    foundation for authenticated-user extraction - it does not resolve a
    full nool User/school profile, since no such table exists yet.
    """
    return {"uid": user.uid, "email": user.email, "role": user.role}
