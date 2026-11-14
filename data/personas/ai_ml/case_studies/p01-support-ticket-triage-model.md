# Support Ticket Triage for Kettlewell Support Co.

In late 2020, I worked with **Kettlewell Support Co.**, a SaaS support organization that needed a faster, more reliable way to route incoming helpdesk tickets. Their existing keyword rules were brittle: they missed context, sent tickets to the wrong team, and created long delays before customers reached the right queue. The business problem was straightforward, but important—every hour of routing delay made support feel slower and created extra work for the team.

I built a ticket triage model in **Python** using **scikit-learn** to classify incoming requests into **14 support queues**. The model was exposed through a **FastAPI** service so the support platform could send tickets for instant routing. To keep the system up to date as ticket patterns changed, I set up a nightly retraining flow using **Celery** with **Redis**, and stored the supporting data in **PostgreSQL**.

A simple version of the service looked like this:

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Ticket(BaseModel):
    subject: str
    body: str

@app.post("/route")
def route_ticket(ticket: Ticket):
    queue = model.predict([ticket.subject + " " + ticket.body])[0]
    return {"queue": queue}
```

The result was a clear operational improvement. The classifier reached a **macro-F1 of 0.88**, compared with **0.62** for the old keyword rules. More importantly for the business, the **median routing time dropped from 6 hours to 4 minutes**. That meant support agents could start work much sooner, tickets were assigned more consistently, and customers got to the right specialist with far less waiting.

For Kettlewell Support Co., this was not just a modeling exercise. It was a practical automation project that reduced manual triage work and made the support operation faster, more predictable, and easier to scale.
