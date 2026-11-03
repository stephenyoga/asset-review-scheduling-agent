"""决策器单元测试：MockLLM 决策表 + OpenAICompat 多厂商适配与降级异常处理。"""
from src.llm import create_llm, MockLLM, OpenAICompatLLM
from src.llm.base import Action
from src.llm.openai_compat import (
    PROVIDERS,
    SYSTEM_PROMPT,
    _extract_json,
    _summarize_state,
)


# ---- MockLLM：辅助函数与决策表 ----
def test_mock_slot_status():
    slots = [
        {"time": "18:00", "status": "occupied"},
        {"time": "19:00", "status": "free"},
    ]
    assert MockLLM._slot_status(slots, "18:00") == "occupied"
    assert MockLLM._slot_status(slots, "19:00") == "free"
    assert MockLLM._slot_status(slots, "09:00") == "unknown"


def test_mock_find_free_respects_deadline():
    slots = [
        {"time": "18:00", "status": "occupied"},
        {"time": "19:00", "status": "free"},
        {"time": "20:00", "status": "free"},
    ]
    # deadline 19:00 时，20:00 被排除，只返回 19:00
    assert MockLLM._find_free(slots, "18:00", "19:00") == "19:00"


def test_mock_find_free_skips_occupied():
    slots = [
        {"time": "18:00", "status": "occupied"},
        {"time": "19:00", "status": "occupied"},
        {"time": "20:00", "status": "free"},
    ]
    assert MockLLM._find_free(slots, "18:00", None) == "20:00"


def test_mock_decide_start_reads_asset():
    llm = MockLLM()
    a = llm.decide({"asset_id": "M01", "phase": "start"}, None)
    assert a.name == "read_asset"
    assert a.args["asset_id"] == "M01"
    assert a.source == "mock"


def test_mock_after_read_missing_sets_need_more_info():
    llm = MockLLM()
    state = {"phase": "read_asset", "asset_id": "M03"}
    obs = {"ok": True, "asset": {"asset_id": "M03"}, "missing_fields": ["owner"]}
    llm._consume(state, obs)
    assert state["review_status"] == "need_more_info"
    assert state["phase"] == "done"
    assert llm._next(state).name == "finish"


def test_mock_after_check_high_risk_blocks():
    llm = MockLLM()
    state = {"phase": "check_rules"}
    obs = {"ok": True, "risks": [{"level": "high"}], "passed": False}
    llm._consume(state, obs)
    assert state["review_status"] == "blocked"
    assert state["phase"] == "done"


def test_mock_after_check_pass_goes_to_slots():
    llm = MockLLM()
    state = {"phase": "check_rules"}
    obs = {"ok": True, "risks": [], "passed": True}
    llm._consume(state, obs)
    assert state["review_status"] == "approved"
    assert state["phase"] == "query_slots"


# ---- OpenAI 兼容：JSON 提取与动作解析 ----
def test_extract_json_variants():
    assert _extract_json('{"action": "finish"}') == {"action": "finish"}
    assert _extract_json('```json\n{"action": "finish"}\n```') == {"action": "finish"}
    assert _extract_json('前缀 {"action": "finish"} 后缀') == {"action": "finish"}
    assert _extract_json("不是 JSON") is None


def test_parse_action_rejects_unknown_tool():
    llm = OpenAICompatLLM("deepseek", api_key="k")
    assert llm._parse_action('{"action": "publish", "action_input": {}}') is None
    assert llm._parse_action('{"action": "finish"}') is not None


def test_parse_action_sets_source():
    llm = OpenAICompatLLM("qwen", api_key="k")
    a = llm._parse_action('{"action": "read_asset", "action_input": {"asset_id": "M01"}}')
    assert a.name == "read_asset"
    assert a.source == "llm:qwen"


# ---- 多厂商适配：base_url / model 覆盖 ----
def test_providers_config():
    assert PROVIDERS["deepseek"]["base_url"] == "https://api.deepseek.com"
    assert PROVIDERS["qwen"]["base_url"].endswith("/compatible-mode/v1")
    assert PROVIDERS["claude"]["base_url"] == "https://api.anthropic.com/v1"
    assert PROVIDERS["deepseek"]["model"] == "deepseek-chat"


def test_openai_compat_constructor_override():
    llm = OpenAICompatLLM(
        "deepseek", api_key="k", base_url="https://custom.example/v1", model="custom-model"
    )
    assert llm.base_url == "https://custom.example/v1"
    assert llm.model == "custom-model"


def test_create_llm_types():
    assert isinstance(create_llm("mock"), MockLLM)
    assert isinstance(create_llm("deepseek", api_key="k"), OpenAICompatLLM)


# ---- 降级与异常处理 ----
def test_openai_fallback_on_unparseable_output(monkeypatch):
    llm = OpenAICompatLLM("deepseek", api_key="k", max_retries=1)

    def fake_chat(messages):
        return "抱歉，我无法输出 JSON"

    monkeypatch.setattr(llm, "_chat", fake_chat)
    a = llm.decide({"asset_id": "M01", "phase": "start"}, None)
    assert a.source == "mock(fallback)"
    assert a.name == "read_asset"  # 降级到 Mock 决策器


def test_openai_fallback_on_network_error(monkeypatch):
    llm = OpenAICompatLLM("qwen", api_key="k", max_retries=1)

    def boom(messages):
        raise OSError("connection reset")

    monkeypatch.setattr(llm, "_chat", boom)
    a = llm.decide({"asset_id": "M01", "phase": "start"}, None)
    assert a.source == "mock(fallback)"


def test_openai_chat_payload_shape(monkeypatch):
    llm = OpenAICompatLLM("claude", api_key="k")

    captured = {}

    def fake_urlopen(req, timeout):
        import json as _json

        body = _json.loads(req.data.decode("utf-8"))
        captured["url"] = req.full_url
        captured["model"] = body["model"]
        captured["auth"] = req.get_header("Authorization")
        captured["messages"] = body["messages"]
        assert req.get_header("Content-type") == "application/json"

        class Resp:
            def read(self):
                return _json.dumps(
                    {"choices": [{"message": {"content": '{"action": "finish"}'}}]}
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return Resp()

    monkeypatch.setattr("src.llm.openai_compat.urllib.request.urlopen", fake_urlopen)
    a = llm.decide({"asset_id": "M01", "phase": "start"}, None)
    assert captured["url"] == "https://api.anthropic.com/v1/chat/completions"
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["auth"] == "Bearer k"
    assert captured["messages"][0]["role"] == "system"
    assert a.name == "finish"
