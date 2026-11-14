import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from data_pipeline.common import PROCESSED_DIR

AS_OF = date(2024, 7, 31)
DISLIKES = {"generic_opening": 0.6, "too_long": 0.4, "no_relevant_example": 0.5,
            "upfront_questions": 0.25}
QUANTILES = (10, 25, 50, 75, 90)
MAX_GROUPS_PER_CLIENT = 30

Job = dict[str, Any]


def load_priors(path: Path = PROCESSED_DIR / "client_priors.json") -> dict[str, Any]:
    priors: dict[str, Any] = json.loads(path.read_text())["jobs"]
    return priors


def from_quantiles(q: dict[str, float], u: float, tail: float = 3.0, floor: float = 0.0) -> float:
    """Inverse CDF through p10..p90, linear tails."""
    xs = [0.0, *(k / 100 for k in QUANTILES), 1.0]
    ys = [floor, *(q[f"p{k}"] for k in QUANTILES), q["p90"] * tail]
    return float(np.interp(u, xs, ys))


def normal_client(cid: str, priors: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    hires = round(from_quantiles(priors["feedback_count"], rng.random()))
    if hires:
        rate = rng.beta(4, 3)
        posted = max(hires, int(np.ceil(hires / rate)))
        low = priors["spent_zero_share"]
        spent = round(from_quantiles(priors["spent_usd"], low + (1 - low) * rng.random()), 2)
        rating = round(min(5.0, from_quantiles(priors["rating"], rng.random(), tail=1.0, floor=3.0)), 2)
    else:
        posted, spent, rating = 1 + int(rng.poisson(1.5)), 0.0, None
    years = rng.uniform(0.3, 2.0) + min(hires, 60) / 60 * rng.uniform(0, 10)
    return {
        "client_id": cid,
        "synthetic": True,
        "country": None,
        "member_since": (AS_OF - timedelta(days=int(years * 365))).isoformat(),
        "payment_verified": bool(rng.random() < (0.9 if spent > 0 else 0.4)),
        "total_spent_usd": spent,
        "jobs_posted": posted,
        "hires": hires,
        "hire_rate": round(hires / posted, 2),
        "rating": rating,
        "reviews_count": hires,
    }


def scammer_client(cid: str, rng: np.random.Generator) -> dict[str, Any]:
    odd = rng.random() < 0.3
    posted = int(rng.integers(3, 16))
    hires = int(odd and rng.random() < 0.5)
    return {
        "client_id": cid,
        "synthetic": True,
        "country": None,
        "member_since": (AS_OF - timedelta(days=int(rng.integers(2, 60)))).isoformat(),
        "payment_verified": bool(rng.random() < 0.15),
        # odd spend
        "total_spent_usd": float(rng.integers(250, 900)) * 100 if odd else 0.0,
        "jobs_posted": posted,
        "hires": hires,
        "hire_rate": round(hires / posted, 2),
        "rating": None,
        "reviews_count": 0,
    }


def build_clients(splits: dict[str, list[Job]], scam_groups: set[str], n_clients: int,
                  scammer_share: float, seed: int,
                  priors: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    """Public clients, hidden secrets, and job_id -> client_id."""
    priors = priors or load_priors()
    rng = np.random.default_rng([seed, 11])
    n_scam = max(1, round(n_clients * scammer_share))
    ids = [f"cl_{i:04d}" for i in range(1, n_clients + 1)]
    scammer_ids, normal_ids = ids[:n_scam], ids[n_scam:]

    clients = [scammer_client(c, rng) for c in scammer_ids]
    clients += [normal_client(c, priors, rng) for c in normal_ids]
    countries = {k: v for k, v in priors["country_top15"].items() if k != "missing"}
    names, weights = list(countries), np.array(list(countries.values()))
    for client in clients:
        client["country"] = str(rng.choice(names, p=weights / weights.sum()))

    # one client per dup group
    groups = sorted({j["dup_group"] for jobs in splits.values() for j in jobs})
    scam_list = [g for g in groups if g in scam_groups]
    normal_list = [g for g in groups if g not in scam_groups]
    owner: dict[str, str] = {}
    for i, group in enumerate(scam_list):
        owner[group] = scammer_ids[i % len(scammer_ids)]
    shuffled = [normal_list[i] for i in rng.permutation(len(normal_list))]
    weights = 1 / np.arange(1, len(normal_ids) + 1) ** 0.5
    load: Counter[str] = Counter()
    for i, group in enumerate(shuffled):
        cid = normal_ids[i] if i < len(normal_ids) else str(rng.choice(normal_ids, p=weights / weights.sum()))
        # spill over busy clients
        while load[cid] >= MAX_GROUPS_PER_CLIENT:
            cid = normal_ids[(normal_ids.index(cid) + 1) % len(normal_ids)]
        owner[group] = cid
        load[cid] += 1

    assignment = {j["job_id"]: owner[j["dup_group"]] for jobs in splits.values() for j in jobs}
    jobs_by_client: dict[str, list[Job]] = {}
    for jobs in splits.values():
        for job in jobs:
            jobs_by_client.setdefault(assignment[job["job_id"]], []).append(job)

    secrets = [secret(c["client_id"], c["client_id"] in scammer_ids,
                      jobs_by_client.get(c["client_id"], []), rng) for c in clients]
    return clients, secrets, assignment


def secret(cid: str, scammer: bool, jobs: list[Job], rng: np.random.Generator) -> dict[str, Any]:
    skills = Counter(s for j in jobs for s in (j.get("skills") or []))
    fixed = [j["budget_max"] for j in jobs if j.get("budget_max")]
    hourly = [j["hourly_max"] for j in jobs if j.get("hourly_max")]
    return {
        "client_id": cid,
        "synthetic": True,
        "is_scammer": scammer,
        "must_have_skills": [s for s, _ in skills.most_common(2)],
        "budget_ceiling_fixed": round(max(fixed) * rng.uniform(1.0, 1.3)) if fixed else None,
        "budget_ceiling_hourly": round(max(hourly) * rng.uniform(1.0, 1.2), 2) if hourly else None,
        "dislikes": [d for d, p in DISLIKES.items() if rng.random() < p],
        "reply_tendency": round(float(rng.uniform(0.85, 1.0) if scammer else rng.beta(2, 4)), 2),
    }
