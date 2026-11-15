import re

from langsmith.anonymizer import create_anonymizer

from apps.api.tracing import MASKS


def test_masks_contact_and_payment_details() -> None:
    mask = create_anonymizer([{"pattern": re.compile(p), "replace": r} for p, r in MASKS])
    out = mask({"text": "Mail sam.lee@example.com or call +1 415 555 0134, card 4111 1111 1111 1111.",
                "nested": ["pay me at paypal.me/samlee"]})
    flat = str(out)
    assert "example.com" not in flat and "415 555" not in flat and "4111" not in flat and "paypal.me" not in flat
    assert "<email>" in flat and "<payment>" in flat
