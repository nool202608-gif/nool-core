"""Creates real, login-capable Firebase accounts for admin-provisioned
users (teacher invite, student create, school admin invite) - no email
step anywhere in this codebase. A random temp password is generated here,
returned to the caller exactly once, and never persisted in plaintext.

Uses firebase_admin.get_app() - the process-wide default app - rather than
constructing its own. This is safe, not incidental: every route that calls
into this module sits behind require_role, which resolves through
get_current_user -> verify_token -> FirebaseIdentityProvider._get_app()
before the route body ever runs (see src/api/deps.py), so the default app
is always already initialized by the time create_firebase_user() is
called. See services/auth/src/services/token_service.py's docstring for
why a *second* FirebaseIdentityProvider must never call initialize_app()
again - this module never does, for the same reason.
"""

import secrets
from dataclasses import dataclass

import firebase_admin
from firebase_admin import auth as firebase_auth

from shared.errors import ConflictError

from src.domain.models import Role


@dataclass
class ProvisionedUser:
    firebase_uid: str
    temp_password: str


def _generate_temp_password() -> str:
    # url-safe, comfortably exceeds Firebase's 6-character minimum, no
    # ambiguous-character concerns since it's shown once and copy-pasted,
    # never hand-typed.
    return secrets.token_urlsafe(9)


def create_firebase_user(*, email: str, display_name: str, role: Role) -> ProvisionedUser:
    app = firebase_admin.get_app()
    temp_password = _generate_temp_password()
    try:
        user_record = firebase_auth.create_user(
            email=email,
            password=temp_password,
            display_name=display_name,
            app=app,
        )
    except firebase_auth.EmailAlreadyExistsError as exc:
        raise ConflictError(f'An account with email "{email}" already exists.') from exc

    firebase_auth.set_custom_user_claims(
        user_record.uid, {"role": role.value, "mustChangePassword": True}, app=app
    )
    return ProvisionedUser(firebase_uid=user_record.uid, temp_password=temp_password)


def reset_password(*, firebase_uid: str, role: Role) -> str:
    """Called by a School/Super Admin action against an EXISTING account -
    the no-email-recovery path: there is no self-service "forgot password"
    here since there's no email channel to verify identity through (see
    this module's top-of-file docstring). Generates a brand new temp
    password, sets it directly on the account via update_user (unlike
    create_firebase_user, this account already exists), and re-flags
    mustChangePassword so the recipient goes through the same one-time
    change flow as a fresh invite.
    """
    app = firebase_admin.get_app()
    temp_password = _generate_temp_password()
    firebase_auth.update_user(firebase_uid, password=temp_password, app=app)
    firebase_auth.set_custom_user_claims(
        firebase_uid, {"role": role.value, "mustChangePassword": True}, app=app
    )
    return temp_password


def clear_must_change_password_claim(*, firebase_uid: str, role: Role) -> None:
    """Called once the invitee has changed their temp password - re-sets
    the claim with mustChangePassword: False, preserving role.
    """
    app = firebase_admin.get_app()
    firebase_auth.set_custom_user_claims(
        firebase_uid, {"role": role.value, "mustChangePassword": False}, app=app
    )
