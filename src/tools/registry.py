"""工具注册与统一调度。

所有工具返回统一的 observation dict：成功含 "ok": True，失败含 "ok": False + "error"。
调度层捕获工具异常，统一封装为失败，保证决策器总能拿到结构化结果。
"""
from .read_asset import read_asset
from .check_rules import check_rules
from .query_slots import query_slots
from .save_draft import save_draft

TOOLS = {
    "read_asset": read_asset,
    "check_rules": check_rules,
    "query_slots": query_slots,
    "save_draft": save_draft,
}

FINISH = "finish"


def execute(action_name: str, args: dict, store: dict) -> dict:
    fn = TOOLS.get(action_name)
    if fn is None:
        return {"ok": False, "error": f"未知工具：{action_name}"}
    try:
        return fn(args or {}, store)
    except Exception as exc:  # 工具异常也返回结构化失败
        return {"ok": False, "error": f"工具 {action_name} 执行异常：{exc}"}
