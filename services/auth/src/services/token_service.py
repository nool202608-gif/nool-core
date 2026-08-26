from shared.auth import AuthenticatedUser, authenticate_with_password, verify_token


class TokenService:
    """Verifies the caller's token via whichever identity provider is
    configured - see shared/auth/provider.py. The provider itself is
    constructed and registered once, at app startup (src/main.py's
    create_app(), the one place in the Auth service that names Firebase
    concretely - mirrors nool-apps' AuthProvider.tsx, which has exactly
    one line naming its concrete identity service). It must not be
    reconstructed per-request: firebase_admin.initialize_app() is a
    process-global operation, so a second FirebaseIdentityProvider calling
    it again - even a fresh instance - raises "the default Firebase app
    already exists" against the one process-wide app the first instance
    already created.
    """

    def verify(self, token: str) -> AuthenticatedUser:
        return verify_token(token)

    def authenticate(self, email: str, password: str) -> str:
        """Checks email/password against the identity provider and returns
        a custom token for the client to exchange for its own session -
        see shared/auth/provider.py's PasswordAuthResult.
        """
        return authenticate_with_password(email, password).custom_token
