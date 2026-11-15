# AI Usage Disclosure

## Tool

Claude Code (Anthropic), used as a coding assistant throughout the project. I remain responsible
for all code and every result in this repository.

## My role

- I wrote the requirements and the prompts for each stage of the build.
- I made the design and trade-off decisions:
  - the datasets: Kaggle jobs and contracts, plus labelled synthetic personas and clients;
  - the cut list under the deadline;
  - keeping qwen3:4b over qwen3:8b after the decision eval;
  - rejecting my own RAG hypothesis when the ablation did not support it;
  - choosing Render's free tier over paid hosting.
- I set up every account and key myself: Neon, Groq, OpenRouter, LangSmith, Hugging Face, Docker
  Hub and Render.
- I tested the app myself in the UI and reviewed results before committing them.

## What the assistant did

Under my direction it generated most of the implementation code, the tests and the first drafts of
the docs. It also ran the evals and deployments I asked for.

## Files it helped with

| folder | what |
|---|---|
| `agent/` | config, hand-offs, bid and conversation graphs, nodes, memory |
| `rag/` | ingest, index, retrieval variants, claim verifier, embedders |
| `mcp_servers/` | Marketplace, Portfolio and Workspace servers |
| `apps/` | FastAPI backend and React web app |
| `evals/` | runners and metrics (result files come from real runs) |
| `docs/` | first drafts of the architecture, runbook, report and blog |
| also | `gigsim/`, `synth/`, `data_pipeline/`, `infra/`, `scripts/` |

## Things it got wrong that I caught

1. **Hosting plan.** The plan assumed free Hugging Face Docker Spaces. Those now need a paid
   subscription, so we moved the deployment to Render's free tier.
2. **Embeddings.** The first fix for the 512 MB host used the Nomic embedding API, which turned out
   to be paid. The deployed embedder changed to bge-small through fastembed, with its own index, and
   the difference is written up in `docs/rag_notes.md`.
3. **Scam-flag fix.** The first fix for false scam flags was going to be tested on the same dev jobs
   that suggested it. I had it re-tested on a fresh, disjoint sample instead, where it cost some bid
   F1.
