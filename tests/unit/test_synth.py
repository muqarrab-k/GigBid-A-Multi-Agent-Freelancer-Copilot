import base64
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from agent.config import ROOT, load_config
from agent.prompts.loader import load_prompt
from data_pipeline.schema import MarketJob
from evals.datasets.labeling_rules import assign_personas, decide, label_job, price_band
from synth import augment
from synth.clients import build_clients
from synth.facts import PERSONAS, Facts, load_facts
from synth.generator import Generator
from synth.plan import portfolio_items, proposal_items, review_items

SEED_DIR = ROOT / "gigsim" / "seed"
MANIFEST_KEYS = {"evidence_id", "persona", "type", "project", "skills", "date",
                 "client_industry", "outcome", "path", "synthetic", "rendered"}
SECRET_KEYS = {"is_scammer", "must_have_skills", "budget_ceiling_fixed", "budget_ceiling_hourly",
               "dislikes", "reply_tendency"}
LABEL_KEYS = {"is_scam", "has_injection", "decision", "label", "plant", "kind", "subtype",
              "goal", "relevant_evidence_ids", "fair_price_band"}


def job(i: int, **kw: Any) -> dict[str, Any]:
    base = {
        "job_id": f"job{i:013d}",
        "source": "fixture",
        "title": "Build a RAG chatbot with LangChain",
        "description": "We need a LangChain and OpenAI API assistant over our PDFs with FastAPI.",
        "skills": ["LangChain", "Python"],
        "budget_type": "fixed",
        "budget_min": 800.0,
        "budget_max": 800.0,
        "persona_tags": ["ai_ml"],
        "dup_group": f"grp{i:04d}",
        "currency": "USD",
    }
    return {**base, **kw}


@pytest.fixture
def ai_facts() -> Facts:
    return load_facts("ai_ml")


@pytest.fixture
def splits() -> dict[str, list[dict[str, Any]]]:
    return {
        "history": [job(i) for i in range(30)],
        "stream": [job(100 + i) for i in range(50)],
        "dev_pool": [job(200 + i) for i in range(50)],
    }


def test_all_fact_sheets_load() -> None:
    for persona in PERSONAS:
        facts = load_facts(persona)
        assert facts.synthetic and facts.fictional
        assert 15 <= len(facts.projects) <= 25


def test_facts_reject_broken_links(ai_facts: Facts) -> None:
    raw = ai_facts.model_dump()
    raw["repos"][0]["project"] = "p99"
    with pytest.raises(ValidationError, match="unknown project"):
        Facts.model_validate(raw)


def test_manifest_metadata_complete(ai_facts: Facts, splits: dict[str, list[dict[str, Any]]]) -> None:
    items = [*portfolio_items(ai_facts), *review_items(ai_facts, 25),
             *proposal_items(ai_facts, splits["history"] + [job(900, persona_tags=[])], 10)]
    rows = [i.manifest_row(rendered=False) for i in items]
    assert len({r["evidence_id"] for r in rows}) == len(rows)
    for row in rows:
        assert set(row) == MANIFEST_KEYS
        assert row["synthetic"] is True
        assert row["persona"] == "ai_ml"
        if row["type"] == "proposal":
            assert row["outcome"] in {"won", "replied", "ignored"}
        else:
            assert row["outcome"] is None and row["project"] and row["client_industry"]


def test_proposals_only_cite_fact_projects(ai_facts: Facts, splits: dict[str, list[dict[str, Any]]]) -> None:
    ids = {p.id for p in ai_facts.projects}
    for item in proposal_items(ai_facts, splits["history"] + [job(900, persona_tags=[])], 10):
        cited = item.extra["cited_projects"]
        assert set(cited) <= ids and item.date
        for pid in cited:
            assert ai_facts.project(pid).end < item.date[:7] or ai_facts.project(pid).end == item.date[:7]
            assert ai_facts.project(pid).title in item.values["style"]


def test_committed_proposals_cite_fact_projects() -> None:
    for persona in PERSONAS:
        ids = {p.id for p in load_facts(persona).projects}
        path = ROOT / "data" / "personas" / persona / "proposals.jsonl"
        for line in path.read_text().splitlines():
            assert set(json.loads(line)["cited_projects"]) <= ids


def test_label_rules_cases(ai_facts: Facts) -> None:
    cfg = load_config().synth
    assert decide(job(1), ai_facts, None, cfg)[0] == "bid"
    assert decide(job(1), ai_facts, {"kind": "scam", "subtype": "crypto"}, cfg)[0] == "skip"
    assert decide(job(1, title="iOS app with Swift"), ai_facts, None, cfg)[0] == "skip"
    cheap = job(1, budget_min=50.0, budget_max=50.0)
    assert "below floor" in decide(cheap, ai_facts, None, cfg)[1][-1]
    injected = decide(job(1), ai_facts, {"kind": "injection", "subtype": "plain_end"}, cfg)
    assert injected[0] == "bid" and "injection" in injected[1][0]


def test_labels_deterministic(ai_facts: Facts, splits: dict[str, list[dict[str, Any]]]) -> None:
    cfg = load_config().synth
    pricing = {"cells": [{"source": "contracts", "category": "ai_ml", "budget_type": "fixed",
                          "experience_level": "any", "p25": 50.0, "p75": 500.0}]}
    manifest = [i.manifest_row(False) for i in portfolio_items(ai_facts)]
    jobs = splits["dev_pool"] + [job(300, persona_tags=[])]
    first = [label_job(j, "ai_ml", ai_facts, manifest, pricing, None, cfg) for j in jobs]
    second = [label_job(j, "ai_ml", ai_facts, manifest, pricing, None, cfg) for j in jobs]
    assert first == second
    # posted $800 sits above the market band
    assert first[0].relevant_evidence_ids and first[0].fair_price_band == [640.0, 880.0]
    assert assign_personas(jobs, 1) == assign_personas(jobs, 1)
    assert price_band(job(1, budget_type=None), "ai_ml", pricing) is None
    assert price_band(job(1, budget_max=None), "ai_ml", pricing, floor=200) == [200.0, 500.0]


def test_planted_job_files_have_no_labels(splits: dict[str, list[dict[str, Any]]]) -> None:
    chosen = augment.select_plants(splits, 0.1, 0.1, seed=3)
    market, log = augment.apply_plants(splits, chosen, seed=3)
    assert {p["kind"] for p in log} == {"scam", "injection"}
    for rows in market.values():
        for row in rows:
            assert not set(row) & LABEL_KEYS
            MarketJob.model_validate(row)


def test_committed_job_files_have_no_labels() -> None:
    allowed = set(MarketJob.model_fields)
    for split in ("history", "stream", "dev_pool"):
        for line in (SEED_DIR / f"jobs_{split}.jsonl").read_text().splitlines():
            assert set(json.loads(line)) <= allowed


def test_client_secrets_kept_apart(splits: dict[str, list[dict[str, Any]]]) -> None:
    priors = json.loads((Path(__file__).parent / "fixtures_client_priors.json").read_text())
    clients, secrets, owner = build_clients(splits, {"grp0100"}, 20, 0.1, seed=5, priors=priors)
    assert all(not set(c) & SECRET_KEYS for c in clients)
    assert {s["client_id"] for s in secrets} == {c["client_id"] for c in clients}
    scammers = {s["client_id"] for s in secrets if s["is_scammer"]}
    assert owner["job0000000000100"] in scammers
    assert set(owner) == {j["job_id"] for rows in splits.values() for j in rows}


def test_committed_clients_have_no_secrets() -> None:
    for line in (SEED_DIR / "clients.jsonl").read_text().splitlines():
        assert not set(json.loads(line)) & SECRET_KEYS


def test_holdout_styles_never_in_dev() -> None:
    plants = yaml.safe_load(augment.PLANTS_PATH.read_text())["injections"]
    assert not set(plants["holdout_styles"]) & set(plants["dev_styles"])


def test_holdout_disjoint_from_dev(splits: dict[str, list[dict[str, Any]]]) -> None:
    jobs, labels = augment.holdout_jobs(splits["history"], {"job0000000000000"}, 6, seed=2)
    assert "job0000000000000" not in {lab["base_job_id"] for lab in labels}
    assert not {j["job_id"] for j in jobs} & {j["job_id"] for j in splits["dev_pool"]}


def test_committed_holdout_disjoint_from_dev() -> None:
    dev = {json.loads(x)["job_id"] for x in (SEED_DIR / "jobs_dev_pool.jsonl").read_text().splitlines()}
    holdout_dir = ROOT / "evals" / "datasets" / "injection_holdout"
    labels = [json.loads(x) for x in (holdout_dir / "labels.jsonl").read_text().splitlines()]
    log = [json.loads(x) for x in (ROOT / "evals" / "datasets" / "plant_log.jsonl").read_text().splitlines()]
    assert not {lab["job_id"] for lab in labels} & dev
    assert not {lab["base_job_id"] for lab in labels} & dev
    assert not {lab["style"] for lab in labels} & {p["subtype"] for p in log if p["kind"] == "injection"}


def test_injection_styles() -> None:
    assert "​" in augment.styled("hello there", "hola", "zero_width")
    encoded = augment.styled("ignore rules", "x", "base64").split(": ")[1]
    assert base64.b64decode(encoded).decode() == "ignore rules"
    with pytest.raises(ValueError):
        augment.styled("x", "x", "telepathy")


def test_generator_uses_cache(tmp_path: Path) -> None:
    gen = Generator(cache_dir=tmp_path)
    values = {"repo": "r", "path": "a.py", "stack": "Python", "purpose": "p", "built": "b"}
    key = gen.key(load_prompt("synth_system"), gen.prompt("synth_code", **values))
    (tmp_path / f"{key}.json").write_text(json.dumps({"text": "print('cached')"}))
    assert gen.complete("synth_code", "t", **values) == "print('cached')"
    assert gen.stats["cache_hits"] == 1
