from pydantic import model_validator

from src.domain.models import BloomLevel

from .common import CamelModel


class BloomScore(CamelModel):
    level: BloomLevel
    percent: int | None  # null = "Not assessed", never render as 0


class BloomDelta(CamelModel):
    level: BloomLevel
    before: int | None
    after: int | None


class BloomTarget(CamelModel):
    level: BloomLevel
    value: int  # never null; 0 is a valid config value


class BloomDistributionOut(CamelModel):
    """A school's default Bloom-level mix for new Question Papers/Homework
    - see School.default_bloom_distribution's docstring. None = no
    override set, generation falls back to whatever the teacher provides
    (or the deterministic generator's own default if that's empty too).
    """

    distribution: dict[BloomLevel, int] | None


class UpdateBloomDistributionIn(CamelModel):
    distribution: dict[BloomLevel, int]

    @model_validator(mode="after")
    def _check_sums_to_100(self) -> "UpdateBloomDistributionIn":
        if sum(self.distribution.values()) != 100:
            raise ValueError("Bloom distribution percentages must sum to 100.")
        return self
