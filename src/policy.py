"""共享业务规则：硬性发布要求判定。

由 apply_guardrail（Agent 护栏）与 MockLLM._after_slots（决策器）共用，
避免「硬/软判定口径」在两处漂移。
"""


def is_hard(requirement: dict) -> bool:
    """硬性要求：hard_constraint=true 或存在 hard_deadline。

    硬性要求的 preferred_time 不可擅自变更；时段冲突时必须阻断并请求确认。
    """
    if not requirement:
        return False
    return bool(requirement.get("hard_constraint")) or requirement.get("hard_deadline") is not None
