# ADR 0003: pgvector in our Postgres, an open embedder on CPU

- Status: accepted (2026-11-14)
- One Postgres (pgvector image) holds the portfolio chunks (schema `rag`) and will hold the LangGraph checkpointer (schema `langgraph`). One service to run, back up and deploy instead of a separate vector database.
- At about 1,000 chunks per three personas we use exact cosine search (no ANN index). It is about 66 ms p50 per query including the embedding, and exact search keeps V0 an honest baseline with no recall lost to approximation. An HNSW index is one SQL statement if the corpus grows.
- Embeddings: nomic-embed-text v1.5 via sentence-transformers on CPU (768-d, query/document prefixes), as the brief requires open models. Fallback bge-small-en-v1.5 for low-memory hosts and an Ollama option, all chosen in `rag.embeddings`. Each embedder writes to its own table, so switching models never mixes vector spaces.
- nomic's remote model code needs transformers 4.x, so the `embed` extra pins sentence-transformers 5.7.0 with transformers 4.57.6.
- Tests use an in-memory numpy store and a deterministic fake embedder, so CI never needs Docker or model downloads.
