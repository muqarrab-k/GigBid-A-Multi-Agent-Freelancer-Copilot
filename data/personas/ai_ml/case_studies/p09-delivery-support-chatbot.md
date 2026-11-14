# Delivery support chatbot for Parcelwise Logistics

Parcelwise Logistics needed a faster way to handle high-volume delivery support without forcing customers to wait for a human for every routine question. Their team wanted to reduce pressure on support staff while still preserving a smooth handoff whenever a conversation became too complex or sensitive.

I built a WhatsApp and SMS assistant that could help customers track parcels, reschedule deliveries, and escalate to a human agent with the full conversation context already attached. The goal was not just to automate replies, but to create a support experience that felt reliable, conversational, and useful in real customer workflows.

I implemented the assistant with Python, OpenAI API, LangGraph, FastAPI, Redis, and Twilio. The system was designed to manage multi-step conversations, keep track of delivery state, and call the right backend actions at the right moment. Redis helped keep session state responsive, while FastAPI exposed the service behind a production-friendly API. Twilio connected the assistant to both WhatsApp and SMS, which made it easy for customers to reach support on the channels they already used.

A small example of the service setup looked like this:

```python
from fastapi import FastAPI
from twilio.rest import Client
import redis

app = FastAPI()
cache = redis.Redis(host="localhost", port=6379, decode_responses=True)
twilio_client = Client("ACCOUNT_SID", "AUTH_TOKEN")

@app.get("/health")
def health():
    return {"status": "ok"}
```

The impact was clear: 43% of conversations were resolved without an agent, and customer satisfaction reached 4.4 out of 5. For a logistics business, that meant fewer repetitive tickets, faster answers for customers, and better use of support staff time on cases that truly needed human attention.

This engagement ran from 2023-11 to 2024-02 on an hourly basis. What I’m most proud of is that the assistant didn’t just automate answers — it improved the support flow end to end for Parcelwise Logistics.
