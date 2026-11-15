"""A scripted MCP layer for conversation and degraded-mode tests."""

from typing import Any

from agent.mcp_client import MarketplaceDown

CLIENT_MSG = {"message_id": "m1", "thread_id": "t1", "sender": "client", "created_at": "2024-08-05T10:00:00Z"}


class FakeLayer:
    def __init__(self, client_text: str = "Can you start next week?", down: bool = False,
                 user: str = "noor") -> None:
        self.user, self.down, self.client_text = user, down, client_text
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.sent: dict[str, dict[str, Any]] = {}

    async def discover(self) -> None:
        return None

    async def server_status(self) -> dict[str, str]:
        return {"marketplace": "up", "portfolio": "up", "workspace": "up"}

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, args))
        if self.down and name not in ("free_slots",):
            return MarketplaceDown(server="marketplace", detail="gigsim 503").model_dump()
        if name == "list_threads":
            return {"ok": True, "items": [{"thread_id": "t1", "proposal_id": "pr_1", "job_id": "j1"}]}
        if name == "list_messages":
            msg = {**CLIENT_MSG, "untrusted_text": {"source": "client_message", "text": self.client_text}}
            mine = [{"message_id": k, "thread_id": "t1", "sender": "freelancer", "created_at": None, "text": v["text"]}
                    for k, v in self.sent.items()]
            return {"ok": True, "items": [msg, *mine]}
        if name == "free_slots":
            return {"ok": True, "timezone": "Asia/Karachi", "slots": [
                {"start": f"2024-08-0{d}T10:00:00+05:00", "end": f"2024-08-0{d}T10:30:00+05:00"} for d in (6, 7, 8)]}
        if name == "send_message":
            if args.get("dry_run"):
                return {"ok": True, "dry_run": True, "policy_check": {"passed": True}}
            key = args["idempotency_key"]
            # same key, same message: like gigsim
            self.sent.setdefault(key, {"text": args["text"]})
            return {"ok": True, "message": {"message_id": key, "thread_id": "t1", "sender": "freelancer"}}
        if name == "get_connects_balance":
            return {"ok": True, "connects": {"balance": 80}}
        return {"ok": True, "items": []}
