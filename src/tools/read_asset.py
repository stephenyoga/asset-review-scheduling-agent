"""工具：读取素材元数据，并检测必填字段缺失。"""
from .utils import get_path

# 必填字段集合（确认口径 6）：缺任一即判定「信息不足」，不能排期。
REQUIRED_FIELDS = [
    "title",
    "category",
    "owner",
    "publish_requirement.preferred_time",
]


def read_asset(args: dict, store: dict) -> dict:
    asset_id = args.get("asset_id")
    asset = None
    for a in store["assets"]:
        if a.get("asset_id") == asset_id:
            asset = a
            break

    if asset is None:
        return {"ok": False, "error": f"素材 {asset_id} 不存在"}

    missing = [f for f in REQUIRED_FIELDS if get_path(asset, f) is None]
    return {
        "ok": True,
        "asset_id": asset_id,
        "asset": asset,
        "missing_fields": missing,
    }
