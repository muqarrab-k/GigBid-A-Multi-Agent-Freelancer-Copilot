from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.model import load_classifier, predict_ticket

router = APIRouter()


class TicketRequest(BaseModel):
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)


class TicketResponse(BaseModel):
    queue: str
    confidence: float
    top_queues: list[str] = []


_classifier = None


def get_classifier():
    global _classifier
    if _classifier is None:
        _classifier = load_classifier()
    return _classifier


@router.post("/route", response_model=TicketResponse)
def route_ticket(ticket: TicketRequest) -> TicketResponse:
    # Load the latest available model on first request.
    classifier = get_classifier()

    try:
        result = predict_ticket(classifier, ticket.subject, ticket.body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to route ticket") from exc

    queue = result.get("queue")
    confidence = result.get("confidence")

    if not queue or confidence is None:
        raise HTTPException(status_code=500, detail="Model returned an invalid response")

    top_queues = result.get("top_queues", [])
    return TicketResponse(queue=queue, confidence=float(confidence), top_queues=top_queues)
