from src.domain.models import Feature, Plan


def effective_enabled_features(*, plan: Plan | None) -> list[Feature] | None:
    """None = every feature enabled - the default until a Super Admin
    narrows a plan's `enabled_features`. This is the single source of
    truth for feature access (configured on the plan/subscription, flows
    to every school on it) - see Plan.enabled_features' docstring and
    requirements.md §7.14.
    """
    if plan is None or plan.enabled_features is None:
        return None
    return [Feature(value) for value in plan.enabled_features]


def is_feature_enabled(feature: Feature, *, plan: Plan | None) -> bool:
    effective = effective_enabled_features(plan=plan)
    return effective is None or feature in effective
