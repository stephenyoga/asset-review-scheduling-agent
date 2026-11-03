import pytest

from src.llm import create_llm
from src.store import build_store


@pytest.fixture
def store():
    return build_store()


@pytest.fixture
def llm():
    return create_llm("mock")
