from .common import CamelModel


class DatasetOut(CamelModel):
    id: str
    name: str
    question_count: int
    description: str


class DatasetShare(CamelModel):
    dataset_id: str
    percent: int
