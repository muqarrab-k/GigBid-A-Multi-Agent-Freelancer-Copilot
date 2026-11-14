# ADR 0001: Foundation — one LLM client, config-driven models

- Status: accepted (2026-11-14)
- All chat models go through `langchain_openai.ChatOpenAI` pointed at a `base_url`, because Ollama (`/v1`), Groq, OpenRouter and Together all expose the OpenAI-compatible API. One client means one code path to test, trace and add fallbacks to.
- Every node's provider, model, base URL and temperature live in `agent/config.yaml` under an `open` (required) and `paid` (optional) profile. Code only asks `get_model("writer")`; no model names are in Python.
- Cheap nodes run a small local Qwen3 with a hosted fallback; writer, critic and liaison use a hosted gpt-oss-120b. Swapping a model for evaluation is a YAML edit or `MODEL_PROFILE=paid`.
- Budgets, thresholds and bidding rules sit in the same file, so the expected GigSim policy update should be a config change, not a code change.
- Config is validated by Pydantic at load time, so a typo or unknown provider fails fast with a clear message instead of at the first LLM call.
- Trade-off: provider-specific features (native tool formats, Anthropic caching) are not used unless exposed through the OpenAI-compatible API.
