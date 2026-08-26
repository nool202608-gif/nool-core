from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class PasswordAuthResult:
    """Returned by IdentityProvider.authenticate_with_password on a
    successful credential check. Deliberately not the raw provider
    session (e.g. Firebase's own idToken/refreshToken pair) - callers
    (services/auth/src/api/routes/auth.py's /login) hand this custom_token
    to the client, which exchanges it for a real client-side session via
    the provider's own client SDK (signInWithCustomToken). This keeps
    token refresh/session persistence entirely inside that SDK - the
    backend's only job is the one thing a browser/app cannot safely do
    itself: hold the credential-check secret.
    """

    custom_token: str


@dataclass(frozen=True)
class AuthenticatedUser:
    """Provider-agnostic authenticated caller. Every IdentityProvider
    implementation must produce this same shape regardless of what its
    underlying identity provider calls its own token/claims - route
    handlers and business logic depend only on this, never on a specific
    provider's SDK types.
    """

    uid: str
    email: str | None
    claims: dict[str, Any]
    role: str | None = None


class IdentityProvider(Protocol):
    """The seam between nool-core services and whatever identity provider
    is actually in use (see shared/auth/providers/). Swapping providers -
    Firebase to Keycloak, or anything else - means writing a new class
    that satisfies this Protocol and changing the single line in each
    service's deps.py that constructs one (see
    shared/auth/providers/firebase.py's docstring). Nothing else -
    route handlers, business logic, tests using a fake provider - should
    need to change.
    """

    def verify_token(self, token: str) -> AuthenticatedUser:
        """Verifies a caller-supplied token and returns the identity it
        represents. Must raise UnauthorizedError (not a provider-specific
        exception type) for any invalid/expired/malformed/revoked token -
        callers never see, and must not need to know, which provider is
        active.
        """
        ...  # noqa: B027 - Protocol method, not an incomplete override

    def authenticate_with_password(self, email: str, password: str) -> PasswordAuthResult:
        """Checks a caller-supplied email/password against the identity
        provider and, on success, returns a token the client can exchange
        for its own session (see PasswordAuthResult). Must raise
        UnauthorizedError for any bad-credentials case, without
        distinguishing "no such account" from "wrong password" (that
        distinction is an enumeration risk, not a UX requirement).
        """
        ...  # noqa: B027 - Protocol method, not an incomplete override


__all__ = ["AuthenticatedUser", "IdentityProvider", "PasswordAuthResult"]
