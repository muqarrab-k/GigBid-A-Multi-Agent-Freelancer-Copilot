from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Any, Iterable


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%m/%d/%Y",
    "%d.%m.%Y",
    "%d %b %Y",
    "%d %B %Y",
)


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_amount(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    cleaned = re.sub(r"[^\d,.\-]", "", text)
    if not cleaned or cleaned in {"-", ".", ","}:
        return None

    if cleaned.count(",") > 0 and cleaned.count(".") > 0:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", ".")

    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    return f"{amount.quantize(Decimal('0.01'))}"


def _to_decimal(value: Any) -> Decimal | None:
    normalized = normalize_amount(value)
    if normalized is None:
        return None
    return Decimal(normalized)


def check_totals(invoice: dict[str, Any]) -> dict[str, Any]:
    # Normalise known date fields.
    for key in ("invoice_date", "due_date", "issue_date"):
        if key in invoice:
            invoice[key] = normalize_date(invoice.get(key))

    # Normalise money fields.
    for key in ("subtotal", "tax", "total"):
        if key in invoice:
            invoice[key] = normalize_amount(invoice.get(key))

    line_items = invoice.get("line_items") or []
    line_total = Decimal("0.00")
    for item in line_items:
        amount = _to_decimal(item.get("amount") or item.get("total"))
        if amount is not None:
            line_total += amount

    subtotal = _to_decimal(invoice.get("subtotal"))
    tax = _to_decimal(invoice.get("tax"))
    total = _to_decimal(invoice.get("total"))

    if subtotal is None:
        subtotal = line_total
    computed_total = subtotal + (tax or Decimal("0.00"))

    invoice["calculated_subtotal"] = f"{subtotal.quantize(Decimal('0.01'))}"
    invoice["calculated_total"] = f"{computed_total.quantize(Decimal('0.01'))}"

    if total is not None:
        invoice["totals_match"] = total.quantize(Decimal("0.01")) == computed_total.quantize(Decimal("0.01"))
    else:
        invoice["totals_match"] = None

    return invoice
