# Architecture

GigBid is a set of LangGraph agents that reach the outside world only through our MCP servers.
This page covers the marketplace and tool layer, retrieval, and the full bid graph: analysis,
writing, claim verification, Critic, Compliance, the human approval interrupt and submission,
with Postgres checkpoints.

```
agent node -> agent/mcp_client.py (allowlist, trace_id, retries) -> our MCP server
           -> MarketplacePort -> GigSim adapter (live Upwork later)
                              -> Portfolio retriever (RAG variant over pgvector)
```

## Bid graph (`agent/graphs/bid_graph.py`)

Rendered from code (`make graph-render` writes `docs/images/bid_graph.mmd`):

```mermaid
graph TD;
	__start__([<p>__start__</p>]):::first
	intake(intake)
	analyst(analyst)
	risk_assessor(risk_assessor)
	fit_matcher(fit_matcher)
	join(join)
	decide(decide)
	pricing(pricing)
	writer(writer)
	verifier(verifier)
	critic(critic)
	compliance(compliance)
	prepare_approval(prepare_approval)
	approval_gate(approval_gate)
	apply_edit(apply_edit)
	reject(reject)
	submit(submit)
	__end__([<p>__end__</p>]):::last
	__start__ --> intake;
	analyst --> join;
	apply_edit --> verifier;
	approval_gate -.-> apply_edit;
	approval_gate -.-> reject;
	approval_gate -.-> submit;
	compliance -. &nbsp;end&nbsp; .-> __end__;
	compliance -.-> prepare_approval;
	critic -.-> compliance;
	critic -.-> writer;
	decide -. &nbsp;end&nbsp; .-> __end__;
	decide -.-> pricing;
	fit_matcher --> join;
	intake -.-> analyst;
	intake -.-> fit_matcher;
	intake -.-> risk_assessor;
	join -. &nbsp;stop&nbsp; .-> __end__;
	join -.-> decide;
	prepare_approval -. &nbsp;end&nbsp; .-> __end__;
	prepare_approval -.-> approval_gate;
	pricing --> writer;
	risk_assessor --> join;
	verifier -.-> compliance;
	verifier -.-> critic;
	writer -. &nbsp;end&nbsp; .-> __end__;
	writer -.-> verifier;
	reject --> __end__;
	submit --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

One thread per job. `intake` fans out with `Send` to three nodes that run in parallel, `join`
waits for all three and enforces the step and token budgets, `decide` applies the rules, and
only `bid` continues to `pricing` and then to the proposal half below.

| node | job | model | tools (allowlist) |
|---|---|---|---|
| analyst | JobSpec: deliverables, requirements, skills, budget, timeline, screening questions, hidden needs | cheap (qwen3) | none |
| risk_assessor | client quality from public history, scam / unpaid work / off-platform / injection flags; rules plus the model, every fired signal recorded | cheap (qwen3) | marketplace read |
| fit_matcher | its own requirement list, `search_evidence` per requirement, requirement-to-evidence matrix, fit score minus persona gaps | cheap (qwen3) + retriever | portfolio read |
| decide | skip / watch / bid from `decision` and `thresholds` in `agent/config.yaml`, with reasons | none (rules) | none |
| pricing | bid amount from market stats, client spend and the persona floor; whether the Connects cost is worth it | none (rules) | marketplace read incl. `get_market_stats` |
| scout (script) | saved searches, dedupe by job id and content hash; each new job starts its own thread | none | marketplace read |

**Decision rules** (first match wins, every fired rule is a reason): injected instructions are
flagged and never steer the decision (`injection_action: flag`); risk flags in `skip_flags`
(scam, unpaid work, off-platform) skip; risk above `maximum_risk_score` skips; a failed fit
analysis goes to watch for a human; a persona gap skips; a budget under the persona floor skips;
Connects above the per-job limit watches; then fit decides: `>= minimum_fit_score` bid,
`>= watch_fit_score` watch, else skip. A policy change is a config edit.

**Design trade-off: duplicated requirement extraction.** The analyst and the fit matcher both
pull requirements out of the job post. The fit matcher cannot wait for the analyst without
breaking the required parallelism, so it runs its own short extraction tuned for portfolio
search phrases. Cost: one extra small-model call per job (about 300 tokens) and two requirement
lists that can disagree. Benefit: the three branches stay independent and the slowest one sets
the latency. If they drift, the writer should use the analyst's list for the proposal and the
fit matrix only as evidence.

**Market stats.** GigSim is frozen and has no statistics endpoint, so `get_market_stats` on the
marketplace server serves `data/processed/pricing_stats.json` (made by `make data` from the
Kaggle jobs and contracts) and labels the source in every answer.

## Proposal half: writer to submit

| node | job | model | tools |
|---|---|---|---|
| writer | `ProposalDraft` in short paragraphs; every factual sentence ends with evidence ids; opens with the client's problem; screening answers; price from `PriceQuote`; on a revision it gets the Critic's reasons and the claims the verifier removed | strong (`writer` in config), local fallback | portfolio read incl. `get_evidence` |
| verifier | `rag/verify.py`: one claim per factual sentence; deterministic checks first (cited ids exist, every number and name appears in the cited evidence, key-word coverage), small-model judge only for the middle band; unsupported claims are removed before the Critic; before/after counts in `verification` | cheap | portfolio read |
| critic | rules: claims removed by the verifier, fewer than 2 grounded claims, generic opener, first paragraph not using the job's terms, length outside `writer.min_words..max_words`, missing screening answers. Pass or revise with reasons; at most `budgets.max_revisions` (2) rewrites, then the best draft goes on with a visible `critic_unresolved` note | none (rules) | none |
| compliance | `data/policy_pack/policy_rules.yaml` patterns and keywords for contact details, off-platform, guarantees, unpaid work, credentials; fabrication from the verifier's `unsupported_after`; fewer than `compliance.min_grounded_claims` (1) evidence-backed claims left; the small model only for sentences with borderline words (`compliance.borderline_terms`). Any violation blocks (`compliance.clean_rules: []`); `cleaned_text` shows the draft without the flagged sentences | cheap, borderline only | none |
| prepare_approval | dry runs of `create_proposal_draft` and the Connects balance; payload: draft (with and without tags), claim table with evidence, risk report, price rationale, cost and balance after, verifier/critic/compliance notes | none | `approval` allowlist |
| approval_gate | `interrupt(payload)`; resume with `Command(resume={"action": "approve" \| "edit" \| "reject", ...})` | human | none |
| apply_edit | the human's text replaces the draft, a unified diff goes to `pending_edits` (style memory later); then verifier (report only, a human's words are never rewritten) and Compliance run again and the gate interrupts again | none | none |
| reject | records the reason in `submission` and ends with status `rejected` | none | none |
| submit | `create_proposal_draft` then `submit_proposal`, both through the marketplace MCP server, idempotency key `thread_id:sha256(draft, answers, price)`; marketplace down means status `queued`, never a crash | none | `approval` allowlist |

**Autonomy.** `autonomy.auto_skip_low_fit` lets the graph skip low-fit jobs on its own (off turns
those into `watch`). `autonomy.auto_send` is typed `Literal[False]`: a config that sets it to true
fails to load, and `submit` raises unless the stored approval says `approve`. The proposal eval
uses an auto-approver that lives only in `evals/runners/proposal_eval.py`.

**Durability.** Real runs use `AsyncPostgresSaver` in schema `langgraph`
(`agent/graphs/checkpoint.py`, `checkpointer` in config); tests use the in-memory saver. Only
our hand-off models may be deserialised from a checkpoint. `invoke` retries a failing thread
from its last checkpoint up to `nodes.max_attempts` (3) times, then marks it `dead_letter` with
every error. `make replay THREAD=<id> NODE=<name>` forks a thread from the checkpoint before a
node against a scratch GigSim. `make crash-resume` kills the process while it waits for approval
and again right after `submit_proposal` returns, then restarts; results in
`evals/results/crash_resume.json`.

## State, execution trace and long-term memory are separate

- **State** (`agent/state.py`, `BidState`): what this job needs right now: the raw job, the
  hand-offs (JobSpec, RiskReport, FitReport, BidDecision, PriceQuote), evidence, status, and
  the step and token counters. Fields that parallel branches write use reducers (evidence merges
  by id; counters, errors, failed hand-offs and trace events add up), so the three branches never
  clash. Checkpointed by `MemorySaver` for now, Postgres next.
- **Execution trace** (`state["trace"]` plus the MCP servers' audit logs): append-only events for
  every LLM call (model, attempt, tokens, latency, USD, cache hit) and tool call (name, args, ok,
  latency), all under one `trace_id` that also reaches the audit logs through MCP request meta.
  It is for audit and debugging; nodes never read it to decide anything.
- **Long-term memory** (next task, LangGraph store): only promoted knowledge (style and outcome
  memory) written by an explicit rule in `agent/memory/promotion_rules.py`. Raw tool output and
  trace events never go there.

## Node plumbing (`agent/nodes/common.py`)

- Every prompt is a versioned file in `agent/prompts/` (`analyst.v1.md`, `risk_assessor.v1.md`,
  `fit_matcher.v1.md`, plus `untrusted_rule`, `json_output`, `json_retry` fragments).
- `untrusted()` wraps job and client text in `<untrusted>` tags with the standard data-only rule;
  the text cannot close the block itself.
- `structured()` asks for JSON (JSON mode, qwen3 thinking off), validates against the node's
  Pydantic model, retries once with the validation error, then tries the fallback model; if all
  fail, the hand-off is listed in `failed` and the graph continues.
- An LLM cache keyed by model and full prompt makes eval reruns free and reproducible.
- `ToolBox` gives a node only its allowlisted tools and logs each call to the trace.

## Measured so far (decision eval, 90-job stratified dev sample)

`make decision-eval` and `make decision-eval MODEL=qwen3:8b`. Fallback model: Groq
`openai/gpt-oss-20b`. Live latency and tokens come from the first live runs (commit `0442e4d`,
2,388 tokens and 25.9 s / 54.5 s p50 / p95 per job for 4B; 44.4 s / 73.2 s for 8B); the rows below
replay the cached model replies, so only retrieval and `decide` ran again.

**Correction (2026-11-15).** Until commit `702812d`, in-process MCP sessions carried no user, so
every persona searched the ai_ml portfolio and used the ai_ml GigSim account. Fit scores for
data_analyst and fullstack were wrong. Those files are kept with a `_tenant_bug` suffix (and the
older `_model_flags_skip` files have the same problem); the table uses the re-runs.

| cheap nodes | sample | rule set | bid F1 | scam P / R | injection detected / false pos. | price in band | file |
|---|---|---|---|---|---|---|---|
| **qwen3:4b** | first | flags need a rule | **0.870** | 1.00 / 1.00 | 100% / 0% | 30 / 30 | `decisions_qwen3_4b.json` |
| qwen3:8b | first | flags need a rule | 0.794 | 0.90 / 1.00 | 100% / 0% | 25 / 25 | `decisions_qwen3_8b.json` |
| qwen3:4b | fresh | model flags skip | 0.879 | 0.67 / 1.00 | 100% / 0% | 25 / 29 | `decisions_qwen3_4b_fresh_corroboration_off.json` |
| qwen3:4b | fresh | flags need a rule | 0.841 | 0.86 / 1.00 | 100% / 0% | 25 / 29 | `decisions_qwen3_4b_fresh_corroboration_on.json` |

Before the fix the first-sample 4B F1 was 0.750 and 8B 0.571: most of the gap was retrieval
against the wrong portfolio, not the models.

**What changed.** The small models over-flag: on the 72 non-scam jobs the 8B model added
`vague_scope` 71 times, `low_budget` 70 times and `off_platform` 42 times (4B: 28, 15 and 3).
With `decision.model_flags_need_rule: true`, a skip flag that only the model raised counts only
when a rule signal backs it (a scam, unpaid-work or off-platform pattern, or a client red flag
from `decision.corroborating_signals`). Injection detection is deliberately not a corroborating
signal, so injected text cannot push a job to skip by itself.

**Caveats.** Scam recall of 1.0 is partly circular: the rule patterns were written with our
scam templates in view. Per persona (first sample, 4B) F1 is 0.88 ai_ml, 0.86 data_analyst,
0.87 fullstack. qwen3:4b stays the cheap-node model: better on every metric and about 40% faster
than 8B.

**Check on a fresh sample.** `--fresh` draws a second stratified 90-job sample with seed 43,
disjoint from the first; `--corroboration off|on` overrides the rule. Both fresh runs use the
same cached model replies, so only `decide` differs. Four decisions changed, all on gold-skip
jobs: one moved to watch and three to bid. On unseen jobs the rule removes false scam calls
(precision 0.67 to 0.86, recall unchanged) but costs bid F1 (0.879 to 0.841), because the three
jobs it let through are real skips. The +0.06 F1 on the first sample was tuning to that sample.
We keep the rule: a wrong scam skip hides a real job from the user for good, while a wrong bid
still stops at the human approval gate, where the risk report shows the model's flag.

## Measured so far (proposal eval, 15 bid jobs)

`make proposal-eval` on 15 gold-bid jobs the graph also bid on (5 per persona), writer
`openai/gpt-oss-120b` on Groq with local `qwen3:8b` as fallback, verifier and compliance on
`qwen3:4b`. Approval comes from an auto-approver that exists only in the eval runner. Approved
drafts went to an in-process GigSim (dev scenario, rule-only clients), which then ticked 168 hours.
File: `evals/results/proposals_openai_gpt-oss-120b.json`.

Writer prompt v4 and the wider verifier (present-tense experience claims, screening answers)
are the current run; the v3 column is the run before that change (same file at commit `e534d81`).

| metric | v4 + wider verifier | v3 (`e534d81`) |
|---|---|---|
| drafted / submitted / blocked by compliance / writer failed | 14 / 9 / 3 / 3 | 14 / 7 / 5 / 3 |
| claims per proposal before / after verification | 6.14 / 2.29 | 2.93 / 2.14 |
| unsupported claims per proposal before / after verification | 3.86 / 0.00 | 0.79 / 0.00 |
| critic rewrites per proposal (0 / 1 / 2) | 4 / 0 / 10; 10 `critic_unresolved` | 4 / 1 / 9; 7 `critic_unresolved` |
| compliance violations caught | 3 (off-platform 2, guarantees 1) | 8 (guarantees 5, off-platform 2, fabrication 1) |
| tokens / cost per proposal (writer, verifier, critic, compliance) | 9,039 / $0.0002 | 7,728 / $0.0003 |
| latency per job p50 / p95 (whole graph, cached analysis) | 87.5 s / 354.3 s | 72.8 s / 223.3 s |
| first reply rate after 168 h (replied or interview / submitted) | 3 / 9 = 0.33 | 3 / 7 = 0.43 |

**Read with care.** Groq's free tier limits tokens per minute and per day, so 12 of 14 drafts
(v3: 13 of 14) were written wholly or partly by the `qwen3:8b` fallback, not the configured
120B model. The three writer failures in each run are the 8B model returning the JSON schema
instead of filling it in. The wider verifier finds about twice as many claims, and most of the
new ones are unsupported habits ("I routinely...") or screening-answer claims; after removal the
grounded count barely moves (2.29 vs 2.14). Two submitted v4 drafts were left with no grounded
claim at all (`291e4ff84d9094f0`, `031cbf7ac05d13a6`, both `claims_after: 0`). Compliance now
blocks such drafts (`no_grounded_claims`), so under the current code this run would submit 7, not
9; the eval was not re-run for this change. In v3 most compliance
blocks were the small model reading "ensure" as a guarantee. The reply rate comes from GigSim's
seeded rule-only clients on 7 to 9 proposals and says little about real clients.

**Gaps closed.** Present-tense and "I have experience" sentences now count as claims, and
screening answers go through the same checks; an answer emptied by the verifier stays empty so
the Critic asks for it again. Tests: `test_untagged_present_tense_claim_is_removed`,
`test_screening_answers_are_verified`.

### Example (job `1c0b990bb7dbe947`, writer `gpt-oss-120b`, submitted in the v3 run)

> You need a prototype AI chatbot that can convincingly simulate conversations with a chosen
> historical figure. I understand that the model must capture the figure's voice, manage context
> across turns, and stay accurate to the source material.
>
> I have built a messaging-app support bot that handled multi-step dialogues, used the OpenAI API,
> LangGraph, FastAPI and Redis for state management, and integrated entity recognition and
> sentiment analysis. The solution resolved 43 % of interactions without a human and earned a CSAT
> of 4.4 /5, demonstrating effective context handling and user satisfaction.
>
> My core competencies include Python, PyTorch, OpenAI API, LangChain and cloud deployment on AWS
> with Docker, as documented in my CV. I routinely design conversational flows, train large
> language models on custom corpora, and monitor performance for continuous improvement.
>
> My rate is $55 per hour, and I am ready to start building, training and deploying the
> historical-figure chatbot on your preferred cloud platform.

| claim | evidence | label |
|---|---|---|
| built a messaging-app support bot … OpenAI API, LangGraph, FastAPI, Redis … entity recognition, sentiment | `ai_ml:case_study:p09` | supported |
| resolved 43 % without a human, CSAT 4.4/5 | `ai_ml:review:19` | supported |
| Python, PyTorch, OpenAI API, LangChain, AWS, Docker per the CV | `ai_ml:cv` | supported |

Price $55/h (market p25-p75 $27-$54, client up to $74, fit 0.90); dry run: 12 Connects,
balance 80 → 68, platform policy check passed. Under the wider verifier the untagged "I routinely
design conversational flows, train large language models..." sentence would now be removed. The invented "historical letters and speeches
[p08]" claim from the single-agent baseline on this job is the verifier's regression test
(`test_verifier_catches_p08_fabrication`).
