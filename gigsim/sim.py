import json
from datetime import timedelta
from typing import Any

from gigsim.clients import client_message, over_ceiling, rng_for, rule_score, sigmoid
from gigsim.judge import Judge
from gigsim.policy import Policy, load_policy
from gigsim.seeding import next_weekday
from gigsim.settings import Settings
from gigsim.store import Store, iso, parse_iso


class Sim:
    """Simulated clock, clients and lifecycle."""

    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self.judge = Judge(settings.clients.llm, settings.path(settings.clients.llm.cache_dir))

    @property
    def seed(self) -> str:
        return self.store.meta("seed")

    def policy(self) -> Policy:
        return load_policy(self.settings.path(self.settings.policies_dir), self.store.meta("policy"))

    def hours_later(self, low_high: tuple[int, int], *parts: object) -> str:
        rng = rng_for(self.seed, *parts)
        return iso(self.store.now() + timedelta(hours=rng.uniform(*low_high)))

    def set_status(self, proposal: dict[str, Any], status: str, **fields: Any) -> None:
        sets = ", ".join(f"{k} = ?" for k in ["status", "updated_at", *fields])
        values = (status, self.store.meta("now"), *fields.values(), proposal["proposal_id"])
        self.store.execute(f"UPDATE proposals SET {sets} WHERE proposal_id = ?", values)
        self.store.add_event(proposal["account_id"], "proposal.status_changed",
                             {"proposal_id": proposal["proposal_id"], "job_id": proposal["job_id"], "status": status})

    def job(self, job_id: str) -> dict[str, Any]:
        row = self.store.one("SELECT data FROM jobs WHERE job_id = ?", (job_id,))
        return json.loads(row["data"]) if row else {}

    def secret(self, client_id: str) -> dict[str, Any]:
        row = self.store.one("SELECT data FROM client_secrets WHERE client_id = ?", (client_id,))
        return json.loads(row["data"]) if row else {"dislikes": [], "must_have_skills": [],
                                                      "reply_tendency": 0.2, "is_scammer": False}

    def score(self, proposal: dict[str, Any], job: dict[str, Any], secret: dict[str, Any]) -> float:
        rule = rule_score(proposal, job, secret)
        if self.settings.clients.mode != "blended":
            return rule
        llm = self.judge.score(proposal, job, secret)
        weight = self.settings.clients.llm.weight
        return rule if llm is None else round((1 - weight) * rule + weight * llm, 4)

    # messages
    def post_client_message(self, thread_id: str, intent: str, offer: float | None, account_id: str) -> None:
        msg_id = self.store.next_id("msg", "messages")
        rng = rng_for(self.seed, msg_id)
        text, injected = client_message(intent, rng, offer, self.settings.clients.injection_share)
        self.store.execute(
            "INSERT INTO messages VALUES (?, ?, 'client', ?, ?, ?, ?)",
            (msg_id, thread_id, text, self.store.meta("now"), intent, int(injected)),
        )
        self.store.add_event(account_id, "message.created", {"thread_id": thread_id, "message_id": msg_id})

    def open_thread(self, proposal: dict[str, Any], client_id: str) -> str:
        thread_id = self.store.next_id("th", "threads")
        self.store.execute(
            "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, NULL)",
            (thread_id, proposal["account_id"], proposal["job_id"], client_id,
             proposal["proposal_id"], self.store.meta("now")),
        )
        return thread_id

    # lifecycle
    def view(self, proposal: dict[str, Any]) -> None:
        job = self.job(proposal["job_id"])
        secret = self.secret(job.get("client_id") or "")
        pid = proposal["proposal_id"]
        tendency = secret["reply_tendency"]
        scammer = secret["is_scammer"]
        p_view = 0.95 if scammer else min(0.95, max(0.05, self.settings.clients.base_view + 0.4 * (tendency - 0.3)))
        if rng_for(self.seed, pid, "view").random() >= p_view:
            self.set_status(proposal, "ignored")
            return
        score = self.score(proposal, job, secret)
        final_at = self.hours_later(self.settings.clients.final_delay_hours, pid, "final")
        self.set_status(proposal, "viewed", score=score, final_at=final_at)

        rng = rng_for(self.seed, pid, "respond")
        if scammer:
            intent, status = "scam", "replied"
        elif rng.random() < sigmoid(1.2 * score - 0.5) * (0.5 + tendency):
            interview = score > 1.0 and rng.random() < 0.5
            intent = "interview_request" if interview else (
                "negotiation" if over_ceiling(proposal, job, secret) else "question")
            status = "interview" if interview else "replied"
        else:
            return
        thread_id = self.open_thread(proposal, job.get("client_id") or "")
        offer = round(0.8 * proposal["bid_amount"]) if proposal["bid_amount"] else None
        self.post_client_message(thread_id, intent, offer, proposal["account_id"])
        self.set_status(proposal, status, thread_id=thread_id)

    def finalize(self, proposal: dict[str, Any]) -> None:
        if proposal["status"] == "viewed":
            self.set_status(proposal, "ignored")
            return
        job = self.job(proposal["job_id"])
        secret = self.secret(job.get("client_id") or "")
        if secret["is_scammer"]:
            self.set_status(proposal, "lost")
            return
        engaged = self.store.one(
            "SELECT 1 FROM messages WHERE thread_id = ? AND sender = 'freelancer'", (proposal["thread_id"],)
        )
        p_hire = sigmoid((proposal["score"] or 0) - 0.3) * (1.3 if engaged else 0.6)
        if rng_for(self.seed, proposal["proposal_id"], "hire").random() < p_hire:
            self.set_status(proposal, "hired")
            self.store.execute("UPDATE jobs SET status = 'closed' WHERE job_id = ?", (proposal["job_id"],))
        else:
            self.set_status(proposal, "lost")

    def followups(self, now: str) -> None:
        due = self.store.query(
            "SELECT t.*, p.status AS p_status FROM threads t JOIN proposals p USING (proposal_id) "
            "WHERE t.followup_at IS NOT NULL AND t.followup_at <= ? ORDER BY t.thread_id", (now,))
        for thread in due:
            self.store.execute("UPDATE threads SET followup_at = NULL WHERE thread_id = ?", (thread["thread_id"],))
            if thread["p_status"] in ("hired", "lost"):
                continue
            scammer = self.secret(thread["client_id"])["is_scammer"]
            intent = "scam_followup" if scammer else "followup"
            self.post_client_message(thread["thread_id"], intent, None, thread["account_id"])

    def refill(self) -> None:
        policy = self.policy()
        if self.store.now() < parse_iso(self.store.meta("next_refill")):
            return
        if policy.connects.weekly_refill == "reset":
            self.store.execute("UPDATE accounts SET connects = weekly_connects")
        else:
            self.store.execute("UPDATE accounts SET connects = connects + weekly_connects")
        for row in self.store.query("SELECT account_id FROM accounts"):
            self.store.add_event(row["account_id"], "connects.refilled", {})
        self.store.set_meta("next_refill", iso(next_weekday(self.store.now(), policy.connects.refill_weekday)))

    def step(self) -> None:
        """Advance one simulated hour."""
        now = iso(self.store.now() + timedelta(hours=1))
        self.store.set_meta("now", now)
        self.store.execute(
            "UPDATE jobs SET status = 'open', posted_at = release_at WHERE status = 'pending' AND release_at <= ?", (now,))
        self.refill()
        for p in self.store.query(
            "SELECT * FROM proposals WHERE status = 'submitted' AND decide_at <= ? ORDER BY proposal_id", (now,)):
            self.view(p)
        for p in self.store.query(
            "SELECT * FROM proposals WHERE status IN ('viewed', 'replied', 'interview') AND final_at <= ? "
            "ORDER BY proposal_id", (now,)):
            self.finalize(p)
        self.followups(now)

    def tick(self, hours: int) -> dict[str, Any]:
        for _ in range(hours):
            self.step()
        return {"sim_time": self.store.meta("now")}
