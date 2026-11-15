# gigbid-portfolio-mcp

A small, read-only MCP server that lets Claude Desktop, Cursor or any MCP client search **your own
portfolio folder** for proof: case studies, repo READMEs, code, client reviews, a CV and (only when
you ask) past proposals. It is the standalone version of the Portfolio server inside
[GigBid](https://github.com/muqarrab-k/GigBid-A-Multi-Agent-Freelancer-Copilot).

- **No API keys, no model download.** Search is BM25 over paragraph chunks, best chunk per item.
- **Proof first.** Past proposals are left out of `search_evidence` unless you pass
  `types: ["proposal"]`. In GigBid's retrieval study, proposals crowded out real evidence
  (Recall@5 0.023 with them, 0.235 without; `evals/results/rag_results_table.md`).
- **Read-only.** Every tool is annotated `readOnlyHint: true`; nothing is written anywhere.

## Install

From GitHub with [uv](https://docs.astral.sh/uv/) (no clone needed):

```bash
PORTFOLIO_DIR=~/my-portfolio uvx --from "git+https://github.com/muqarrab-k/GigBid-A-Multi-Agent-Freelancer-Copilot#subdirectory=mcp_servers/portfolio" gigbid-portfolio-mcp
```

With Docker (public image on Docker Hub, linux/amd64 and linux/arm64):

```bash
docker run -i --rm -v ~/my-portfolio:/portfolio:ro mmuq/gigbid-portfolio-mcp
```

Both start an MCP server on stdio. Add `--http --host 0.0.0.0 --port 8103` for Streamable HTTP
(with Docker also `-p 8103:8103`).

## Claude Desktop / Cursor config

`claude_desktop_config.json` (Claude Desktop) or `.cursor/mcp.json` (Cursor):

```json
{
  "mcpServers": {
    "portfolio": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/muqarrab-k/GigBid-A-Multi-Agent-Freelancer-Copilot#subdirectory=mcp_servers/portfolio",
        "gigbid-portfolio-mcp"
      ],
      "env": { "PORTFOLIO_DIR": "/Users/you/my-portfolio" }
    }
  }
}
```

Or with Docker:

```json
{
  "mcpServers": {
    "portfolio": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "/Users/you/my-portfolio:/portfolio:ro", "mmuq/gigbid-portfolio-mcp"]
    }
  }
}
```

## Your portfolio folder

Any folder works. Every text file becomes one evidence item (id = its path):

| file | evidence type |
|---|---|
| `case_studies/*.md` | `case_study` |
| `README*` | `readme` |
| `cv.*`, `resume.*` | `cv` |
| `*.py`, `*.ts`, `*.sql`, `*.yml`, ... | `code` |
| `reviews.jsonl` (one `{"text": ...}` per line) | `review` |
| `proposals.jsonl` (`proposal_text`, `job_title`, `outcome`) | `proposal` |
| anything else (`.md`, `.txt`) | `document` |

An optional `manifest.jsonl` adds metadata per path (`evidence_id`, `type`, `project`, `date`,
`skills`, `client_industry`, `outcome`); `list_skills` reads skills from it. Try it on a synthetic
persona from this repo: `PORTFOLIO_DIR=data/personas/ai_ml`.

## Tools, resources, prompts

| name | kind | what it does |
|---|---|---|
| `search_evidence(requirement, k=5, types=None)` | tool | best matching items with type, source, project, date, outcome, score and a snippet |
| `get_case_study(case_id)` | tool | full case study by project id, evidence id or path |
| `get_evidence(evidence_id)` | tool | full text of any item |
| `list_skills()` | tool | skills from the manifest, with counts and projects |
| `portfolio://case/{id}`, `portfolio://proposal/{id}` | resources | full items for a host to load |
| `answer_screening_question`, `find_proof`, `pick_best_projects` | prompts | ready-made tasks that call the tools and cite evidence ids |

## Limits

BM25 matches words, not meaning: "async task queue" will not find a page that only says "Celery
worker". The full GigBid server adds dense embeddings (hybrid with reciprocal rank fusion, which
scored Recall@5 0.255 vs 0.235 for the filter alone) and pgvector, at the cost of a database and a
model.

Author: Muqarrab · i230511 · Section C. MIT license.
