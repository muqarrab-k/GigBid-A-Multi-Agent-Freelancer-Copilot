"""Workspace MCP server: local mock calendar and email drafts."""

import argparse
import json
import random
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, ToolAnnotations
from pydantic import BaseModel, Field

from agent.config import McpUser, WorkspaceMock, get_config
from mcp_servers.common import (
    AuditLog,
    RateLimiter,
    ToolFailure,
    ToolOut,
    ToolRunner,
    Verifier,
    auth_settings,
)

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
STEP_MINUTES = 30


class Slot(BaseModel):
    start: datetime
    end: datetime


class Hold(BaseModel):
    hold_id: str
    start: datetime
    end: datetime
    title: str
    status: str = "tentative"


class EmailDraft(BaseModel):
    draft_id: str
    to: str
    subject: str
    body: str
    status: str = "draft"


class SlotsOut(ToolOut):
    timezone: str | None = None
    slots: list[Slot] = []


class HoldOut(ToolOut):
    dry_run: bool = False
    would_create: dict[str, Any] | None = None
    hold: Hold | None = None


class EmailOut(ToolOut):
    dry_run: bool = False
    would_create: dict[str, Any] | None = None
    draft: EmailDraft | None = None


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as err:
        raise ToolFailure("invalid_timezone", f"unknown timezone {name!r}") from err


class Calendar:
    """Seeded busy blocks per day plus a small runtime file of holds and drafts."""

    def __init__(self, user: McpUser, mock: WorkspaceMock, folder: Path) -> None:
        self.user, self.mock = user, mock
        self.tz = zone(user.timezone)
        self.path = folder / f"{user.tenant}.json"
        self.lock = threading.Lock()

    def load(self) -> dict[str, Any]:
        if self.path.exists():
            data: dict[str, Any] = json.loads(self.path.read_text())
            return data
        return {"holds": [], "drafts": [], "keys": {}}

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=1, default=str))

    def busy(self, day: datetime) -> list[tuple[datetime, datetime]]:
        """Seeded meetings for one local day."""
        rng = random.Random(f"{self.mock.seed}|{self.user.tenant}|{day.date()}")
        blocks = []
        for _ in range(self.mock.busy_blocks_per_day):
            hour = rng.randint(self.mock.work_start_hour, self.mock.work_end_hour - 1)
            start = day.replace(hour=hour, minute=rng.choice([0, 30]))
            blocks.append((start, start + timedelta(minutes=rng.choice([30, 60, 90]))))
        return blocks

    def taken(self, start: datetime, end: datetime, data: dict[str, Any]) -> bool:
        local = start.astimezone(self.tz)
        day = local.replace(hour=0, minute=0, second=0, microsecond=0)
        blocks = self.busy(day) + [(datetime.fromisoformat(h["start"]), datetime.fromisoformat(h["end"]))
                                   for h in data["holds"]]
        return any(start < b_end and b_start < end for b_start, b_end in blocks)

    def in_hours(self, start: datetime, end: datetime) -> bool:
        a, b = start.astimezone(self.tz), end.astimezone(self.tz)
        return (a.weekday() < 5 and a.date() == b.date() and a.hour >= self.mock.work_start_hour
                and (b.hour, b.minute) <= (self.mock.work_end_hour, 0))

    def free(self, start: datetime, end: datetime, minutes: int, limit: int) -> list[tuple[datetime, datetime]]:
        data = self.load()
        cursor = start.astimezone(self.tz)
        cursor = cursor.replace(second=0, microsecond=0)
        cursor += timedelta(minutes=(-cursor.minute) % STEP_MINUTES)
        found: list[tuple[datetime, datetime]] = []
        while cursor + timedelta(minutes=minutes) <= end and len(found) < limit:
            slot_end = cursor + timedelta(minutes=minutes)
            if self.in_hours(cursor, slot_end) and not self.taken(cursor, slot_end, data):
                found.append((cursor, slot_end))
            cursor += timedelta(minutes=STEP_MINUTES)
        return found


def build_server(folder: Path | None = None, limiter: RateLimiter | None = None,
                 audit_path: Path | None = None, port: int | None = None) -> FastMCP:
    settings = get_config()
    cfg, limits = settings.mcp, settings.mcp.limits
    folder = folder or cfg.workspace_dir
    port = port or cfg.ports["workspace"]
    rl = settings.marketplace.rate_limit
    runner = ToolRunner(cfg, limiter or RateLimiter(rl.requests_per_minute, rl.burst),
                        AuditLog(audit_path or cfg.audit_dir / "workspace.jsonl"))
    mcp = FastMCP("gigbid-workspace", instructions="Local mock calendar and email drafts. Nothing is ever sent.",
                  token_verifier=Verifier(cfg), auth=auth_settings(cfg, port), port=port)
    calendars: dict[str, Calendar] = {}

    def calendar(user: McpUser) -> Calendar:
        if user.user not in calendars:
            calendars[user.user] = Calendar(user, cfg.workspace, folder)
        return calendars[user.user]

    Key = Annotated[str, Field(min_length=8, max_length=limits.idempotency_key_max_chars,
                               pattern=r"^[A-Za-z0-9._:-]+$", description="Required. Reuse it when retrying.")]
    DryRun = Annotated[bool, Field(description="Preview only, nothing is written.")]
    Minutes = Annotated[int, Field(ge=limits.slot_min_minutes, le=limits.slot_max_minutes)]

    def aware(value: datetime, name: str) -> datetime:
        if value.tzinfo is None:
            raise ToolFailure("invalid_datetime", f"{name} needs a timezone offset, e.g. 2024-08-05T10:00:00+00:00")
        return value

    @mcp.tool(annotations=READ)
    async def free_slots(
        ctx: Context,  # type: ignore[type-arg]
        start: datetime,
        end: datetime,
        duration_minutes: Minutes,
        timezone: Annotated[str, Field(min_length=1, max_length=64, description="IANA zone for the results")],
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> Annotated[CallToolResult, SlotsOut]:
        """Free interview slots in the freelancer's working hours, shown in the given timezone."""
        args = {"start": start, "end": end, "duration_minutes": duration_minutes, "timezone": timezone}

        async def body(user: McpUser) -> SlotsOut:
            tz = zone(timezone)
            a, b = aware(start, "start"), aware(end, "end")
            if b <= a:
                raise ToolFailure("invalid_range", "end must be after start")
            if b - a > timedelta(days=limits.free_slots_max_days):
                raise ToolFailure("invalid_range", f"range longer than {limits.free_slots_max_days} days")
            found = calendar(user).free(a, b, duration_minutes, limit)
            return SlotsOut(timezone=timezone, slots=[Slot(start=s.astimezone(tz), end=e.astimezone(tz))
                                                      for s, e in found])

        return await runner.run(ctx, "free_slots", args, SlotsOut, body)

    @mcp.tool(annotations=WRITE)
    async def create_tentative_hold(
        ctx: Context,  # type: ignore[type-arg]
        slot: Slot,
        title: Annotated[str, Field(min_length=1, max_length=limits.email_subject_max_chars)],
        idempotency_key: Key,
        dry_run: DryRun = False,
    ) -> Annotated[CallToolResult, HoldOut]:
        """Put a tentative interview hold on the calendar (no invite is sent)."""
        args = {"slot": slot.model_dump(mode="json"), "title": title, "idempotency_key": idempotency_key,
                "dry_run": dry_run}

        async def body(user: McpUser) -> HoldOut:
            cal = calendar(user)
            a, b = aware(slot.start, "slot.start"), aware(slot.end, "slot.end")
            preview = {"start": a.isoformat(), "end": b.isoformat(), "title": title}
            with cal.lock:
                data = cal.load()
                if idempotency_key in data["keys"]:
                    return HoldOut.model_validate(data["keys"][idempotency_key])
                if b <= a or not cal.in_hours(a, b) or cal.taken(a, b, data):
                    raise ToolFailure("slot_unavailable", "slot is outside working hours or already taken")
                if dry_run:
                    return HoldOut(dry_run=True, would_create=preview)
                hold = Hold(hold_id=f"hold_{len(data['holds']) + 1:04d}", start=a, end=b, title=title)
                data["holds"].append(hold.model_dump(mode="json"))
                out = HoldOut(would_create=preview, hold=hold)
                data["keys"][idempotency_key] = out.model_dump(mode="json")
                cal.save(data)
                return out

        return await runner.run(ctx, "create_tentative_hold", args, HoldOut, body)

    @mcp.tool(annotations=WRITE)
    async def create_email_draft(
        ctx: Context,  # type: ignore[type-arg]
        to: Annotated[str, Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")],
        subject: Annotated[str, Field(min_length=1, max_length=limits.email_subject_max_chars)],
        body: Annotated[str, Field(min_length=1, max_length=limits.email_body_max_chars)],
        idempotency_key: Key,
        dry_run: DryRun = False,
    ) -> Annotated[CallToolResult, EmailOut]:
        """Save an email draft for the freelancer to review. Never sends."""
        args = {"to": to, "subject": subject, "body": body, "idempotency_key": idempotency_key, "dry_run": dry_run}
        preview = {"to": to, "subject": subject, "body": body}

        async def run_body(user: McpUser) -> EmailOut:
            cal = calendar(user)
            with cal.lock:
                data = cal.load()
                if idempotency_key in data["keys"]:
                    return EmailOut.model_validate(data["keys"][idempotency_key])
                if dry_run:
                    return EmailOut(dry_run=True, would_create=preview)
                draft = EmailDraft(draft_id=f"draft_{len(data['drafts']) + 1:04d}", **preview)
                data["drafts"].append(draft.model_dump())
                out = EmailOut(would_create=preview, draft=draft)
                data["keys"][idempotency_key] = out.model_dump(mode="json")
                cal.save(data)
                return out

        return await runner.run(ctx, "create_email_draft", args, EmailOut, run_body)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="GigBid workspace MCP server (local mock)")
    parser.add_argument("--http", action="store_true", help="Streamable HTTP instead of stdio")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    build_server(port=args.port).run(transport="streamable-http" if args.http else "stdio")


if __name__ == "__main__":
    main()
