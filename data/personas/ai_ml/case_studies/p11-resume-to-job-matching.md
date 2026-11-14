# Resume to Job Matching for Hireloop

I worked with Hireloop, an HR tech company, on a system that helps recruiters find strong candidates by matching a job description against a large resume library. The challenge was to turn a growing collection of 210k resumes into a fast, reliable retrieval flow that could surface relevant people quickly and stay up to date as candidate profiles changed.

My focus was on building the matching layer end to end. I used Python with `sentence-transformers` to generate embeddings for resumes and job descriptions, then stored and queried those vectors in Qdrant. The core idea was to represent both sides of the search in the same embedding space so the system could rank resumes by closeness to the job description, rather than relying only on exact keyword overlap.

To keep the experience responsive, I exposed the matching service through FastAPI and wired profile refreshes through Celery workers. Whenever a resume was updated, the affected record was re-embedded asynchronously and written back to the index, so recruiters were always searching against current data without blocking the main application flow.

A simplified version of the approach looked like this:

```python
from fastapi import FastAPI
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

app = FastAPI()
model = SentenceTransformer("all-MiniLM-L6-v2")
qdrant = QdrantClient(url="http://localhost:6333")

def embed(text: str):
    return model.encode(text).tolist()

@app.post("/match")
def match(job_description: str):
    vector = embed(job_description)
    return qdrant.search(collection_name="resumes", query_vector=vector, limit=10)
```

The result was a measurable improvement in retrieval quality. On 300 labelled searches, recall@10 increased from 0.72 to 0.86 after the system was tuned and integrated into the Hireloop workflow. That gave recruiters a much better chance of seeing strong candidates near the top of the list, while keeping the index maintainable as new information came in.

This was a fixed engagement from 2024-03 to 2024-05, and it was a good example of combining LLM-era embedding methods with production ML design to solve a practical hiring workflow problem.
