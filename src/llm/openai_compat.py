"""OpenAI 兼容协议决策器：覆盖 DeepSeek / Qwen / Claude。

三者均走 OpenAI 兼容的 /chat/completions 端点，仅 base_url / model / api_key 不同。
- DeepSeek: https://api.deepseek.com
- Qwen:     https://dashscope.aliyuncs.com/compatible-mode/v1
- Claude:   https://api.anthropic.com/v1（Anthropic 的 OpenAI 兼容端点）

结构化输出不可靠时：解析失败重试，仍失败则降级到 Mock 决策器并标注来源。
核心代码仅用标准库 urllib，无第三方依赖。
"""
import json
import re
import urllib.request
from typing import Optional

from .base import Action, LLM
from .mock import MockLLM
from ..tools.registry import TOOLS, FINISH

PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "claude": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-6",
    },
}

SYSTEM_PROMPT = """你是一个素材审核与发布排期助手，通过调用工具为素材生成可确认的发布排期。

可用工具（只能调用这些）：
1. read_asset(asset_id) —— 读取素材元数据，返回缺失字段
2. check_rules(asset) —— 检查审核规则风险
3. query_slots(date, start, end) —— 查询时段占用
4. save_draft(asset_id, slot, pending_confirmations) —— 保存草稿
5. finish —— 结束

硬性规则（必须严格遵守）：
- 未经用户同意，不得擅自改变硬性发布要求（publish_requirement.hard_constraint=true 或存在 hard_deadline）。
- 硬性要求时段被占用时，必须阻断并请求确认，绝不擅自更换时段。
- 信息缺失或存在高风险时，不得排期。
- 只保存草稿，绝不发布；保存失败必须如实上报，绝不虚报成功。

每次只输出一个动作，严格输出 JSON（不要输出其他文字）：
{"thought": "决策依据", "action": "工具名", "action_input": {...}}"""


def _extract_json(text: str):
    text = (text or "").strip()
    fence = re.match(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass
    return None


def _summarize_state(state: dict) -> str:
    keys = [
        "asset_id",
        "phase",
        "review_status",
        "missing_fields",
        "risks",
        "suggested_slot",
        "pending_confirmations",
        "draft_status",
        "draft_error",
    ]
    summary = {k: state.get(k) for k in keys if k in state}
    asset = state.get("asset")
    if asset:
        summary["asset"] = {
            "asset_id": asset.get("asset_id"),
            "category": asset.get("category"),
            "publish_requirement": asset.get("publish_requirement"),
        }
    return json.dumps(summary, ensure_ascii=False)


class OpenAICompatLLM(LLM):
    def __init__(
        self,
        provider: str,
        api_key: str,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 2,
    ):
        cfg = PROVIDERS.get(provider, {})
        self.provider = provider
        self.api_key = api_key
        self.base_url = (base_url or cfg.get("base_url", "")).rstrip("/")
        self.model = model or cfg.get("model", "")
        self.max_retries = max_retries
        self._fallback = MockLLM()

    def decide(self, state: dict, observation: Optional[dict]) -> Action:
        messages = self._build_messages(state, observation)
        last_error = None
        for _ in range(self.max_retries + 1):
            try:
                raw = self._chat(messages)
                action = self._parse_action(raw)
                if action is not None:
                    return action
                last_error = "模型输出无法解析为合法动作"
            except Exception as exc:  # 网络/接口异常
                last_error = str(exc)
        # 降级：解析/调用失败，回退 Mock，并标注来源
        action = self._fallback.decide(state, observation)
        action.source = "mock(fallback)"
        action.thought = f"[降级] {last_error}；改用 Mock 决策"
        return action

    def _build_messages(self, state: dict, observation: Optional[dict]) -> list:
        user = {
            "当前状态": _summarize_state(state),
            "上一步工具返回": observation,
        }
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ]

    def _parse_action(self, raw: str) -> Optional[Action]:
        data = _extract_json(raw)
        if not data:
            return None
        name = data.get("action")
        if name != FINISH and name not in TOOLS:
            return None
        action = Action.from_dict(data)
        action.source = f"llm:{self.provider}"
        return action

    def _chat(self, messages: list) -> str:
        payload = json.dumps(
            {"model": self.model, "messages": messages, "temperature": 0}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
