"""ReAct 循环：模型选择动作 -> 执行工具 -> 观察结果 -> 调整下一步或结束。

含两项关键防御：
- 步数上限 MAX_TOOL_CALLS，达到上限返回明确的「未完成」状态。
- 后置校验护栏 apply_guardrail，拦截越权修改硬性发布要求的保存动作。
"""
from typing import Callable, List, Optional

from .llm import LLM
from .llm.base import Action
from .policy import is_hard
from .tools import execute, FINISH
from .tools.utils import time_to_minutes

MAX_TOOL_CALLS = 10


def apply_guardrail(action: Action, state: dict) -> Action:
    """后置校验护栏：防止模型擅自修改硬性发布要求。"""
    if action.name != "save_draft":
        return action

    asset = state.get("asset")
    if not asset:
        return action
    req = asset.get("publish_requirement", {})
    slot = action.args.get("slot")
    preferred = req.get("preferred_time")
    deadline = req.get("hard_deadline")
    hard = is_hard(req)

    slot_min = time_to_minutes(slot) if slot else None
    dl_min = time_to_minutes(deadline) if deadline else None

    reasons = []
    if hard and preferred and slot != preferred:
        reasons.append("护栏拦截：硬性要求时段不可擅自变更")
    if slot_min is not None and dl_min is not None and slot_min > dl_min:
        reasons.append("护栏拦截：超出硬性截止时间")

    if reasons:
        state["review_status"] = "blocked"
        state["pending_confirmations"] = reasons
        state["phase"] = "done"
        return Action("finish", {}, "护栏拦截越权保存", "guardrail")

    return action


def process_asset(
    asset_id: str,
    date: str,
    llm: LLM,
    store: dict,
    interactive: bool = False,
    confirm_fn: Optional[Callable] = None,
) -> dict:
    state = {
        "asset_id": asset_id,
        "date": date,
        "phase": "start",
        "review_status": "pending",
        "tool_calls": 0,
    }
    obs = None
    steps: List[dict] = []
    finished = False

    for step in range(1, MAX_TOOL_CALLS + 1):
        action = llm.decide(state, obs)
        action = apply_guardrail(action, state)

        # 交互模式：保存带待确认项的草稿前，请求用户确认
        if (
            interactive
            and action.name == "save_draft"
            and action.args.get("pending_confirmations")
            and confirm_fn is not None
        ):
            if not confirm_fn(asset_id, action.args["slot"], action.args["pending_confirmations"]):
                state["review_status"] = "pending_confirmation"
                state["pending_confirmations"] = action.args["pending_confirmations"] + [
                    "用户未确认，暂不保存"
                ]
                state["phase"] = "done"
                action = Action("finish", {}, "用户未确认，跳过保存", "interactive")

        steps.append(
            {
                "step": step,
                "thought": action.thought,
                "action": action.name,
                "action_input": action.args,
                "source": action.source,
                "observation": obs,
            }
        )

        if action.name == FINISH:
            finished = True
            break

        obs = execute(action.name, action.args, store)
        state["tool_calls"] = step

    if not finished:
        state["unfinished"] = True
        state["review_status"] = "unfinished"
        state["unfinished_reason"] = f"超过 {MAX_TOOL_CALLS} 次工具调用上限"

    return build_result(state, steps)


def build_result(state: dict, steps: List[dict]) -> dict:
    return {
        "asset_id": state["asset_id"],
        "review_status": state.get("review_status"),
        "risk_reasons": [r.get("reason") for r in state.get("risks", [])],
        "missing_fields": state.get("missing_fields", []),
        "suggested_slot": state.get("suggested_slot"),
        "pending_confirmations": state.get("pending_confirmations", []),
        "draft_status": state.get("draft_status", "none"),
        "draft": state.get("draft"),
        "draft_error": state.get("draft_error"),
        "error": state.get("error"),
        "unfinished": state.get("unfinished", False),
        "unfinished_reason": state.get("unfinished_reason"),
        "tool_calls": state.get("tool_calls", 0),
        "trace": steps,
    }


def run(
    asset_ids: List[str],
    date: str,
    llm: LLM,
    store: dict,
    interactive: bool = False,
    confirm_fn: Optional[Callable] = None,
) -> List[dict]:
    """依次处理多个素材；store.drafts 共享，重复提交会命中幂等去重。"""
    results = []
    for aid in asset_ids:
        results.append(process_asset(aid, date, llm, store, interactive, confirm_fn))
    return results
