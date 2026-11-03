"""草稿存储：仅保存草稿（draft），不接真实发布。

关键设计：
- 幂等去重：唯一键 (asset_id, slot)，相同请求重复保存只产生一份草稿。
- 保存失败：目标时段为 faulty（查询时表现为 free，保存时才暴露的隐藏故障）
  或 occupied 时，明确返回失败，绝不虚报成功。
"""
import itertools
from typing import Any, Dict, Optional


class DraftStore:
    def __init__(self, schedule: Dict[str, Any]):
        self._schedule = schedule
        self._drafts: Dict[tuple, Dict[str, Any]] = {}
        self._counter = itertools.count(1)

    def _find_slot(self, slot: str) -> Optional[Dict[str, Any]]:
        for s in self._schedule.get("slots", []):
            if s["time"] == slot:
                return s
        return None

    def save(
        self,
        asset_id: str,
        slot: str,
        pending_confirmations: Optional[list] = None,
    ) -> Dict[str, Any]:
        pending = pending_confirmations or []
        s = self._find_slot(slot)

        if s is None:
            return {"ok": False, "error": f"时段 {slot} 不在排期内，草稿保存失败"}
        if s.get("faulty"):
            return {"ok": False, "error": f"时段 {slot} 存储异常（faulty slot），草稿保存失败"}
        if s.get("status") == "occupied":
            return {"ok": False, "error": f"时段 {slot} 已被占用，草稿保存失败"}

        key = (asset_id, slot)
        if key in self._drafts:
            d = self._drafts[key]
            return {
                "ok": True,
                "duplicate": True,
                "draft_id": d["draft_id"],
                "message": "重复提交，返回已存在草稿，不新建",
            }

        draft_id = f"D-{next(self._counter):04d}"
        draft = {
            "draft_id": draft_id,
            "asset_id": asset_id,
            "slot": slot,
            "status": "draft",
            "pending_confirmations": pending,
        }
        self._drafts[key] = draft
        return {"ok": True, "duplicate": False, "draft_id": draft_id, "message": "草稿保存成功"}

    def count(self) -> int:
        return len(self._drafts)

    def get(self, asset_id: str, slot: str) -> Optional[Dict[str, Any]]:
        return self._drafts.get((asset_id, slot))
