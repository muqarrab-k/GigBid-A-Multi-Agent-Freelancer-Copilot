---
title: "GigBid: design review of a multi-agent freelancer copilot"
subtitle: "AI-4016 Assignment II · R&D report (draft)"
author: "Muqarrab · i230511 · Section C"
date: "15 November 2026"
---

Every number in this report comes from a committed file under `evals/results/` (named in
brackets) or from a commit hash. The instructor did not release GigSim, the personas or the
evaluation sets, so I built all three: real job and contract data from Kaggle, plus clearly
labelled synthetic personas, clients and gold labels (`docs/DATA_CARD.md`). The hidden test has
not run yet.

# 1. Problem and constraints

A freelancer scans job feeds for hours, pays Connects to bid, and sends proposals that clients
ignore or that land on scams asking for free work or off-platform payment. GigBid automates the
reading and the drafting; the freelancer keeps the decisions.

**What must never be automated.** Sending a proposal or a message, and spending Connects. Every
such write goes through a LangGraph `interrupt()` and resumes only with an explicit human
`approve`. `autonomy.auto_send` is typed `Literal[False]`, so a config that turns it on fails to
load, and `submit` raises unless the stored approval says approve (`docs/ARCHITECTURE.md`). A
proposal may claim only what the portfolio supports, and job posts and client messages are
untrusted data.

**Budgets I declared** (`agent/config.yaml`, `budgets.targets`): p95 latency 20 s per job analysed
and 60 s per proposal; cost $0.002 per job and $0.01 per proposal. Section 10 compares them with
what I measured.

# 2. Architecture

GigBid is two hand-written LangGraph graphs on one Postgres checkpointer, three MCP servers of
my own, and a React + FastAPI front end (`docs/ARCHITECTURE.md` has both graphs rendered from code).

**Bid graph** (one thread per job). `intake` fans out with `Send` to three nodes that run in
parallel. The **Job Analyst** extracts a `JobSpec` and exists because everything downstream needs
structured requirements. The **Risk Assessor** combines rule signals (scam patterns, client
history, injection patterns) with one small-model call; it exists because scams and injected text
must be caught before anything costs money. The **Fit Matcher** maps each requirement to portfolio
evidence. `join` enforces the step and token budgets, `decide` applies config rules (skip / watch /
bid), and **Pricing** sets a bid from market statistics, client spend and the persona floor. The
**Writer** drafts with evidence ids on every factual sentence. The **claim verifier**
(`rag/verify.py`) removes unsupported claims before the **Critic** sees the draft. The Critic
sends it back at most twice, then a **Compliance Guard** checks `policy_rules.yaml`.
`prepare_approval` dry-runs the submission and the human gate interrupts. Edits re-run the
verifier and compliance.

**Conversation graph** (one thread per client conversation): read messages, classify intent,
propose real calendar slots, guard the reply, interrupt for approval, send with an idempotency key.

**Tool layer.** Agents never call GigSim directly: node → MCP client (per-node allowlist, one
trace id, retries) → Marketplace MCP server → `MarketplacePort` → GigSim adapter (or the Upwork
adapter in live mode). The Portfolio MCP server serves retrieval and the Workspace server serves
calendar slots and email drafts. Write tools take an idempotency key and support `dry_run`
(`docs/TOOLS.md`).

**Stores.** Postgres holds checkpoints (state), the LangGraph store (long-term style and outcome
memory, written only by promotion rules in `agent/memory/promotion_rules.py`) and pgvector
(retrieval). The execution trace is kept apart from state and memory: nodes never read it to decide.

**Durability, proven once.** I killed the process while it waited for approval, and again right
after `submit_proposal` returned, then restarted. The job was submitted exactly once and Connects
were charged once (80 → 68 for a 12-Connect job) although two submit calls reached the server
[`crash_resume.json`, commit `13c64f9`].

# 3. RQ-A: tool granularity (not run)

I did not run this study. The plan: 40 tasks with known correct tool calls (search, fetch, client
history, balance, draft), three tool sets (many fine-grained tools, a few coarse ones, and the
current set with rewritten descriptions), one agent model, and three metrics: tool-selection
accuracy, argument accuracy against the gold call, and tokens per task. The only evidence I have is
anecdotal. The single ReAct baseline, offered all 9 tools, picked a sensible sequence on both demo
jobs (`get_job`, `get_client_history`, 2–3 × `search_evidence`, `create_proposal_draft`)
[`single_agent_demo.json`]. That is not a measurement, so I make no claim.

# 4. RQ-B: retrieval and claim verification

**Hypothesis, stated before any variant ran** (`docs/rag_notes.md`): a portfolio-type filter plus
requirement decomposition plus hybrid retrieval raises Recall@5 by 15+ points over V0 on dev bid
jobs with 4+ requirements, by less on the others, and a cross-encoder rerank adds a few more.

**Setup.** 95 dev bid jobs with gold evidence (case studies, READMEs, reviews, code), k = 10,
nomic-embed-text v1.5 embeddings, bge-reranker-v2-m3 over the top 30.

| Variant | Recall@5 | MRR | nDCG@10 | R@5, 4+ reqs | R@5, <4 reqs | p50 ms |
|---|---|---|---|---|---|---|
| V0 dense | 0.023 | 0.046 | 0.030 | 0.026 | 0.016 | 90 |
| type filter | 0.235 | 0.405 | 0.316 | 0.240 | 0.221 | 64 |
| **filter + hybrid (shipped)** | **0.255** | **0.475** | **0.348** | 0.249 | 0.275 | 65 |
| filter + decomposition | 0.147 | 0.298 | 0.230 | 0.149 | 0.144 | 214 |
| filter + rerank | 0.132 | 0.261 | 0.192 | 0.126 | 0.149 | 5,886 |
| filter + decomp + hybrid | 0.196 | 0.405 | 0.298 | 0.197 | 0.192 | 398 |
| filter + decomp + hybrid + rerank | 0.119 | 0.269 | 0.190 | 0.126 | 0.101 | 2,191 |

[`rag_results_table.md`]. **Ablation of the shipped variant:** dropping the filter costs 0.239
Recall@5 and 0.422 MRR; dropping hybrid costs 0.020 Recall@5 and 0.070 MRR [`rag_ablation.json`].
**Per persona** (shipped): ai_ml 0.195, data_analyst 0.339, fullstack 0.239 Recall@5.

**The hypothesis is rejected.** On 4+ requirement jobs the full stack does beat V0 by 17.1 points
(0.026 → 0.197), but the type filter alone gives all of it, and decomposition then takes 5.2 points
away (0.249 → 0.197). Rerank subtracts instead of adding. Why: in V0, 448 of the 475 top-5 hits were
past **proposals** [`rag_v0.json`]. They are written in answer to job posts, so they read like the
query, and they are 70% of all chunks. Short requirement queries ("experience with Python") favour
short, skill-dense reviews (232 of 475 top-5 slots against 110 gold items), and the cross-encoder
favours code chunks (86 top-5 slots against 3 gold). A stronger text matcher widens the gap between
"text that mentions the skill" and "proof of having done the project". The corrective loop (V8)
refused 41% of gap-skip jobs but also 35% of real bid jobs [`rag_v8_filter.json`]: too blunt to
replace the fit matcher's gap check.

**Shipped choice:** `rag.variant: v2_filter` (portfolio-type filter + BM25/dense hybrid with RRF).
It has the best Recall@5, MRR and nDCG@10 and is as fast as V0.

**Deployed embedder.** The 512 MB host cannot run torch, so the deployment uses bge-small through
fastembed. On the same 95 jobs, that scored *slightly higher*: Recall@5 0.267, MRR 0.507, nDCG@10
0.364 [`rag_v2_filter_bge_small_en_v1_5.json`]. One run, so I read it as "no worse", not better.

**Claim verification, before and after** (15 gold-bid jobs, 14 drafted): claims per proposal 6.14 →
2.29 and unsupported claims 3.86 → 0.00 [`proposals_openai_gpt-oss-120b.json`]. The wider verifier
(present-tense habits like "I routinely…", screening answers; commit `3a4b161`) finds about twice
as many claims as the first version, and most of the new ones are unsupported. Two submitted drafts
were left with **no** grounded claim (`291e4ff84d9094f0`, `031cbf7ac05d13a6`). Compliance now blocks
those (`no_grounded_claims`, commit `6e08661`), but I did not re-run the eval after that change.

**Not done:** the calibrated LLM judge (no Cohen's kappa yet), the human pairwise panel, and the
GigSim reply rate per variant. The GigSim first-reply rate of the current pipeline is 3 / 9 = 0.33
on seeded rule-only clients, too few proposals to say anything about variants.

# 5. RQ-C: is the multi-agent design worth it?

The brief asks for 50 dev jobs and three designs. I ran the single ReAct agent on 2 jobs and did
**not** run the prebuilt supervisor, so this is a limited comparison.

| | Single ReAct agent, 9 tools (gpt-oss-120b) | Hand-built graph |
|---|---|---|
| Jobs | 2 [`single_agent_demo.json`] | 90 decisions [`decisions_qwen3_4b.json`], 15 proposals |
| Bid/skip on the same 2 jobs | 1 / 2: drafted for a WordPress job (a listed gap, gold skip) | 2 / 2 [`decisions_qwen3_4b_jobs.json`] |
| Injection followed | no, flagged | no; 100% detection, 0% false positives on the sample |
| Invented experience | yes: "fine-tuned a Transformer on … historical letters and speeches", cited to a clinical-notes case study | 0.00 unsupported claims per proposal after verification |
| Tokens per job | 29,654 and 19,824 | 2,388 per job analysed; 9,039 per proposal |
| Latency | 164 s and 73 s | p50 88 s, p95 354 s per proposal |

On these two jobs the graph was right where the single agent was wrong, and the single agent's
invented claim became the verifier's regression test (`test_verifier_catches_p08_fabrication`).
But two jobs cannot show where a single agent wins. Its natural advantage is fewer hand-offs on
simple, well-matched jobs, and I have not measured that. Next: run all three designs on the same 50
jobs with the same writer model, and compare bid/skip accuracy, unsupported claims, compliance
catches, tokens and latency.

# 6. The change request

*To be filled after the measured change request (section added last).*

# 7. Signature extension

Not done. I spent the time on the evaluation, durability and the change request instead. The
closest groundwork is the outcome memory (reply rates per job category), which an A/B proposal
experiment (X2) would build on.

# 8. Failure analysis

Twelve failed dev jobs from the result files, grouped into the brief's taxonomy:

| Job | Category | What happened | Fix tried | Worked? |
|---|---|---|---|---|
| `18c1125f8c509df4` lawyer in the UK | wrong bid | fit 0.60 hit the bid threshold on generic AI words; gold has 0 matching skills | none yet; candidate: require 2+ strong requirement matches | open |
| `2ca989d14cda9f6b` lead-gen / cold email | wrong bid | fit 0.60 from loosely matching evidence | same | open |
| `6c9ded7f61c2a9d9` email lead capture | wrong bid | fit 0.75 | same | open |
| `fe3ce9f8d61b2885` full-stack trainer | wrong bid | teaching job, fit 0.62 on stack words | same | open |
| `0410383b08f37e1f`, `3723a499e4d24915`, `356920dbcef774b5` | wrong bid (with injection) | each carries a planted injection that was flagged and **not** followed; the job was still off-topic | injection never steers the decision by design; the miss is fit | partly |
| `415b827d69fc3d75` Kibana dashboard | wrong skip (watch) | fit 0.50, inside the watch band; gold bid | watch goes to a human, so nothing is lost | acceptable |
| `22da285bce53b433`, `2298deadbfaf9fad`, `27d97376f2ac1781` | tool error | the fallback writer (qwen3:8b) returned the JSON schema instead of filling it | retry with the validation error, then fallback; status `needs_attention` | no (Groq quota is the root cause) |
| `291e4ff84d9094f0`, `031cbf7ac05d13a6` | unsupported claim | every claim was unsupported and removed, and the empty-of-proof draft was submitted | `no_grounded_claims` compliance block (`6e08661`) | yes, by code; not re-run |
| `03fdb39475cfadc3` | compliance error | "ensure data integrity" read as a guarantee and blocked | narrower borderline terms | partly |
| `1c0b990bb7dbe947` | compliance error | "a WhatsApp and SMS assistant" (a real project) blocked as off-platform | — | open |
| `03fdb39475cfadc3`, `0cd6b5727da68d65`, `16e6b1dc6d5fc66f` | missed evidence | Recall@5 = 0 with the shipped retriever; 20 of 95 bid jobs score 0 [`rag_v2_filter.json`] | type filter + hybrid (87 jobs at 0 in V0) | partly |

[`decisions_qwen3_4b.json`, `proposals_openai_gpt-oss-120b.json`, `rag_v2_filter.json`]. Not seen
in these files: **mispriced** (prices in band on 30 / 30 priced gold-bid jobs), **successful
injection** (0 followed), and **generic opening** as a final failure. The Critic flags generic
openers, but 10 of 14 drafts ended `critic_unresolved`, mostly on length and screening answers.

**Two earlier failures that changed the system.** (1) Until commit `702812d`, every persona
searched the ai_ml portfolio because in-process MCP sessions carried no user. Bid F1 for 4B rose from 0.750
to 0.870 after the fix [`decisions_qwen3_4b_tenant_bug.json`]: most of the 4B-vs-8B gap was retrieval against the wrong portfolio. (2)
Small models over-flag. On 72 non-scam jobs, qwen3:8b raised `off_platform` 42 times and `scam`
19 times (qwen3:4b: 3 and 0) [`decisions_qwen3_8b.json`, `decisions_qwen3_4b.json`]. With
model-only flags allowed to skip, scam precision was 0.277 for 8B and 0.692 for 4B
[`decisions_qwen3_*_model_flags_skip.json`]. A model-only skip flag now needs a rule to back it
(`decision.model_flags_need_rule`, commit `985aa5e`).

# 9. Safety and platform respect

**What GigBid must never do, and how it is enforced.**

- **Send or spend without a human:** interrupts, a typed `auto_send: Literal[False]`, and an
  idempotency key on every write. The crash test shows one submission and one charge.
- **Follow injected instructions:** job and client text are wrapped in `<untrusted>` tags that the
  text cannot close; injection is a flag, never a decision input, and it cannot corroborate a skip.
  It was detected on 100% of planted injections with 0% false positives on the 90-job sample.
- **Claim what is not in the portfolio:** the verifier plus the `no_grounded_claims` block.
- **Contact details, guarantees, off-platform payment:** the Compliance Guard on
  `data/policy_pack/policy_rules.yaml`.
- **Leak secrets or personal data:** the CI repo check blocks committed keys; masked tracing
  (commit `59b6c73`); per-user tenant scoping (commit `702812d`).
- **Scrape or overload a platform:** marketplace access only through the port and its rate limiter,
  no scraping, and Upwork only through its official MCP server.

**What still gets through.** Scam recall of 1.0 is partly circular: I wrote the rule patterns with
my own scam templates in view. The six held-out injection styles (base64, HTML comment, Spanish,
fake tool JSON, homoglyphs, role-play; `evals/datasets/injection_holdout/`) have **not** been run
against the defences yet. Compliance both over-blocks (two false blocks above) and depends on
patterns that a paraphrase can avoid.

# 10. Budgets: declared vs measured

| Budget | Declared | Measured | Source | Met? |
|---|---|---|---|---|
| p95 latency per job analysed | 20 s | 54.5 s live (p50 25.9 s), qwen3:4b on a laptop | `decisions_qwen3_4b.json` at `ac46ff7` | no |
| cost per job analysed | $0.002 | $0.000008 | same | yes |
| p95 latency per proposal | 60 s | 354.3 s (p50 87.5 s) | `proposals_openai_gpt-oss-120b.json` | no |
| cost per proposal | $0.01 | $0.000205 | same | yes |

Cost is far under budget because the open models are local or on free tiers. Latency is far over,
for one main reason: Groq's free tier limits tokens per minute, so 12 of 14 drafts fell back to a
local qwen3:8b and waited on rate limits. The optimisation that helped most was skipping early:
`decide` stops before pricing and writing on skip/watch, and a cached analysis makes reruns cost
nothing. **The hidden test run is pending**; I will add its numbers here without excuses.
