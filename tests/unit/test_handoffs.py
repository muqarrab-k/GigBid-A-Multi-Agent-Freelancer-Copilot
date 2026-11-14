import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from agent.handoffs import (
    Approval,
    BidDecision,
    Claim,
    ClaimCheck,
    ClientIntent,
    ComplianceVerdict,
    Critique,
    EvidenceItem,
    FitReport,
    InterviewSlot,
    JobSpec,
    PriceQuote,
    ProposalDraft,
    RequirementMatch,
    RiskReport,
)

SAMPLE_JOBS = Path(__file__).resolve().parents[2] / "data" / "sample" / "jobs.json"

GOOD: list[tuple[type[BaseModel], dict[str, Any]]] = [
    (JobSpec, {"job_id": "j1", "title": "Churn model", "budget_min": 100, "budget_max": 200}),
    (RiskReport, {"score": 0.2, "client_quality": 0.9, "explanation": "verified client"}),
    (EvidenceItem, {"evidence_id": "e1", "type": "case_study", "source": "cv", "text": "x"}),
    (RequirementMatch, {"requirement": "Python", "strength": "strong", "evidence_ids": ["e1"]}),
    (FitReport, {"score": 0.7, "reasons": ["has python"]}),
    (BidDecision, {"job_id": "j1", "action": "bid", "reasons": ["good fit"]}),
    (
        PriceQuote,
        {
            "amount": 400,
            "billing": "fixed",
            "rationale": "mid band",
            "connects_cost": 8,
            "connects_worth_it": True,
        },
    ),
    (Claim, {"claim_id": "c1", "text": "Built a churn model", "evidence_ids": ["e1"]}),
    (ClaimCheck, {"claim_id": "c1", "label": "supported", "evidence_ids": ["e1"]}),
    (ProposalDraft, {"job_id": "j1", "cover_letter": "Hello.\n\nI built this."}),
    (Critique, {"verdict": "pass"}),
    (ComplianceVerdict, {"verdict": "allowed", "cleaned_text": "ok"}),
    (ClientIntent, {"intent": "question", "confidence": 0.8}),
    (InterviewSlot, {"start": "2026-11-20T10:00:00", "end": "2026-11-20T10:30:00"}),
    (Approval, {"action": "approve"}),
]


def test_risk_score_is_bounded() -> None:
    report = RiskReport(score=0.5, flags=[], explanation="sample")
    assert 0 <= report.score <= 1


def test_fit_score_is_bounded() -> None:
    report = FitReport(score=0.8)
    assert 0 <= report.score <= 1


@pytest.mark.parametrize(("model", "data"), GOOD, ids=lambda x: getattr(x, "__name__", ""))
def test_every_handoff_validates_and_round_trips(
    model: type[BaseModel], data: dict[str, Any]
) -> None:
    obj = model.model_validate(data)
    again = model.model_validate_json(obj.model_dump_json())
    assert again == obj


@pytest.mark.parametrize(("model", "data"), GOOD, ids=lambda x: getattr(x, "__name__", ""))
def test_every_handoff_rejects_extra_fields(model: type[BaseModel], data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**data, "surprise": 1})


def test_sample_job_maps_to_jobspec() -> None:
    job = json.loads(SAMPLE_JOBS.read_text())[0]
    spec = JobSpec(
        job_id=job["job_id"],
        title=job["title"],
        required_skills=job["required_skills"],
        budget_min=job["budget"]["min"],
        budget_max=job["budget"]["max"],
        timeline_days=job["duration_days"],
        screening_questions=job["screening_questions"],
        connects_cost=job["connects_cost"],
    )
    assert spec.connects_cost == 8


@pytest.mark.parametrize(
    "bad",
    [
        {"budget_min": 500, "budget_max": 100},
        {"budget_min": -1},
        {"connects_cost": -2},
        {"timeline_days": -1},
        {"title": "   "},
    ],
)
def test_jobspec_rejects_bad_values(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        JobSpec(**{"job_id": "j1", "title": "t", **bad})


def test_risk_flags_dedupe_and_sync_injection() -> None:
    report = RiskReport(
        score=0.9, flags=["scam", "scam", "off_platform"], injection_detected=True, explanation="x"
    )
    assert report.flags == ["scam", "off_platform", "injection"]

    from_flag = RiskReport(score=0.9, flags=["injection"], explanation="x")
    assert from_flag.injection_detected


@pytest.mark.parametrize(
    "bad", [{"score": 1.2}, {"flags": ["spooky"]}, {"client_quality": -0.1}, {"explanation": ""}]
)
def test_risk_rejects_bad_values(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RiskReport(**{"score": 0.3, "explanation": "x", **bad})


def test_requirement_match_needs_consistent_evidence() -> None:
    with pytest.raises(ValidationError):
        RequirementMatch(requirement="dbt", strength="strong")
    with pytest.raises(ValidationError):
        RequirementMatch(requirement="dbt", strength="none", evidence_ids=["e1"])


def test_fit_report_collects_matrix_evidence() -> None:
    report = FitReport(
        score=0.6,
        evidence_ids=["e1"],
        matrix=[
            RequirementMatch(requirement="Python", strength="strong", evidence_ids=["e1", "e2"]),
            RequirementMatch(requirement="dbt", strength="none"),
        ],
    )
    assert report.evidence_ids == ["e1", "e2"]


def test_bid_decision_rejects_bad_values() -> None:
    with pytest.raises(ValidationError):
        BidDecision(job_id="j1", action="maybe", reasons=["x"])  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        BidDecision(job_id="j1", action="skip", reasons=[])


@pytest.mark.parametrize("bad", [{"amount": 0}, {"billing": "weekly"}, {"connects_cost": -1}])
def test_price_quote_rejects_bad_values(bad: dict[str, Any]) -> None:
    base = {
        "amount": 300,
        "billing": "hourly",
        "rationale": "floor",
        "connects_cost": 6,
        "connects_worth_it": False,
    }
    with pytest.raises(ValidationError):
        PriceQuote(**{**base, **bad})


def test_claim_check_needs_evidence_unless_unsupported() -> None:
    with pytest.raises(ValidationError):
        ClaimCheck(claim_id="c1", label="partly")
    assert ClaimCheck(claim_id="c1", label="unsupported").evidence_ids == []


def test_draft_syncs_paragraphs_and_text() -> None:
    draft = ProposalDraft(job_id="j1", paragraphs=["Hi.", "I can help."])
    assert draft.cover_letter == "Hi.\n\nI can help."
    legacy = ProposalDraft(job_id="j1", cover_letter="Hi.\n\nI can help.")
    assert legacy.paragraphs == ["Hi.", "I can help."]


def test_draft_rejects_empty_and_unknown_evidence() -> None:
    with pytest.raises(ValidationError):
        ProposalDraft(job_id="j1")
    with pytest.raises(ValidationError, match="unknown evidence"):
        ProposalDraft(
            job_id="j1",
            cover_letter="I built X.",
            evidence_ids=["e1"],
            claims=[Claim(claim_id="c1", text="I built X", evidence_ids=["e9"])],
        )


def test_critique_and_compliance_need_reasons() -> None:
    with pytest.raises(ValidationError):
        Critique(verdict="revise")
    with pytest.raises(ValidationError):
        Critique(verdict="pass", revision_count=-1)
    with pytest.raises(ValidationError):
        ComplianceVerdict(verdict="blocked")


def test_intent_slot_and_approval_rules() -> None:
    with pytest.raises(ValidationError):
        ClientIntent(intent="small_talk", confidence=0.5)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        InterviewSlot(start="2026-11-20T10:00:00", end="2026-11-20T09:00:00")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Approval(action="reject")
    with pytest.raises(ValidationError):
        Approval(action="edit")
