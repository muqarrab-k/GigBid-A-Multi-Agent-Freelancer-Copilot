import hashlib
import html
import re

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
WORD_RE = re.compile(r"[a-z0-9]+")
CURRENCY_SIGNS = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}


def clean_text(value: object) -> str | None:
    """Strip HTML and collapse whitespace."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    text = html.unescape(TAG_RE.sub(" ", str(value)))
    text = SPACE_RE.sub(" ", text).strip()
    return text or None


def parse_money(value: object) -> float | None:
    """First number in a value like '$1,200.50'."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return None if value != value else float(value)
    match = NUMBER_RE.search(str(value))
    return float(match.group().replace(",", "")) if match else None


def parse_range(value: object) -> tuple[float | None, float | None]:
    """Low and high from '$15.00-$35.00' or a single amount."""
    if value is None or isinstance(value, int | float):
        amount = parse_money(value)
        return amount, amount
    numbers = [float(n.replace(",", "")) for n in NUMBER_RE.findall(str(value))]
    if not numbers:
        return None, None
    return min(numbers[:2]), max(numbers[:2])


def detect_currency(value: object, default: str = "USD") -> str:
    text = str(value or "")
    for sign, code in CURRENCY_SIGNS.items():
        if sign in text:
            return code
    for code in CURRENCY_SIGNS.values():
        if code in text.upper():
            return code
    return default


def normalise(text: object) -> str:
    if not isinstance(text, str):
        return ""
    return " ".join(WORD_RE.findall(text.lower()))


def stable_id(*parts: object) -> str:
    raw = "|".join(normalise(str(p)) for p in parts if p is not None)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def exact_key(title: str | None, description: str | None, *extra: object) -> str:
    """Same text; extra fields only when no description."""
    if isinstance(description, str) and description:
        return stable_id(title, description)
    return stable_id(title, *extra)


def near_key(
    title: str | None, description: str | None, words: int = 30, min_words: int = 15
) -> str | None:
    """Title plus opening words, ignoring numbers."""
    tokens = [w for w in normalise(description).split() if not w.isdigit()]
    if len(tokens) < min_words:
        return None
    return stable_id(title, " ".join(tokens[:words]))


def dup_groups(exact: list[str], near: list[str | None]) -> list[str]:
    """Union rows sharing either key, return group id per row."""
    parent = list(range(len(exact)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for keys in (exact, near):
        first: dict[str | None, int] = {}
        for i, key in enumerate(keys):
            if key is None:
                continue
            if key in first:
                parent[find(i)] = find(first[key])
            else:
                first[key] = i

    roots = [find(i) for i in range(len(exact))]
    return [exact[root] for root in roots]
