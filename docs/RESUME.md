# Résumé bullet

- Built **GigBid**, a LangGraph multi-agent freelancer copilot (3 MCP servers, Postgres checkpoints, human-approval gate): reached **0.87 bid-or-skip F1** on a 90-job dev sample and cut unsupported proposal claims from **3.86 to 0.00 per proposal** with an evidence-checking verifier.
- Raised portfolio retrieval **Recall@5 from 0.023 to 0.255** by filtering out past proposals and adding BM25/dense hybrid search, and showed cross-encoder reranking (0.132) and query decomposition (0.147) made it worse; published the Portfolio MCP server via uvx and Docker Hub.

Sources: `evals/results/decisions_qwen3_4b.json`, `evals/results/proposals_openai_gpt-oss-120b.json`,
`evals/results/rag_results_table.md`.
