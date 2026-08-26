from src.domain.models import Role

from .common import CamelModel


class ProfileOut(CamelModel):
    id: str
    role: Role
    display_name: str
    school: str
    # For clients that call this DB-backed /me directly (nool-school-admin,
    # nool-super-admin) - nool-apps instead reads the mirrored Firebase
    # custom claim, since it calls Auth's claim-only /me, which has no DB
    # access by design. Both read the same users.must_change_password
    # column - see src/services/user_provisioning.py.
    must_change_password: bool


class MeResponse(CamelModel):
    """profile: None means the token is genuinely valid but has no
    matching application user yet - a real, expected "unknown profile"
    state, not an error. See src/api/routes/profile.py.
    """

    profile: ProfileOut | None
