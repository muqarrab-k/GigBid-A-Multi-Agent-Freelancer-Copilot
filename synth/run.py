import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from agent.config import ROOT, get_config
from data_pipeline.common import PROCESSED_DIR, REAL_SEED_DIR, SEED_DIR
from data_pipeline.schema import MarketJob
from evals.datasets.labeling_rules import assign_personas, label_job
from synth import augment, quality
from synth.clients import build_clients
from synth.facts import PERSONAS, PERSONAS_DIR, load_facts
from synth.generator import Generator, write_cost_report
from synth.plan import load_jsonl, plan_persona
from synth.render import Renderer, write_jsonl

DEV_DIR = ROOT / "evals" / "datasets" / "dev"
SPLITS = ("history", "stream", "dev_pool")
SPOT_CHECK_ROWS = 30


def render_corpus() -> Renderer:
    renderer = Renderer(Generator())
    for persona in PERSONAS:
        stats = renderer.render_persona(persona)
        print(f"  {persona:<13} {stats['rendered']}/{stats['items']} items rendered")
    calls = renderer.generator.stats
    print(f"  llm calls this run: {calls['calls']} new, {calls['cache_hits']} cached")
    if renderer.stopped:
        print(f"  render stopped: {renderer.stopped}")
    return renderer


def clean_job(job: dict[str, Any]) -> dict[str, Any]:
    """Validate as MarketJob, so no label field slips in."""
    return MarketJob.model_validate(job).model_dump(mode="json")


def build_market(seed: int) -> dict[str, list[dict[str, Any]]]:
    cfg = get_config().synth
    real = {s: load_jsonl(REAL_SEED_DIR / f"jobs_{s}.jsonl") for s in SPLITS}
    chosen = augment.select_plants(real, cfg.scam_share, cfg.injection_share, seed)
    scam_groups = {c["dup_group"] for c in chosen if c["kind"] == "scam"}
    clients, secrets, owner = build_clients(real, scam_groups, cfg.clients, cfg.scammer_share, seed)
    market, log = augment.apply_plants(real, chosen, seed)

    for split, jobs in market.items():
        rows = [clean_job({**j, "client_id": owner[j["job_id"]]}) for j in jobs]
        market[split] = rows
        write_jsonl(SEED_DIR / f"jobs_{split}.jsonl", rows)
    write_jsonl(SEED_DIR / "clients.jsonl", clients)
    write_jsonl(SEED_DIR / "client_secrets.jsonl", secrets)
    write_jsonl(augment.PLANT_LOG, log)

    used = {i.extra["job_id"] for p in PERSONAS for i in plan_persona(p) if i.type == "proposal"}
    holdout, labels = augment.holdout_jobs(real["history"], used, cfg.holdout_size, seed)
    augment.HOLDOUT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(augment.HOLDOUT_DIR / "jobs.jsonl", [clean_job(j) for j in holdout])
    write_jsonl(augment.HOLDOUT_DIR / "labels.jsonl", labels)
    print(f"  clients: {len(clients)} ({sum(s['is_scammer'] for s in secrets)} scammers)")
    print(f"  plants: {Counter((p['split'], p['kind']) for p in log)}")
    print(f"  injection holdout: {len(holdout)} jobs")
    return market


def build_labels(dev_jobs: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    cfg = get_config().synth
    pricing = json.loads((PROCESSED_DIR / "pricing_stats.json").read_text())
    plants = {p["job_id"]: p for p in load_jsonl(augment.PLANT_LOG) if p["split"] == "dev_pool"}
    owner = assign_personas(dev_jobs, seed)
    facts = {p: load_facts(p) for p in PERSONAS}
    manifests = {p: load_jsonl(PERSONAS_DIR / p / "manifest.jsonl") for p in PERSONAS}
    labels = []
    for job in sorted(dev_jobs, key=lambda j: j["job_id"]):
        persona = owner[job["job_id"]]
        label = label_job(job, persona, facts[persona], manifests[persona], pricing,
                          plants.get(job["job_id"]), cfg)
        labels.append(label.model_dump())
    DEV_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(DEV_DIR / "labels.jsonl", labels)
    return labels


def spot_check(labels: list[dict[str, Any]], jobs: list[dict[str, Any]], seed: int, path: Path) -> None:
    by_id = {j["job_id"]: j for j in jobs}
    rng = np.random.default_rng([seed, 31])
    picks = [labels[i] for i in sorted(rng.choice(len(labels), SPOT_CHECK_ROWS, replace=False))]
    lines = [
        "# Dev label spot check",
        "",
        "30 random dev jobs (seeded) with their rule-based labels. Mark each one agree or disagree,",
        "and note the correct label. These are reused for judge calibration.",
        "",
    ]
    for n, label in enumerate(picks, start=1):
        job = by_id[label["job_id"]]
        price = (f"fixed ${job['budget_max']:.0f}" if job.get("budget_max") is not None
                 else f"hourly ${job['hourly_min']}-{job['hourly_max']}" if job.get("hourly_max") is not None
                 else "no budget")
        desc = " ".join(str(job.get("description") or "").split())[:300]
        lines += [
            f"## {n}. {job['title']}",
            "",
            f"- job_id: `{job['job_id']}` | persona: **{label['persona']}** | {price}",
            f"- skills: {', '.join(job.get('skills') or []) or 'none'}",
            f"- text: {desc}...",
            f"- **decision: {label['decision']}** | scam: {label['is_scam']} | injection: {label['has_injection']}",
            f"- fair price band: {label['fair_price_band']}",
            f"- evidence: {', '.join(label['relevant_evidence_ids']) or 'none'}",
            f"- reasons: {'; '.join(label['reasons'])}",
            "- your verdict: [ ] agree  [ ] disagree, correct label: ____",
            "",
        ]
    path.write_text("\n".join(lines))


def summary(market: dict[str, list[dict[str, Any]]], labels: list[dict[str, Any]], renderer: Renderer) -> None:
    print("\nsummary")
    for persona in PERSONAS:
        manifest = load_jsonl(PERSONAS_DIR / persona / "manifest.jsonl")
        types = Counter(m["type"] for m in manifest)
        rendered = sum(m["rendered"] for m in manifest)
        outcomes = Counter(m["outcome"] for m in manifest if m["type"] == "proposal")
        print(f"  {persona}: {dict(types)}, rendered {rendered}/{len(manifest)}, outcomes {dict(outcomes)}")
    by_persona = Counter((lab["persona"], lab["decision"]) for lab in labels)
    print(f"  dev labels: {dict(sorted(by_persona.items()))}")
    print(f"  dev scams: {sum(lab['is_scam'] for lab in labels)}, injections: {sum(lab['has_injection'] for lab in labels)}")
    for persona, q in quality.main().items():
        g, c = q["grounding"], q["code"]
        print(f"  quality {persona}: stray numbers {g['with_stray_numbers']}/{g['proposals']}, "
              f"python parses {c['python_parses']}, three-ways overlap {q['three_ways']['mean_trigram_jaccard']}")
    cost = write_cost_report(renderer.generator.used)
    print(f"  llm: {cost['calls']} calls, {cost['input_tokens']:,} in / {cost['output_tokens']:,} out, ~${cost['cost_usd']}")


def main() -> None:
    seed = get_config().data.seed
    print("1/4 render corpus")
    renderer = render_corpus()
    print("2/4 clients and plants")
    market = build_market(seed)
    print("3/4 dev labels")
    labels = build_labels(market["dev_pool"], seed)
    print("4/4 spot check")
    spot_check(labels, market["dev_pool"], seed, DEV_DIR / "SPOT_CHECK.md")
    summary(market, labels, renderer)


if __name__ == "__main__":
    main()
