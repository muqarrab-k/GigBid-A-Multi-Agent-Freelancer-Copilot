# ticket-router

Support ticket triage model for routing incoming helpdesk tickets into 14 queues.

## Setup

Python service with scikit-learn, FastAPI, Celery, Redis, and PostgreSQL.

Install dependencies, then configure the app to connect to Redis and PostgreSQL.

## Usage

Start the API and the Celery worker, then send a ticket payload to the route endpoint.

```bash
uvicorn app.api:app --reload
celery -A app.tasks worker --loglevel=info
```

Example request:

```bash
curl -X POST http://localhost:8000/route \
  -H "Content-Type: application/json" \
  -d '{"subject":"Password reset failed","body":"User cannot access account after password reset"}'
```

The API returns the predicted queue and a confidence score.

## Notes

`app/model.py` contains a TF-IDF plus linear SVM pipeline and a `predict` function.

`app/api.py` exposes the FastAPI route used for inference.

`app/tasks.py` retrains the model from newly labelled tickets and swaps in the updated model through a Celery task.

The system was built to replace keyword rules with a learned classifier. In practice, routing quality improved substantially and median handoff time dropped from hours to minutes.
