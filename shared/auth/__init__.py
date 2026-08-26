"""Identity-provider-agnostic authentication for every service.

See provider.py for the IdentityProvider seam. Services never import a
concrete provider (e.g. FirebaseIdentityProvider) here or in route
handlers/business logic - only in the one place each service's deps.py
constructs one (see providers/firebase.py's docstring for why). Swapping
the identity provider means adding a new class under providers/ and
changing those construction call sites - nothing that imports from this
top-level package should need to change.
"""

from ..errors.exceptions import AppError
from .provider import AuthenticatedUser, IdentityProvider, PasswordAuthResult


class IdentityProviderNotConfiguredError(AppError):
    code = "AUTH_NOT_CONFIGURED"
    status_code = 500


_provider: IdentityProvider | None = None


def configure_identity_provider(provider: IdentityProvider) -> None:
    """Stores the active identity provider. Called once per request by
    each service's get_current_user() dependency, passing a freshly
    constructed provider built from that service's own settings - cheap,
    since a well-behaved provider only does real work (e.g. opening a
    Firebase app) lazily, on first verify_token() call, not here.
    """
    global _provider
    _provider = provider


def verify_token(token: str) -> AuthenticatedUser:
    if _provider is None:
        raise IdentityProviderNotConfiguredError("No identity provider is configured.")
    return _provider.verify_token(token)


def authenticate_with_password(email: str, password: str) -> PasswordAuthResult:
    if _provider is None:
        raise IdentityProviderNotConfiguredError("No identity provider is configured.")
    return _provider.authenticate_with_password(email, password)


def reset_identity_provider() -> None:
    """Test helper: clears the configured provider between test cases."""
    global _provider
    _provider = None


__all__ = [
    "AuthenticatedUser",
    "IdentityProvider",
    "IdentityProviderNotConfiguredError",
    "PasswordAuthResult",
    "configure_identity_provider",
    "verify_token",
    "authenticate_with_password",
    "reset_identity_provider",
]
