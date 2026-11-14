from typing import Any

from agent.marketplace_port import Capabilities, NotConfigured

MESSAGE = (
    "live Upwork mode is not configured yet: it needs the official Upwork MCP server and OAuth "
    "(a later task). Set marketplace.mode to gigsim in agent/config.yaml."
)


class UpworkLiveAdapter:
    """Placeholder for the live Upwork adapter (drafts only)."""

    capabilities = Capabilities(marketplace="upwork", can_submit=False, drafts_only=True,
                                requires_platform_confirmation=True)

    def __init__(self, **kwargs: Any) -> None:
        raise NotConfigured(MESSAGE)
