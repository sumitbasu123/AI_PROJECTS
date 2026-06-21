"""Finance research goal runtime primitives.

Exports are resolved lazily so importing a lightweight helper such as
``src.goal.context`` does not initialize the full tool and provider stack.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORT_MODULES = {
    "AuditRow": "src.goal.models",
    "EvidenceInput": "src.goal.models",
    "EvidenceRecord": "src.goal.models",
    "GoalClaim": "src.goal.models",
    "GoalCriterion": "src.goal.models",
    "GoalRecord": "src.goal.models",
    "GoalStatus": "src.goal.models",
    "RiskTier": "src.goal.models",
    "StaleGoalError": "src.goal.models",
    "normalize_required_text": "src.goal.policy",
    "reject_live_execution_objective": "src.goal.policy",
    "GoalStore": "src.goal.store",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value

__all__ = [
    "AuditRow",
    "EvidenceInput",
    "EvidenceRecord",
    "GoalClaim",
    "GoalCriterion",
    "GoalRecord",
    "GoalStatus",
    "GoalStore",
    "RiskTier",
    "StaleGoalError",
    "normalize_required_text",
    "reject_live_execution_objective",
]
