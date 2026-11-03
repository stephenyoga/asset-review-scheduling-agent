"""Agent 集成测试：ReAct 链路、结束条件、交互模式、仅草稿约束、护栏 deadline 分支。

与 tests/test_agent.py 的 6 验收点不重复，聚焦循环机制与边界。
"""
from src.agent import apply_guardrail, process_asset, run, MAX_TOOL_CALLS
from src.llm.base import Action, LLM
from src.tools.registry import TOOLS, FINISH

DATE = "2026-11-04"


# ---- ReAct 完整决策链路与结束条件 ----
def test_react_full_chain_action_sequence(store, llm):
    r = process_asset("M02", DATE, llm, store)
    actions = [s["action"] for s in r["trace"]]
    assert actions == ["read_asset", "check_rules", "query_slots", "save_draft", "finish"]
    # 最后一步必须结束，且结果不为 unfinished
    assert actions[-1] == FINISH
    assert r["unfinished"] is False


def test_react_ends_on_missing_info(store, llm):
    r = process_asset("M03", DATE, llm, store)
    actions = [s["action"] for s in r["trace"]]
    # 缺字段应在 read 后直接 finish，不进入 check/query/save
    assert actions == ["read_asset", "finish"]


def test_react_ends_on_rule_risk(store, llm):
    r = process_asset("M04", DATE, llm, store)
    actions = [s["action"] for s in r["trace"]]
    assert actions == ["read_asset", "check_rules", "finish"]


# ---- 未知素材：read_asset 失败 -> error，而非无限循环 ----
def test_unknown_asset_returns_error(store, llm):
    r = process_asset("NOPE", DATE, llm, store)
    assert r["review_status"] == "error"
    assert r["error"]
    assert r["unfinished"] is False


# ---- run()：多素材 + 共享 store 幂等 ----
def test_run_multiple_assets(store, llm):
    results = run(["M02", "M03", "M04"], DATE, llm, store)
    statuses = [r["review_status"] for r in results]
    assert statuses == ["approved", "need_more_info", "blocked"]


def test_run_duplicate_reuses_draft(store, llm):
    results = run(["M01", "M01"], DATE, llm, store)
    assert results[0]["draft"]["draft_id"] == results[1]["draft"]["draft_id"]
    assert results[1]["draft"]["duplicate"] is True
    assert store["drafts"].count() == 1


# ---- 「仅保存草稿、不接真实发布」约束 ----
def test_all_results_never_published(store, llm):
    results = run([a["asset_id"] for a in store["assets"]], DATE, llm, store)
    for r in results:
        assert r["draft_status"] != "published"
        if r.get("draft"):
            assert r["draft"]["status"] == "draft"
            assert r["draft"]["status"] != "published"
    # 注册表中不存在任何 publish 工具
    assert "publish" not in TOOLS


# ---- 交互模式：待确认项 y/n ----
def test_interactive_reject_skips_save(store, llm):
    r = process_asset("M01", DATE, llm, store, interactive=True, confirm_fn=lambda *a: False)
    assert r["review_status"] == "pending_confirmation"
    assert r["draft_status"] == "none"
    assert any("未确认" in p for p in r["pending_confirmations"])


def test_interactive_accept_saves_draft(store, llm):
    r = process_asset("M01", DATE, llm, store, interactive=True, confirm_fn=lambda *a: True)
    assert r["review_status"] == "approved"
    assert r["draft_status"] == "drafted"


# ---- 护栏：deadline 分支（真正的超时拦截，而非 hard_constraint 分支）----
def test_guardrail_deadline_branch_blocks(store):
    asset = {
        "asset_id": "X",
        "publish_requirement": {
            "preferred_time": "18:00",
            "hard_constraint": False,  # 关键：不含 hard_constraint，避免走第一分支
            "hard_deadline": "19:00",
        },
    }
    state = {"asset": asset, "phase": "save_draft"}
    a = apply_guardrail(Action("save_draft", {"slot": "20:00"}, "超 deadline", "llm:x"), state)
    assert a.name == "finish"
    assert a.source == "guardrail"
    assert state["review_status"] == "blocked"
    assert any("截止" in p for p in state["pending_confirmations"])


def test_guardrail_deadline_boundary_inclusive(store):
    asset = {
        "asset_id": "X",
        "publish_requirement": {
            "preferred_time": "19:00",
            "hard_constraint": False,
            "hard_deadline": "19:00",
        },
    }
    state = {"asset": asset, "phase": "save_draft"}
    # 语义 B：含 hard_deadline 即硬性；slot 等于 preferred（未改时段）且未超 deadline → 放行
    a = apply_guardrail(Action("save_draft", {"slot": "19:00"}, "等于 preferred 且等于 deadline", "llm:x"), state)
    assert a.name == "save_draft"


# ---- 步数上限：立即 finish 不误判为 unfinished ----
class _FinishNowLLM(LLM):
    def decide(self, state, observation):
        return Action("finish", {}, "直接结束", "test")


def test_finish_immediately_not_unfinished(store):
    r = process_asset("M01", DATE, _FinishNowLLM(), store)
    assert r["unfinished"] is False
    assert r["tool_calls"] == 0


def test_max_tool_calls_reason_explicit(store):
    class _LoopLLM(LLM):
        def decide(self, state, observation):
            return Action("read_asset", {"asset_id": state["asset_id"]}, "死循环", "test")

    r = process_asset("M01", DATE, _LoopLLM(), store)
    assert r["unfinished"] is True
    assert r["review_status"] == "unfinished"
    assert r["tool_calls"] == MAX_TOOL_CALLS
    assert str(MAX_TOOL_CALLS) in r["unfinished_reason"]
