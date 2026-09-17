"""The single star-rating formula for a completed session's mastery
percent - shared so a chapter's stars on the Journey map
(test_completion.py's StudentChapterProgress write) always match the same
1-3 star reveal the student already saw on their own win screen
(nool-apps' features/ai-learner/computeSessionReward.ts uses the exact
same thresholds client-side - keep both in sync if this ever changes).
"""


def stars_for_mastery_percent(mastery_percent: int) -> int:
    if mastery_percent >= 85:
        return 3
    if mastery_percent >= 65:
        return 2
    return 1
