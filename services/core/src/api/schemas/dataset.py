from src.domain.models import DatasetType

from .common import CamelModel


class DatasetOut(CamelModel):
    id: str
    name: str
    question_count: int
    description: str
    # QA (a hand-curated question/answer bank) or PRIMARY_CONTENT (raw
    # source content grounding real, on-demand generation) - see
    # DatasetType's docstring. Surfaced here so a teacher blending this
    # dataset into a paper (QuestionPaperDatasetShare) can tell which kind
    # they're picking - a PRIMARY_CONTENT share sets the paper's KG scope,
    # a QA share is a stored-question pool.
    type: DatasetType


class DatasetShare(CamelModel):
    dataset_id: str
    percent: int
