"""决策器抽象：动作数据模型 + LLM 接口。

动作采用统一结构化格式，Mock 与真实 LLM 输出同构，可无缝替换。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Action:
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    thought: str = ""
    source: str = ""  # 决策来源：mock / llm:<provider> / mock(fallback)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thought": self.thought,
            "action": self.name,
            "action_input": self.args,
            "source": self.source,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Action":
        return Action(
            name=d.get("action", "finish"),
            args=d.get("action_input") or {},
            thought=d.get("thought", ""),
            source=d.get("source", ""),
        )


class LLM:
    """决策器接口：根据当前状态与上一步观察，返回下一个动作。"""

    def decide(self, state: Dict[str, Any], observation: Optional[dict]) -> Action:
        raise NotImplementedError
