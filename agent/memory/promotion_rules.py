"""When a repeated human edit or an outcome pattern may become long-term memory.

Style: each approval edit is reduced to named patterns (cut the first sentence, removed a watched
term, made it much shorter, cut the sign-off). A pattern is promoted only when it shows up in at
least `min_repeats` edits, in at least `min_share` of the last `window` edits, and no edit in that
window went the other way (put the term back, made it longer). Only these derived patterns are
stored, never raw tool output or the draft text itself.

Outcome: a job category is promoted only after `min_submitted` proposals and a reply rate of at
least `min_reply_rate`; a weaker category is kept as an observation, not a rule.
"""

import re
from dataclasses import dataclass

from agent.config import OutcomeMemory, StyleMemory
from rag.verify import sentences


@dataclass(frozen=True)
class Pattern:
    key: str
    rule: str


def words(text: str) -> int:
    return len(text.split())


def has_term(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text.lower()) is not None


def edit_patterns(before: str, after: str, cfg: StyleMemory) -> tuple[list[Pattern], list[str]]:
    """Patterns this edit shows, plus keys it contradicts."""
    found: list[Pattern] = []
    against: list[str] = []
    old, new = sentences(before), sentences(after)
    if len(old) > 1 and new and old[0] not in after and old[1] in after:
        found.append(Pattern("cut_first_sentence", "Drop the warm-up first sentence; open with the client's problem."))
    if len(old) > 1 and new and old[-1] not in after and old[-2] in after:
        found.append(Pattern("cut_last_sentence", "End on the plan or the price; skip a closing pleasantry."))
    for term in cfg.watch_terms:
        if has_term(before, term) and not has_term(after, term):
            found.append(Pattern(f"removed_term:{term}", f"Never use the phrase '{term}'."))
        elif has_term(after, term) and not has_term(before, term):
            against.append(f"removed_term:{term}")
    if before and words(after) <= cfg.shorter_ratio * words(before):
        found.append(Pattern("shorter", f"Keep cover letters short, about {words(after)} words or fewer."))
    elif before and words(after) > words(before):
        against.append("shorter")
    return found, against


def should_promote(key: str, history: list[dict[str, list[str]]], cfg: StyleMemory) -> bool:
    """history: per edit, its 'patterns' and 'against' keys, oldest first."""
    total = sum(key in h["patterns"] for h in history)
    recent = history[-cfg.window :]
    share = sum(key in h["patterns"] for h in recent) / len(recent) if recent else 0.0
    contradicted = any(key in h["against"] for h in recent)
    return total >= cfg.min_repeats and share >= cfg.min_share and not contradicted


def should_promote_outcome(submitted: int, replied: int, cfg: OutcomeMemory) -> bool:
    return submitted >= cfg.min_submitted and replied / submitted >= cfg.min_reply_rate
