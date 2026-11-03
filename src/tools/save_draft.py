"""工具：保存排期草稿。仅草稿，不接真实发布。"""
from .utils import time_to_minutes


def save_draft(args: dict, store: dict) -> dict:
    asset_id = args.get("asset_id")
    slot = args.get("slot")
    pending = args.get("pending_confirmations", [])

    if not asset_id or not slot:
        return {"ok": False, "error": "缺少 asset_id 或 slot"}

    if time_to_minutes(slot) is None:
        return {"ok": False, "error": f"非法时段格式：{slot}"}

    return store["drafts"].save(asset_id, slot, pending)
