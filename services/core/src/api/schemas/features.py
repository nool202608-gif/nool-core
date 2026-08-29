from src.domain.models import Feature

from .common import CamelModel


class FeaturesOut(CamelModel):
    """A school's feature entitlements - see School.enabled_features'
    docstring. None = no override set, every feature is enabled.
    """

    enabled_features: list[Feature] | None


class UpdateFeaturesIn(CamelModel):
    enabled_features: list[Feature] | None
