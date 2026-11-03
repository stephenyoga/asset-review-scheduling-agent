"""工具层单元测试：覆盖各工具的边界、异常与「仅草稿」约束。

与 tests/test_agent.py 的 6 个验收点不重复，这里聚焦工具本身的
输入校验、返回结构与失败模式。
"""
from src.tools.registry import TOOLS, FINISH, execute
from src.tools.read_asset import read_asset, REQUIRED_FIELDS
from src.tools.check_rules import check_rules
from src.tools.query_slots import query_slots
from src.tools.save_draft import save_draft
from src.tools.utils import get_path, matches, time_to_minutes


# ---- get_path / matches ----
def test_get_path_nested_and_missing():
    obj = {"a": {"b": 1}}
    assert get_path(obj, "a.b") == 1
    assert get_path(obj, "a.c") is None
    assert get_path(obj, "x") is None


def test_matches_in_contains_gt():
    assert matches("gambling", {"in": ["gambling", "sensitive"]}) is True
    assert matches(["banned_word"], {"contains": "banned_word"}) is True
    assert matches(90, {"gt": 60}) is True
    assert matches(30, {"gt": 60}) is False
    # contains 仅对 list 生效
    assert matches("banned_word", {"contains": "banned_word"}) is False


# ---- read_asset ----
def test_read_asset_required_fields_definition():
    assert "owner" in REQUIRED_FIELDS
    assert "publish_requirement.preferred_time" in REQUIRED_FIELDS


def test_read_asset_nonexistent(store):
    r = read_asset({"asset_id": "NOPE"}, store)
    assert r["ok"] is False
    assert "不存在" in r["error"]


def test_read_asset_all_present(store):
    r = read_asset({"asset_id": "M02"}, store)
    assert r["ok"] is True
    assert r["missing_fields"] == []


def test_read_asset_missing_owner(store):
    r = read_asset({"asset_id": "M03"}, store)
    assert r["ok"] is True
    assert r["missing_fields"] == ["owner"]


# ---- check_rules ----
def test_check_rules_no_asset(store):
    r = check_rules({}, store)
    assert r["ok"] is False


def test_check_rules_high_risk_blocks(store):
    asset = next(a for a in store["assets"] if a["asset_id"] == "M04")
    r = check_rules({"asset": asset}, store)
    assert r["ok"] is True
    assert r["passed"] is False
    assert len([x for x in r["risks"] if x["level"] == "high"]) == 2


def test_check_rules_gt_duration(store):
    asset = {
        "asset_id": "X",
        "category": "education",
        "duration_min": 90,
        "risk_flags": [],
    }
    r = check_rules({"asset": asset}, store)
    assert r["passed"] is False
    assert any("时长" in x["reason"] for x in r["risks"])


# ---- query_slots ----
def test_query_slots_no_filter(store):
    r = query_slots({"date": "2026-11-04"}, store)
    assert r["ok"] is True
    assert len(r["slots"]) == 12


def test_query_slots_range_filter_inclusive(store):
    r = query_slots({"date": "2026-11-04", "start": "10:00", "end": "12:00"}, store)
    times = [s["time"] for s in r["slots"]]
    assert times == ["10:00", "11:00", "12:00"]


def test_query_slots_default_date(store):
    r = query_slots({}, store)
    assert r["date"] == store["schedule"]["date"]


# ---- save_draft ----
def test_save_draft_missing_args(store):
    r = save_draft({}, store)
    assert r["ok"] is False


def test_save_draft_invalid_format(store):
    r = save_draft({"asset_id": "X", "slot": "abc"}, store)
    assert r["ok"] is False
    assert "非法时段" in r["error"]


def test_save_draft_occupied(store):
    r = save_draft({"asset_id": "X", "slot": "18:00"}, store)
    assert r["ok"] is False
    assert "占用" in r["error"]


def test_save_draft_faulty(store):
    r = save_draft({"asset_id": "M07", "slot": "20:00"}, store)
    assert r["ok"] is False
    assert "faulty" in r["error"]


def test_save_draft_idempotent(store):
    r1 = save_draft({"asset_id": "M02", "slot": "10:00"}, store)
    r2 = save_draft({"asset_id": "M02", "slot": "10:00"}, store)
    assert r1["ok"] is True
    assert r2["ok"] is True
    assert r2["duplicate"] is True
    assert r1["draft_id"] == r2["draft_id"]
    assert store["drafts"].count() == 1


def test_save_draft_never_published(store):
    # 草稿状态恒为 draft，绝不出现 published
    r = save_draft({"asset_id": "M02", "slot": "10:00"}, store)
    assert r["ok"] is True
    assert "draft_id" in r
    # 直接从存储层确认状态字段
    d = store["drafts"].get("M02", "10:00")
    assert d["status"] == "draft"
    assert d["status"] != "published"


# ---- 工具注册表：无 publish 工具，仅 4 个只读/草稿工具 + finish ----
def test_registry_has_no_publish_tool():
    assert "publish" not in TOOLS
    assert "published" not in TOOLS
    assert set(TOOLS.keys()) == {
        "read_asset",
        "check_rules",
        "query_slots",
        "save_draft",
    }
    assert FINISH == "finish"


def test_execute_unknown_tool(store):
    r = execute("publish", {"asset_id": "M01"}, store)
    assert r["ok"] is False
    assert "未知工具" in r["error"]


def test_execute_tool_exception_wrapped(store, monkeypatch):
    import src.tools.registry as registry

    def boom(args, store):
        raise RuntimeError("boom")

    monkeypatch.setitem(registry.TOOLS, "boom_tool", boom)
    r = execute("boom_tool", {}, store)
    assert r["ok"] is False
    assert "异常" in r["error"]
    assert "boom" in r["error"]
