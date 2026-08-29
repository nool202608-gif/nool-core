from datetime import datetime

from src.domain.models import ImportJobType

from .common import CamelModel


class ImportJobOut(CamelModel):
    id: str
    school_id: str
    school_name: str
    initiated_by: str
    initiated_by_name: str
    job_type: ImportJobType
    filename: str
    row_count: int
    created_count: int
    error_count: int
    created_at: datetime
