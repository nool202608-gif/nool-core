from .common import CamelModel


class SchoolLogoOut(CamelModel):
    """See School.logo_data_uri's docstring. None = no logo set."""

    logo_data_uri: str | None


class UpdateSchoolLogoIn(CamelModel):
    logo_data_uri: str | None
