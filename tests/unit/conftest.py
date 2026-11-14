from collections.abc import Iterator

import pytest

from agent.config import get_config
from agent.prompts.loader import load_prompt

ENV_KEYS = (
    "MODEL_PROFILE",
    "MARKETPLACE_MODE",
    "OLLAMA_BASE_URL",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "TOGETHER_API_KEY",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # blank beats .env
    for key in ENV_KEYS:
        monkeypatch.setenv(key, "")
    get_config.cache_clear()
    load_prompt.cache_clear()
    yield
    get_config.cache_clear()
    load_prompt.cache_clear()
