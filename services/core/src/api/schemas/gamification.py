from .common import CamelModel


class DailyGoalOut(CamelModel):
    id: str
    title: str
    subtitle: str
    xp_reward: int
    completed: bool


class AchievementOut(CamelModel):
    id: str
    title: str
    icon_key: str
    unlocked: bool


class StudentGamificationOut(CamelModel):
    level: int
    xp: int
    xp_for_next_level: int
    daily_goals: list[DailyGoalOut]
    achievements: list[AchievementOut]


class AwardSessionXpIn(CamelModel):
    xp_earned: int
    completed_goal_id: str | None = None
