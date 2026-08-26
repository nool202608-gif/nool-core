import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .mixins import IdMixin


class Dataset(IdMixin, Base):
    """A global question-bank catalog used as the grounding pool for
    Homework and Question Paper generation.
    """

    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(String)
    question_count: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)


class SchoolDataset(IdMixin, Base):
    """Which datasets a school has enabled - see PUT /api/v1/school/datasets.
    Scopes what a Teacher at that school sees in GET /api/v1/datasets, the
    same way SchoolCurriculum scopes GET /api/v1/subjects.
    """

    __tablename__ = "school_datasets"
    __table_args__ = (UniqueConstraint("school_id", "dataset_id"),)

    school_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("schools.id"))
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
