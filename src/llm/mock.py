"""离线 Mock 决策器：用「状态机 + 规则」模拟 LLM 的 ReAct 决策。

动作选择严格由工具返回驱动，不同结果走向不同分支，满足「根据工具结果调整动作」：
- read_asset 缺字段 -> need_more_info，不排期
- check_rules 高风险 -> blocked，阻断
- query_slots 时段 occupied + 软性 -> 建议替代时段 + 待确认
- query_slots 时段 occupied + 硬性 -> 阻断 + 请求确认，不擅自改
- save_draft 重复 -> 复用已有草稿；失败 -> 如实上报 save_failed
"""
from typing import Optional

from .base import Action, LLM
from ..policy import is_hard
from ..tools.utils import time_to_minutes


class MockLLM(LLM):
    def decide(self, state: dict, observation: Optional[dict]) -> Action:
        if observation is not None:
            self._consume(state, observation)
        return self._next(state)

    # ---- 消费观察，更新阶段 ----
    def _consume(self, state: dict, obs: dict) -> None:
        phase = state.get("phase")
        if phase == "read_asset":
            self._after_read(state, obs)
        elif phase == "check_rules":
            self._after_check(state, obs)
        elif phase == "query_slots":
            self._after_slots(state, obs)
        elif phase == "save_draft":
            self._after_save(state, obs)

    def _after_read(self, state: dict, obs: dict) -> None:
        state["asset"] = obs.get("asset")
        if not obs.get("ok"):
            state["review_status"] = "error"
            state["error"] = obs.get("error")
            state["phase"] = "done"
            return
        state["missing_fields"] = obs.get("missing_fields", [])
        if state["missing_fields"]:
            state["review_status"] = "need_more_info"
            state["phase"] = "done"
        else:
            state["phase"] = "check_rules"

    def _after_check(self, state: dict, obs: dict) -> None:
        state["risks"] = obs.get("risks", [])
        if not obs.get("passed"):
            state["review_status"] = "blocked"
            state["phase"] = "done"
        else:
            state["review_status"] = "approved"
            state["phase"] = "query_slots"

    def _after_slots(self, state: dict, obs: dict) -> None:
        slots = obs.get("slots", [])
        asset = state["asset"]
        req = asset.get("publish_requirement", {}) if asset else {}
        preferred = req.get("preferred_time")
        hard = is_hard(req)
        deadline = req.get("hard_deadline")

        pref_status = self._slot_status(slots, preferred)

        if pref_status == "free":
            state["suggested_slot"] = preferred
            state["phase"] = "save_draft"
            return

        if hard:
            state["review_status"] = "blocked"
            state["pending_confirmations"] = [
                f"硬性要求时段 {preferred} 不可用（{pref_status}），需用户确认，未擅自变更"
            ]
            state["phase"] = "done"
            return

        alt = self._find_free(slots, preferred, deadline)
        if alt:
            state["suggested_slot"] = alt
            state["pending_confirmations"] = [
                f"期望时段 {preferred} 不可用，建议改为 {alt}"
            ]
            state["phase"] = "save_draft"
        else:
            state["review_status"] = "blocked"
            state["pending_confirmations"] = [
                f"期望时段 {preferred} 不可用，且无可用替代时段"
            ]
            state["phase"] = "done"

    def _after_save(self, state: dict, obs: dict) -> None:
        if obs.get("ok"):
            state["draft"] = {
                "draft_id": obs.get("draft_id"),
                "slot": state.get("suggested_slot"),
                "status": "draft",
                "duplicate": obs.get("duplicate", False),
            }
            state["draft_status"] = "drafted"
        else:
            state["draft_status"] = "save_failed"
            state["draft_error"] = obs.get("error")
        state["phase"] = "done"

    # ---- 依据阶段产生下一动作 ----
    def _next(self, state: dict) -> Action:
        phase = state.get("phase")
        if phase == "start":
            state["phase"] = "read_asset"
            return Action("read_asset", {"asset_id": state["asset_id"]}, "读取素材信息", "mock")
        if phase == "read_asset":
            return Action("read_asset", {"asset_id": state["asset_id"]}, "读取素材信息", "mock")
        if phase == "check_rules":
            return Action("check_rules", {"asset": state["asset"]}, "检查审核规则风险", "mock")
        if phase == "query_slots":
            return Action(
                "query_slots",
                {"date": state.get("date"), "start": None, "end": None},
                "查询目标时段及邻近时段占用",
                "mock",
            )
        if phase == "save_draft":
            return Action(
                "save_draft",
                {
                    "asset_id": state["asset_id"],
                    "slot": state["suggested_slot"],
                    "pending_confirmations": state.get("pending_confirmations", []),
                },
                "保存排期草稿",
                "mock",
            )
        return Action("finish", {}, "处理完成", "mock")

    # ---- 辅助 ----
    @staticmethod
    def _slot_status(slots: list, time: str) -> str:
        for s in slots:
            if s.get("time") == time:
                return s.get("status", "unknown")
        return "unknown"

    @staticmethod
    def _find_free(slots: list, preferred: str, deadline: Optional[str]) -> Optional[str]:
        pref_min = time_to_minutes(preferred)
        dl_min = time_to_minutes(deadline) if deadline else None
        candidates = []
        for s in slots:
            if s.get("status") != "free":
                continue
            t = time_to_minutes(s.get("time"))
            if t is None or pref_min is None:
                continue
            if dl_min is not None and t > dl_min:
                continue
            # 双向搜索：按与期望时段的距离最近排序，距离相同时优先更晚
            candidates.append((abs(t - pref_min), -t, s["time"]))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]
