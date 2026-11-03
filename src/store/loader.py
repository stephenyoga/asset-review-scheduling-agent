"""合成数据加载：素材、审核规则、已有排期。

数据均为本地 JSON，评审可离线复现；无任何外部依赖。
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load(name: str):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def load_assets():
    return _load("assets.json")


def load_rules():
    return _load("rules.json")


def load_schedule():
    return _load("schedule.json")
