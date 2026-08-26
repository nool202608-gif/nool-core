from src.domain.models import TestStatus

from .common import CamelModel


class TeacherDashboardClassOption(CamelModel):
    id: str
    label: str
    meta: str


class TeacherHeadlineTest(CamelModel):
    id: str
    title: str
    meta: str
    status: TestStatus


class TeacherDashboardOut(CamelModel):
    class_options: list[TeacherDashboardClassOption]
    active_class: TeacherDashboardClassOption
    headline_test: TeacherHeadlineTest | None  # null when the class has no Test yet
