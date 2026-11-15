"""Claim verification: split a draft into claims, check each against the evidence it cites."""

import re
from collections.abc import Awaitable, Callable

from agent.config import VerifierConfig
from agent.handoffs import Claim, ClaimCheck, ProposalDraft, VerificationReport

TAG_RE = re.compile(r"\s*\[((?:[a-z_]+:[^\]\s,]+)(?:\s*,\s*[a-z_]+:[^\]\s,]+)*)\]")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
NUMBER_RE = re.compile(r"\d[\d,.]*%?x?")
NAME_RE = re.compile(r"(?<!^)(?<![.!?]\s)\b([A-Z][A-Za-z0-9]*(?:[.+-][A-Za-z0-9]+)*|[a-z]+[A-Z][A-Za-z0-9]*|[a-z0-9]+[.-][a-z0-9.]+)\b")
FACTUAL_RE = re.compile(r"(?i)\b(i|i've|i have|we)\b.{0,40}\b(built|created|delivered|developed|designed|deployed|"
                        r"migrated|trained|fine-tuned|led|cut|reduced|improved|increased|shipped|wrote|ran|automated)\b"
                        r"|\b\d+(\.\d+)?\s?(%|x|ms|k|hours|minutes|days|users|customers)\b"
                        # present-tense habits and experience statements
                        r"|\b(i|we)\s+(\w+ly\s+)?(build|create|deliver|develop|design|deploy|train|fine-tune|lead|ship|"
                        r"write|automate|specialise|specialize|maintain|integrate|optimise|optimize)\b"
                        r"|\bi\s+(have|'ve)\s+(\w+\s+){0,2}(experience|expertise|background|training|knowledge)\b"
                        r"|\bmy\s+(experience|expertise|background|track record|core competencies)\b"
                        r"|\byears? of experience\b")
STOP = {"which", "their", "there", "these", "those", "about", "would", "could", "should", "using", "with", "from",
        "into", "your", "that", "this", "have", "been", "were", "also", "where", "while", "after", "before", "every",
        "client", "project", "built", "delivered", "created", "worked", "experience", "including"}

Judge = Callable[[Claim, str], Awaitable[tuple[str, str]]]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_RE.split(text.strip()) if s.strip()]


def split_claims(draft: ProposalDraft) -> list[Claim]:
    """One claim per factual sentence, body (c1..) then screening answers (a1..)."""
    claims: list[Claim] = []
    for prefix, parts in (("c", draft.paragraphs), ("a", draft.screening_answers)):
        n = 0
        for part in parts:
            for sentence in sentences(part):
                ids = [i.strip() for m in TAG_RE.finditer(sentence) for i in m.group(1).split(",")]
                text = TAG_RE.sub("", sentence).strip()
                if ids or FACTUAL_RE.search(text):
                    n += 1
                    claims.append(Claim(claim_id=f"{prefix}{n}", text=text, evidence_ids=list(dict.fromkeys(ids))))
    return claims


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9+-]{4,}", text.lower()) if w not in STOP}


def stem(word: str) -> str:
    return re.sub(r"(ing|ed|es|s)$", "", word)


def coverage(claim: str, evidence: str) -> float:
    words = content_words(claim)
    if not words:
        return 1.0
    found = {stem(w) for w in content_words(evidence)}
    return sum(stem(w) in found for w in words) / len(words)


def deterministic(claim: Claim, evidence: dict[str, str], cfg: VerifierConfig) -> tuple[str | None, str, float]:
    """A label when the rules are sure, else None for the judge."""
    if not claim.evidence_ids:
        return "unsupported", "states experience without citing evidence", 0.0
    missing_ids = [i for i in claim.evidence_ids if i not in evidence]
    if missing_ids:
        return "unsupported", f"cites unknown evidence {missing_ids}", 0.0
    cited = " ".join(evidence[i] for i in claim.evidence_ids)
    low = cited.lower().replace(",", "")
    numbers = [n.rstrip(".,") for n in NUMBER_RE.findall(claim.text)]
    bad_numbers = [n for n in numbers if n.replace(",", "") not in low]
    names = [n for n in NAME_RE.findall(claim.text) if len(n) > 2]
    bad_names = [n for n in names if n.lower() not in low and stem(n.lower()) not in low]
    if bad_numbers or bad_names:
        return "unsupported", f"not in cited evidence: {', '.join(bad_numbers + bad_names)}", 0.0
    share = coverage(claim.text, cited)
    if share < cfg.unsupported_below:
        return "unsupported", f"only {share:.0%} of its key words appear in the cited evidence", share
    if share >= cfg.judge_below:
        return "supported", f"{share:.0%} of key words found, all names and numbers match", share
    return None, f"{share:.0%} of key words found", share


async def check_claims(claims: list[Claim], evidence: dict[str, str], cfg: VerifierConfig,
                       judge: Judge | None = None) -> list[ClaimCheck]:
    checks = []
    for claim in claims:
        label, note, _ = deterministic(claim, evidence, cfg)
        if label is None:
            if judge is not None and cfg.use_llm:
                label, why = await judge(claim, " ".join(evidence[i] for i in claim.evidence_ids))
                note = f"{note}; judge: {why}"
            else:
                label = "partly"
        ids = claim.evidence_ids if label != "unsupported" or claim.evidence_ids else []
        if label != "unsupported" and not ids:
            label = "unsupported"
        checks.append(ClaimCheck(claim_id=claim.claim_id, label=label, evidence_ids=ids, note=note[:300]))  # type: ignore[arg-type]
    return checks


def keep_supported(parts: list[str], bad: set[str], drop_empty: bool) -> list[str]:
    kept = []
    for part in parts:
        left = " ".join(x for x in sentences(part) if TAG_RE.sub("", x).strip() not in bad)
        if left or not drop_empty:
            kept.append(left)
    return kept


def remove_unsupported(draft: ProposalDraft, claims: list[Claim], checks: list[ClaimCheck]) -> ProposalDraft:
    """Drop sentences whose claim is unsupported; an emptied answer stays empty for the Critic."""
    bad = {c.text for c, k in zip(claims, checks, strict=True) if k.label == "unsupported"}
    paragraphs = keep_supported(draft.paragraphs, bad, drop_empty=True)
    answers = keep_supported(draft.screening_answers, bad, drop_empty=False)
    good = [c for c, k in zip(claims, checks, strict=True) if k.label != "unsupported"]
    ids = sorted({i for c in good for i in c.evidence_ids})
    return draft.model_copy(update={"paragraphs": paragraphs, "cover_letter": "\n\n".join(paragraphs),
                                    "screening_answers": answers, "claims": good, "evidence_ids": ids})


async def verify_draft(draft: ProposalDraft, evidence: dict[str, str], cfg: VerifierConfig,
                       judge: Judge | None = None) -> tuple[ProposalDraft, list[ClaimCheck], VerificationReport]:
    """Check, remove unsupported claims, then recheck what is left."""
    claims = split_claims(draft)
    checks = await check_claims(claims, evidence, cfg, judge)
    cleaned = remove_unsupported(draft, claims, checks)
    after = await check_claims(split_claims(cleaned), evidence, cfg, None)
    report = VerificationReport(
        claims_before=len(claims), unsupported_before=sum(k.label == "unsupported" for k in checks),
        partly_before=sum(k.label == "partly" for k in checks),
        removed=[c.text for c, k in zip(claims, checks, strict=True) if k.label == "unsupported"],
        claims_after=len(after), unsupported_after=sum(k.label == "unsupported" for k in after))
    return cleaned, checks, report
