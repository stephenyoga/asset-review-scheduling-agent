"""6 个验收点集成测试 + 护栏 + 步数上限。"""
from src.agent import apply_guardrail, process_asset, MAX_TOOL_CALLS
from src.llm.base import Action, LLM

DATE = "2026-11-04"


def _find(store, asset_id):
    for a in store["assets"]:
        if a["asset_id"] == asset_id:
            return a
    raise AssertionError(f"素材 {asset_id} 不存在")


# ---- 验收点① 正常排期 ----
def test_normal_schedule(store, llm):
    r = process_asset("M02", DATE, llm, store)
    assert r["review_status"] == "approved"
    assert r["suggested_slot"] == "10:00"
    assert r["draft_status"] == "drafted"
    assert r["draft"]["status"] == "draft"


# ---- 验收点② 素材信息缺失 ----
def test_missing_info(store, llm):
    r = process_asset("M03", DATE, llm, store)
    assert r["review_status"] == "need_more_info"
    assert "owner" in r["missing_fields"]
    assert r["draft_status"] == "none"


# ---- 验收点③ 规则风险 ----
def test_rule_risk(store, llm):
    r = process_asset("M04", DATE, llm, store)
    assert r["review_status"] == "blocked"
    assert len(r["risk_reasons"]) >= 2
    assert r["draft_status"] == "none"


# ---- 验收点④ 时段冲突（软性：建议替代 + 待确认）----
def test_slot_conflict_soft(store, llm):
    r = process_asset("M01", DATE, llm, store)
    assert r["review_status"] == "approved"
    assert r["suggested_slot"] == "19:00"
    assert any("19:00" in p for p in r["pending_confirmations"])
    assert r["draft_status"] == "drafted"


# ---- 验收点④ 时段冲突（硬性：阻断 + 请求确认，不擅自改）----
def test_slot_conflict_hard(store, llm):
    r = process_asset("M05", DATE, llm, store)
    assert r["review_status"] == "blocked"
    assert r["draft_status"] == "none"
    assert any("未擅自变更" in p for p in r["pending_confirmations"])


# ---- 验收点⑤ 重复提交：只产一份草稿 ----
def test_duplicate_submission(store, llm):
    r1 = process_asset("M01", DATE, llm, store)
    r2 = process_asset("M01", DATE, llm, store)
    assert r1["draft"]["draft_id"] == r2["draft"]["draft_id"]
    assert r2["draft"]["duplicate"] is True
    assert store["drafts"].count() == 1


# ---- 验收点⑥ 保存失败：明确返回失败，不虚报 ----
def test_save_fail(store, llm):
    r = process_asset("M07", DATE, llm, store)
    assert r["draft_status"] == "save_failed"
    assert r["draft_error"]  # 非空错误信息
    assert store["drafts"].count() == 0


# ---- 后置护栏：拦截越权修改硬性要求 ----
def test_guardrail_blocks_hard_override(store):
    asset = _find(store, "M05")
    state = {"asset": asset, "phase": "save_draft"}
    action = Action(
        "save_draft",
        {"asset_id": "M05", "slot": "19:00", "pending_confirmations": []},
        "试图擅自把硬性 18:00 改为 19:00",
        "llm:test",
    )
    result = apply_guardrail(action, state)
    assert result.name == "finish"
    assert result.source == "guardrail"
    assert state["review_status"] == "blocked"


def test_guardrail_blocks_deadline_override(store):
    asset = _find(store, "M05")
    state = {"asset": asset, "phase": "save_draft"}
    action = Action(
        "save_draft",
        {"asset_id": "M05", "slot": "20:00", "pending_confirmations": []},
        "试图超出硬性截止 19:00",
        "llm:test",
    )
    result = apply_guardrail(action, state)
    assert result.name == "finish"
    assert state["review_status"] == "blocked"


# ---- 步数上限：达到上限返回明确未完成 ----
class _LoopLLM(LLM):
    def decide(self, state, observation):
        return Action("read_asset", {"asset_id": state["asset_id"]}, "无限循环", "test")


def test_max_tool_calls(store):
    r = process_asset("M01", DATE, _LoopLLM(), store)
    assert r["unfinished"] is True
    assert r["review_status"] == "unfinished"
    assert r["tool_calls"] == MAX_TOOL_CALLS
    assert "上限" in r["unfinished_reason"]
