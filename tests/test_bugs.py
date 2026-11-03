"""Bug 暴露用例：断言「正确行为」，当前实现不满足时会失败。

这些用例刻意与实现相悖，用于记录发现的缺陷；失败即证据。
"""
from src.agent import apply_guardrail, process_asset
from src.llm import create_llm
from src.llm.base import Action
from src.llm.mock import MockLLM
from src.tools.utils import time_to_minutes

DATE = "2026-11-04"


# ---- Bug 1：time_to_minutes 未校验分钟/小时越界 ----
def test_bug_time_to_minutes_rejects_invalid_minutes():
    # 期望：非法分钟返回 None；实际：18:60 -> 1140
    assert time_to_minutes("18:60") is None


def test_bug_time_to_minutes_rejects_out_of_range_hour():
    # 期望：小时越界返回 None；实际：25:00 -> 1500
    assert time_to_minutes("25:00") is None


# ---- Bug 2：_find_free 仅向前搜索，忽略更早的空闲时段 ----
def test_bug_find_free_considers_earlier_free_slot():
    slots = [
        {"time": "09:00", "status": "free"},
        {"time": "20:00", "status": "occupied"},
    ]
    # 期望：preferred 20:00 被占用时，返回最近空闲 09:00；实际：None（误报无替代）
    assert MockLLM._find_free(slots, "20:00", None) == "09:00"


# ---- Bug 3：hard_deadline 未计入「硬性」判定（护栏放行改时段）----
def test_bug_hard_deadline_makes_preferred_immutable():
    asset = {
        "asset_id": "X",
        "publish_requirement": {
            "preferred_time": "18:00",
            "hard_constraint": False,
            "hard_deadline": "19:00",
        },
    }
    state = {"asset": asset, "phase": "save_draft"}
    # 期望：含 hard_deadline 即硬性，改 18:00 -> 19:00 应被拦截；实际：放行 save_draft
    a = apply_guardrail(Action("save_draft", {"slot": "19:00"}, "改时段", "llm:x"), state)
    assert a.name == "finish"


# ---- Bug 3（续）：Mock 冲突决策同样忽略 hard_deadline，硬性被降级为软性 ----
def test_bug_hard_deadline_conflict_treated_as_hard(store):
    store["assets"] = [
        {
            "asset_id": "H1",
            "title": "t",
            "category": "marketing",
            "owner": "o",
            "duration_min": 5,
            "risk_flags": [],
            "publish_requirement": {
                "preferred_time": "18:00",
                "hard_constraint": False,
                "hard_deadline": "19:00",
                "flexible": False,
            },
        }
    ]
    llm = create_llm("mock")
    r = process_asset("H1", DATE, llm, store)
    # 期望：硬性要求（含 deadline）时段被占 -> blocked + 需确认、未擅自变更
    # 实际：approved + 建议 19:00 + drafted（被当作软性自动替换）
    assert r["review_status"] == "blocked"
    assert any("未擅自变更" in p for p in r["pending_confirmations"])
