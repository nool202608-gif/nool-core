"""Firebase ID token verification - the shared foundation used by every
service that needs to know who is calling it.

Firebase is the identity provider for the whole platform; the Auth service
owns the user-facing identity flows, but token verification itself is generic
infrastructure (JWT verification against Firebase's public keys) that any
service can perform independently without calling out to the Auth service
for every request.
"""

from .firebase import (
    AuthenticatedUser,
    FirebaseNotConfiguredError,
    configure_firebase,
    reset_firebase_state,
    verify_id_token,
)

__all__ = [
    "AuthenticatedUser",
    "FirebaseNotConfiguredError",
    "configure_firebase",
    "reset_firebase_state",
    "verify_id_token",
]
