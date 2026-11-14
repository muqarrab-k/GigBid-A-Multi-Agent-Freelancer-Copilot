# RAG notes (hypothesis material)

## Proposal crowd-out in V0 (2026-11-14)

V0 searches every chunk type with the whole job post as the query. On the 95 dev bid jobs,
448 of the 475 top-5 hits were past **proposals** (`evals/results/rag_v0.json`). Proposals are
written in answer to job posts, so they read like the query, and they are about 70% of all
chunks. The gold evidence (`relevant_evidence_ids`) covers only case studies, READMEs, reviews
and code, so V0 scores Recall@5 0.023, MRR 0.046, nDCG@10 0.030.

Restricting the same V0 search to portfolio types (case study, README, review, code, CV)
gives Recall@5 0.235, MRR 0.405, nDCG@10 0.316
(`evals/results/rag_v0_only_case_study_readme_review_code_cv.json`). That run is a diagnostic,
not a variant: V0 stays as the honest baseline.

Hypotheses for later variants:
- H1: Any variant that separates proof (case studies, code, reviews) from phrasing (past
  proposals) beats V0 by a wide margin; the type filter alone is worth about +21 points of
  Recall@5. The agent-facing default now searches portfolio types and asks for proposals
  explicitly.
- H2: Requirement decomposition (V1) helps most on jobs listing four or more requirements,
  because the whole-post query is dominated by boilerplate.
- H3: Outcome-aware ranking (V4) should use proposals for phrasing and style signals, not as
  evidence of experience.
- H4: Code chunks rarely win with whole-post queries; multi-vector items (V5) should lift README
  and code recall for projects whose README is generic.
