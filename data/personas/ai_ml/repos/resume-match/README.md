# Resume to job matching

Matching service for resume-to-job retrieval. Uses embeddings in Qdrant and a small FastAPI-facing search layer, with Celery handling resume re-indexing when profiles change.

## Setup

Install the Python dependencies for the worker and search service. Configure access to Qdrant and the embedding model used by `sentence-transformers`.

Relevant files:
- `embed_worker.py` for re-embedding changed resumes and upserting them into Qdrant
- `search.py` for querying Qdrant with a job description and applying simple filters

## Usage

```bash
# Rebuild embeddings for changed resumes
python embed_worker.py

# Search resumes for a job description
python search.py --job-description "Backend engineer with Python experience"
```

`embed_worker.py` is meant to run under Celery and processes profile updates as they arrive. `search.py` performs the query-time lookup path.

## Notes

- Built around Python, sentence-transformers, Qdrant, FastAPI, and Celery.
- The index contains 210k resumes.
- Search quality was validated on labeled queries during development, with improved top-10 retrieval over the baseline.
