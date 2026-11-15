"""LangSmith tracing when LANGSMITH_TRACING=true, with personal data masked before upload."""

import logging
import os
import re

log = logging.getLogger(__name__)

# masked in traced inputs and outputs
MASKS = [
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>"),
    (r"\+?\d[\d\s().-]{7,}\d", "<phone>"),
    (r"\b(?:\d[ -]?){13,19}\b", "<card>"),
    (r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", "<iban>"),
    (r"(?i)\b(paypal|venmo|zelle|wise)(\.me)?/\S+", "<payment>"),
]


def enabled() -> bool:
    return os.getenv("LANGSMITH_TRACING", "").lower() == "true" and bool(os.getenv("LANGSMITH_API_KEY"))


def setup_tracing() -> bool:
    """One masked client for every trace; off unless the env asks."""
    if not enabled():
        return False
    import langsmith
    from langsmith.anonymizer import create_anonymizer

    project = os.environ.setdefault("LANGSMITH_PROJECT", "gigbid")
    client = langsmith.Client(anonymizer=create_anonymizer([{"pattern": re.compile(p), "replace": r} for p, r in MASKS]))
    langsmith.configure(client=client, enabled=True, project_name=project)
    log.info("langsmith tracing on, project %s", project)
    return True
