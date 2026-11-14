import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY, persona TEXT, name TEXT, token TEXT UNIQUE,
    connects INTEGER, weekly_connects INTEGER);
CREATE TABLE clients (client_id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE client_secrets (client_id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY, client_id TEXT, status TEXT, release_at TEXT, posted_at TEXT,
    title TEXT, description TEXT, skills TEXT, budget_type TEXT, budget_max REAL,
    hourly_max REAL, data TEXT NOT NULL);
CREATE TABLE proposals (
    proposal_id TEXT PRIMARY KEY, account_id TEXT, job_id TEXT, status TEXT,
    cover_letter TEXT, bid_amount REAL, screening_answers TEXT, connects_spent INTEGER,
    created_at TEXT, submitted_at TEXT, decide_at TEXT, final_at TEXT, updated_at TEXT,
    thread_id TEXT, score REAL);
CREATE TABLE threads (
    thread_id TEXT PRIMARY KEY, account_id TEXT, job_id TEXT, client_id TEXT,
    proposal_id TEXT, created_at TEXT, followup_at TEXT);
CREATE TABLE messages (
    message_id TEXT PRIMARY KEY, thread_id TEXT, sender TEXT, text TEXT, created_at TEXT,
    intent TEXT, injected INTEGER DEFAULT 0);
CREATE TABLE events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT, type TEXT,
    payload TEXT, sim_time TEXT);
CREATE TABLE idempotency (
    account_id TEXT, key TEXT, request_hash TEXT, status_code INTEGER, body TEXT,
    PRIMARY KEY (account_id, key));
CREATE INDEX jobs_status ON jobs (status, posted_at);
CREATE INDEX proposals_due ON proposals (status, decide_at, final_at);
"""
TABLES = ["meta", "accounts", "clients", "client_secrets", "jobs", "proposals", "threads",
          "messages", "events", "idempotency"]


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


class Store:
    """Thin sqlite wrapper with one lock."""

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.lock, self.conn:
            yield self.conn

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self.transaction() as conn:
            conn.execute(sql, params)

    def recreate(self) -> None:
        with self.transaction() as conn:
            for table in TABLES:
                conn.execute(f"DROP TABLE IF EXISTS {table}")
            conn.executescript(SCHEMA)

    def meta(self, key: str) -> str:
        row = self.one("SELECT value FROM meta WHERE key = ?", (key,))
        if row is None:
            raise KeyError(key)
        return str(row["value"])

    def set_meta(self, key: str, value: object) -> None:
        self.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, str(value)))

    def now(self) -> datetime:
        return parse_iso(self.meta("now"))

    def add_event(self, account_id: str, kind: str, payload: dict[str, Any]) -> None:
        self.execute(
            "INSERT INTO events (account_id, type, payload, sim_time) VALUES (?, ?, ?, ?)",
            (account_id, kind, json.dumps(payload), self.meta("now")),
        )

    def next_id(self, prefix: str, table: str) -> str:
        row = self.one(f"SELECT COUNT(*) AS n FROM {table}")
        return f"{prefix}_{(row['n'] if row else 0) + 1:06d}"
