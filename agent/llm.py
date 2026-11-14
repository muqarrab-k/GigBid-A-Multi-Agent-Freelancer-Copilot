import logging
import os

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agent.config import ConfigError, ModelSpec, Settings, get_config

log = logging.getLogger(__name__)

ChatModel = Runnable[LanguageModelInput, BaseMessage]


def build_chat(spec: ModelSpec, settings: Settings) -> ChatOpenAI:
    """One OpenAI-compatible client per spec."""
    provider = settings.models.providers[spec.provider]

    base_url = spec.base_url
    if provider.base_url_env and os.getenv(provider.base_url_env):
        base_url = os.environ[provider.base_url_env]

    # local servers ignore keys
    api_key = "not-needed"
    if provider.api_key_env:
        api_key = os.getenv(provider.api_key_env, "")
        if not api_key:
            raise ConfigError(f"{provider.api_key_env} is not set (provider '{spec.provider}')")

    extra = {"reasoning_effort": spec.reasoning_effort} if spec.reasoning_effort else {}
    return ChatOpenAI(
        model=spec.model,
        base_url=base_url,
        api_key=SecretStr(api_key),
        temperature=spec.temperature,
        timeout=settings.models.request_timeout_s,
        max_retries=settings.models.max_retries,
        **extra,
    )


def get_model(node: str, settings: Settings | None = None) -> ChatModel:
    """Chat model for a node, with fallback if configured."""
    settings = settings or get_config()
    spec = settings.profile.node(node)
    primary = build_chat(spec, settings)
    if spec.fallback is None:
        return primary

    try:
        backup = build_chat(spec.fallback, settings)
    except ConfigError as err:
        log.warning("no fallback for %s: %s", node, err)
        return primary
    return primary.with_fallbacks([backup])
