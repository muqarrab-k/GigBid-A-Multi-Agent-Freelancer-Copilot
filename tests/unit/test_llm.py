import socket
from typing import Any

import pytest
from langchain_core.runnables import RunnableWithFallbacks
from langchain_openai import ChatOpenAI

from agent.config import NODE_NAMES, ConfigError, get_config
from agent.handoffs import JobSpec
from agent.llm import get_model


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network call in unit test")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "TOGETHER_API_KEY"):
        monkeypatch.setenv(key, "test-key")


def primary(model: Any) -> ChatOpenAI:
    if isinstance(model, RunnableWithFallbacks):
        model = model.runnable
    assert isinstance(model, ChatOpenAI)
    return model


@pytest.mark.parametrize("node", NODE_NAMES)
def test_each_node_resolves_from_config(node: str, keys: None) -> None:
    spec = get_config().profile.node(node)
    chat = primary(get_model(node))
    assert chat.model_name == spec.model
    assert chat.openai_api_base == spec.base_url
    assert chat.temperature == spec.temperature


def test_cheap_node_gets_fallback(keys: None) -> None:
    spec = get_config().profile.node("scout")
    assert spec.fallback is not None
    model = get_model("scout")
    assert isinstance(model, RunnableWithFallbacks)
    backup = model.fallbacks[0]
    assert isinstance(backup, ChatOpenAI)
    assert backup.model_name == spec.fallback.model


def test_fallback_skipped_without_key() -> None:
    model = get_model("scout")
    assert isinstance(model, ChatOpenAI)


def test_hosted_node_without_key_fails_clearly() -> None:
    with pytest.raises(ConfigError, match="GROQ_API_KEY"):
        get_model("writer")


def test_ollama_base_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")
    assert primary(get_model("analyst")).openai_api_base == "http://ollama:11434/v1"


def test_paid_profile_switch(monkeypatch: pytest.MonkeyPatch, keys: None) -> None:
    monkeypatch.setenv("MODEL_PROFILE", "paid")
    get_config.cache_clear()
    paid = get_config().models.profiles["paid"].writer
    assert primary(get_model("writer")).model_name == paid.model


def test_unknown_node() -> None:
    with pytest.raises(ConfigError, match="unknown node"):
        get_model("janitor")


def test_structured_output_works_through_fallback(keys: None) -> None:
    model = get_model("analyst")
    assert model.with_structured_output(JobSpec) is not None  # type: ignore[attr-defined]
