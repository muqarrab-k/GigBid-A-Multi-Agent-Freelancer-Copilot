# Contract clause search assistant

Python app for searching clauses across 9,000 contracts and answering questions with quoted clause and page references.

## Setup

Install dependencies for Python, LangChain, OpenAI API, pgvector, PostgreSQL, and FastAPI.

Set up PostgreSQL with pgvector enabled, then configure your database and OpenAI credentials in the environment before running ingestion or query scripts.

## Usage

```bash
python ingest.py
python query.py
```

`ingest.py` splits contracts into clause chunks, keeps page numbers, and stores embeddings in pgvector.

`query.py` pulls the top matching clauses and prompts the model to answer only from those clauses with citations.

## Notes

This repository is designed for contract review workflows where the answer must point back to the exact clause and page used.

The system was checked on a lawyer-written 120-question set and produced faithful answers at a high rate. It also reduced clause lookup time from 25 minutes to 3 minutes.
