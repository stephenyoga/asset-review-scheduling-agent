from .base import Action, LLM
from .mock import MockLLM
from .openai_compat import OpenAICompatLLM


def create_llm(provider: str = "mock", **kwargs) -> LLM:
    """决策器工厂：provider=mock 返回离线 Mock，否则返回 OpenAI 兼容实现。"""
    if provider == "mock":
        return MockLLM()
    return OpenAICompatLLM(provider=provider, **kwargs)


__all__ = ["Action", "LLM", "MockLLM", "OpenAICompatLLM", "create_llm"]
