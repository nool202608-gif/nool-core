from enum import Enum

from .common import CamelModel


class StreakDayState(str, Enum):
    DONE = "DONE"
    TODAY = "TODAY"
    UPCOMING = "UPCOMING"


class PendingActivityKind(str, Enum):
    TEST = "TEST"
    HOMEWORK = "HOMEWORK"
    RETEST = "RETEST"


class StreakDayOut(CamelModel):
    label: str
    state: StreakDayState


class LearningStreakOut(CamelModel):
    current_streak_days: int
    days: list[StreakDayOut]
    message: str


class ContinueJourneyOut(CamelModel):
    subject_id: str
    title: str
    message: str


class SubjectTodayOut(CamelModel):
    subject_id: str
    subject_label: str
    kind: PendingActivityKind
    title: str
    meta: str
    progress_percent: int
    for_you_title: str
    for_you_meta: str


class ProgressSummaryOut(CamelModel):
    overall_mastery_percent: int
    mastery_trend_label: str
    topics_improving: int


class StudentDashboardOut(CamelModel):
    streak: LearningStreakOut
    continue_journey: ContinueJourneyOut | None
    subject_today: list[SubjectTodayOut]
    progress_summary: ProgressSummaryOut
