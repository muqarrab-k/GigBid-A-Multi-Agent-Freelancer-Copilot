# Three things my freelancer copilot taught me about "better" models and "better" retrieval

*Draft. Muqarrab, AI-4016. All numbers come from result files in the GigBid repository
(`evals/results/`), named in brackets.*

For a course assignment I built GigBid, a system of LangGraph agents that reads freelance job
posts, decides which ones are worth a bid, writes a proposal whose every claim should be backed by
my portfolio, and then stops and waits for a human before anything is sent. It runs against a
marketplace simulator I built from public Kaggle job and contract data, with three synthetic
freelancer personas and a hand-labelled dev set.

I went in with the usual instincts: a bigger model will judge better, a smarter retriever will find
better evidence, and asking the writer to cite its sources will keep it honest. All three were wrong
in ways I could measure. This post is about those three surprises, not about how to build the thing.

## 1. The bigger model was the worse risk assessor

GigBid's Risk Assessor looks at a job and its client and raises flags: scam, unpaid work,
off-platform contact, a vague scope, a low budget. Some flags come from plain rules (regular
expressions for "contact me on Telegram", a client with no payment method and a strange spend
history), and some come from one call to a small local model. I compared two sizes of the same
family, qwen3:4b and qwen3:8b, on a stratified sample of 90 dev jobs.

I expected the 8B model to be the safer pair of eyes. It was the more paranoid one. On the 72 jobs
in the sample that were *not* scams, the 8B model raised `off_platform` 42 times and `scam` 19 times.
The 4B model raised them 3 and 0 times [`decisions_qwen3_8b.json`, `decisions_qwen3_4b.json`]. It
also called almost everything vague (71 times) and cheap (70 times).

When those model-only flags were allowed to skip a job, scam precision was 0.277 for the 8B model
and 0.692 for the 4B [`decisions_qwen3_8b_model_flags_skip.json`,
`decisions_qwen3_4b_model_flags_skip.json`]. In plain words: of every four jobs the 8B model threw
away as scams, roughly three were real jobs. Recall was 1.0 for both, which sounds great until you
notice that a model that calls everything a scam also has perfect recall.

The bigger model was not dumber. It was more *cautious*, and caution in a classifier that gates
money is a cost, not a virtue. A wrongly skipped job is invisible: the freelancer never sees it,
never complains, and never knows they lost it. A wrongly approved job still stops at the human
approval screen, where the risk report shows the model's worry.

So I changed the rule, not the model. A skip flag raised only by the model now counts only when a
rule signal backs it, such as a scam pattern or a client red flag. Injection detection is
deliberately not allowed to be that backing signal, so text planted in a job post cannot push a job
to skip by itself. On a fresh, disjoint sample, the rule lifted scam precision from 0.67 to 0.86 and
cost some bid F1 (0.879 to 0.841), because three jobs it let through were real skips. I kept it
anyway. In this product, a false skip is the worse error.

The smaller model also stayed: 0.870 bid F1 against 0.794 for 8B on the first sample, and about 40%
faster [`decisions_qwen3_4b.json`, `decisions_qwen3_8b.json`].

## 2. Reranking and query decomposition made retrieval worse; a type filter did the work

The second surprise was in retrieval, where I had a hypothesis written down before running anything:
splitting a job post into its requirements, mixing keyword search with dense search, and reranking
with a cross-encoder should each add points, especially on jobs that ask for four or more things.

The baseline was dreadful, and the reason was interesting. A plain dense search over the whole
portfolio, using the whole job post as the query, scored Recall@5 0.023 on 95 dev bid jobs
[`rag_v0.json`]. In 448 of the 475 top-5 slots it returned **past proposals**. That makes sense once
you see it: a proposal is written in reply to a job post, so it reads like a job post. Proposals were
70% of all chunks. My retriever was very good at finding text that sounded like the query, and very
bad at finding proof.

One line of configuration fixed most of it: search only portfolio types (case studies, READMEs,
reviews, code, the CV) and ask for proposals explicitly when you want phrasing. Recall@5 went from
0.023 to 0.235 [`rag_results_table.md`]. Adding BM25 to dense search with reciprocal rank fusion took
it to 0.255, with MRR 0.475. That is what shipped.

Then the "smarter" parts went backwards:

- **Requirement decomposition** dropped Recall@5 from 0.235 to 0.147, even on the jobs with four or
  more requirements, where it was supposed to shine. Short queries like "experience with Python"
  matched short, skill-dense client reviews best. Reviews took 232 of the 475 top-5 slots, against
  110 gold items.
- **Cross-encoder reranking** dropped it to 0.132 and made the search about 90 times slower (p50
  5.9 s against 64 ms). The reranker loved code chunks, which mention every library by name: 86 top-5
  slots against 3 gold code items.

Both failures have the same root. My gold labels mark *project-level proof* as relevant: the case
study and README that show I built the thing. A stronger text matcher rewards *text that mentions the
skill*. Making that matcher better widens the gap instead of closing it. The hypothesis was rejected;
the ablation shows the type filter alone accounts for almost the whole gain over the baseline
[`rag_ablation.json`].

A side note I enjoyed: the deployed app runs on a 512 MB host, so it uses a much smaller embedding
model (bge-small via ONNX) instead of nomic-embed. On the same 95 jobs it scored slightly *higher*,
0.267 against 0.255 [`rag_v2_filter_bge_small_en_v1_5.json`]. Once the filter removes the
proposals, what is left is a small, clean corpus, and the size of the embedding model barely matters.

## 3. A citation on every sentence did not stop invented claims

The third surprise is the one I think matters most outside this project.

The writer prompt says every factual sentence must end with evidence ids. The model complied,
beautifully. My first single-agent baseline, given all the tools and a job about a historical-figure
chatbot, wrote: "I fine-tuned a Transformer on domain-specific corpora of thousands of historical
letters and speeches, achieving high fidelity to the source style [ai_ml:case_study:p08]"
[`single_agent_demo.json`]. Case study p08 is about summarising clinical notes. There were no letters
and no speeches. The citation was real; the claim was invented, and the citation made it *look*
checked.

The full pipeline does the same thing, just less visibly. With writer prompt v4, drafts contained
6.14 claims per proposal, and 3.86 of them were unsupported by the evidence they cited
[`proposals_openai_gpt-oss-120b.json`]. Many were habits rather than lies, like "I routinely design
conversational flows", which sound harmless and are exactly what a careful client would ask about.

What worked was a separate verifier that does not trust the writer. It splits the draft into claims,
checks that every cited id exists, that every number and name in the claim appears in the cited
text, and only then asks a small model about the borderline cases. Unsupported claims are removed
before the Critic ever sees the draft. After verification: 0.00 unsupported claims per proposal.

But removing claims creates its own failure. Two drafts lost *every* claim and were still submitted,
polite and empty of proof. The fix was one more rule: Compliance now blocks a draft with no
evidence-backed claim left. A citation is a promise. Without a verifier it is decoration, and
without a floor on what survives, verification can leave you with a well-formatted nothing.

## What I would do next

- **Measure the single agent properly.** I compared it with the graph on 2 jobs. That was enough to
  catch a fabrication, not enough to say where a single agent wins. The next step is the same 50 jobs
  for a single ReAct agent, a prebuilt supervisor and my graph, with the same writer model.
- **Calibrate a judge.** Proposal quality is still measured only by rules and a simulator with
  seeded clients. I want 30 hand-labelled proposals and a Cohen's kappa before I trust any LLM judge.
- **Fix fit, not risk.** Most remaining wrong bids come from a fit score that rewards loosely related
  evidence: a UK lawyer job scored 0.60 on generic AI words. Requiring two strong requirement matches
  is my first candidate.
- **Attack my own defences.** I held out six injection styles (base64, HTML comments, Spanish, fake
  tool output, homoglyphs, role-play) that were never in the dev set. They have not been run yet.
  That is the test I most want to see fail, so I can see how.

The lesson I keep coming back to: in each case the better-sounding component made the system
worse by its own metric, and only the measurement showed it.
