"""构造工具共享的运行上下文（store）。

store 是一个普通 dict，工具层通过键名读取数据，避免强耦合具体类。
"""
from .loader import load_assets, load_rules, load_schedule
from .draft_store import DraftStore


def build_store() -> dict:
    schedule = load_schedule()
    return {
        "assets": load_assets(),
        "rules": load_rules(),
        "schedule": schedule,
        "drafts": DraftStore(schedule),
    }


def find_asset(assets: list, asset_id: str):
    for a in assets:
        if a.get("asset_id") == asset_id:
            return a
    return None
