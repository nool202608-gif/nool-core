from .bloom import BloomScore
from .common import CamelModel


class StudentTestBloomResultOut(CamelModel):
    test_id: str
    overall_percent: int
    bloom_performance: list[BloomScore]
