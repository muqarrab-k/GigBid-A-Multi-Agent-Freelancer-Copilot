from __future__ import annotations

import re
from typing import Optional

import pandas as pd


_WHITESPACE_RE = re.compile(r"\s+")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_DIGITS_RE = re.compile(r"\D+")


def clean_name(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    text = _WHITESPACE_RE.sub(" ", text)
    text = text.replace(".", "")
    return text.title()


def clean_email(value: object) -> str:
    if pd.isna(value):
        return ""
    email = str(value).strip().lower()
    email = email.replace("mailto:", "")
    email = _WHITESPACE_RE.sub("", email)
    return email if _EMAIL_RE.match(email) else ""


def clean_phone(value: object, default_country_code: Optional[str] = None) -> str:
    if pd.isna(value):
        return ""
    digits = _PHONE_DIGITS_RE.sub("", str(value))
    if not digits:
        return ""

    # Keep last 10 digits for standard North American numbers.
    if len(digits) > 10 and digits.startswith("1"):
        digits = digits[1:]
    if default_country_code and len(digits) == 10:
        return f"+{default_country_code}{digits}"

    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11:
        return f"+{digits[0]} {digits[1:4]} {digits[4:7]} {digits[7:]}"
    return digits


def normalize_contact_row(row: pd.Series) -> pd.Series:
    out = row.copy()
    if "name" in out:
        out["name"] = clean_name(out["name"])
    if "email" in out:
        out["email"] = clean_email(out["email"])
    if "phone" in out:
        out["phone"] = clean_phone(out["phone"])
    return out


def normalize_contacts(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for col in ("name", "email", "phone"):
        if col not in normalized.columns:
            normalized[col] = ""
    normalized["name"] = normalized["name"].map(clean_name)
    normalized["email"] = normalized["email"].map(clean_email)
    normalized["phone"] = normalized["phone"].map(clean_phone)
    return normalized
