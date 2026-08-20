from dataclasses import dataclass
from typing import Any

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

from ..errors.exceptions import AppError, UnauthorizedError


@dataclass(frozen=True)
class AuthenticatedUser:
    uid: str
    email: str | None
    claims: dict[str, Any]


class FirebaseNotConfiguredError(AppError):
    code = "AUTH_NOT_CONFIGURED"
    status_code = 500


_app: firebase_admin.App | None = None
_credentials_path: str | None = None
_project_id: str | None = None


def configure_firebase(credentials_path: str | None, project_id: str | None) -> None:
    """Stores Firebase configuration. Cheap and side-effect free - the actual
    Firebase Admin SDK app is only created lazily, on first token verification,
    so a service can start up without valid Firebase credentials configured.
    """
    global _credentials_path, _project_id
    _credentials_path = credentials_path
    _project_id = project_id


def _get_app() -> firebase_admin.App:
    global _app
    if _app is not None:
        return _app
    if not _project_id:
        raise FirebaseNotConfiguredError("Firebase project is not configured.")
    try:
        options = {"projectId": _project_id}
        if _credentials_path:
            cred = credentials.Certificate(_credentials_path)
            _app = firebase_admin.initialize_app(cred, options)
        else:
            _app = firebase_admin.initialize_app(options=options)
    except Exception as exc:
        raise FirebaseNotConfiguredError("Failed to initialize Firebase Admin SDK.") from exc
    return _app


def verify_id_token(token: str) -> AuthenticatedUser:
    app = _get_app()
    try:
        decoded = firebase_auth.verify_id_token(token, app=app)
    except Exception as exc:
        raise UnauthorizedError("Invalid or expired authentication token.") from exc
    return AuthenticatedUser(
        uid=decoded["uid"], email=decoded.get("email"), claims=decoded
    )


def reset_firebase_state() -> None:
    """Test helper: clears module-level Firebase state between test cases."""
    global _app, _credentials_path, _project_id
    if _app is not None:
        firebase_admin.delete_app(_app)
    _app = None
    _credentials_path = None
    _project_id = None
