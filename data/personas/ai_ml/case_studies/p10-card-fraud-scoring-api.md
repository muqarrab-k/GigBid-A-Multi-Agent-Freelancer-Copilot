# Card Fraud Scoring API

I worked with a client in fintech (name withheld) on a card fraud scoring API, engaged on an hourly basis from 2022-09 to 2022-12. The goal was clear: help the business assess card activity faster, before authorisation, so suspicious transactions could be stopped without slowing down legitimate customers.

The challenge was to turn streaming card events into a reliable decision point in the payment flow. The client needed a service that could consume events as they arrived, score them consistently, and return a fraud risk signal quickly enough to be useful during authorisation. That meant balancing model quality, service speed, and operational simplicity in one production system.

I built a scoring service in Python using LightGBM for the model layer and FastAPI for the API. Kafka handled incoming card events, while Docker was used to package the service for deployment. The service reads card events from Kafka, applies the fraud model, and returns a score before authorisation so downstream systems can act on it immediately.

A simplified version of the service shape looked like this:

```python
from fastapi import FastAPI

app = FastAPI()

@app.post("/score")
def score(event: dict):
    features = build_features(event)
    risk = model.predict_proba([features])[0][1]
    return {"fraud_score": float(risk)}
```

The business impact was strong. During the pilot, fraud losses were down 22%, and the service achieved a p95 latency of 38 ms. That combination mattered: the client got a meaningful reduction in losses without introducing noticeable delay into the payment experience.

What I value about this project is that it connected model work to a live operational decision. It was not just about building a classifier; it was about making the scoring path dependable, fast, and usable in production. For a fintech environment, that shift from offline analysis to an operational service is where the value shows up.
