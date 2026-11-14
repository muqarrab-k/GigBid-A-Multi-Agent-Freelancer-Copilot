import re
from functools import lru_cache
from pathlib import Path

import yaml

KEYWORDS_PATH = Path(__file__).with_name("persona_keywords.yaml")


@lru_cache(maxsize=1)
def load_patterns() -> tuple[int, dict[str, re.Pattern[str]]]:
    raw = yaml.safe_load(KEYWORDS_PATH.read_text())
    patterns = {}
    for persona, words in raw["personas"].items():
        alts = "|".join(re.escape(w.lower()) for w in sorted(words, key=len, reverse=True))
        patterns[persona] = re.compile(rf"(?<![a-z0-9])(?:{alts})(?![a-z0-9])")
    return int(raw["min_score"]), patterns


def persona_tags(title: str | None, skills: list[str], description: str | None) -> list[str]:
    """Personas whose keywords score high enough."""
    min_score, patterns = load_patterns()
    head = f"{title or ''} {' '.join(skills)}".lower()
    body = (description or "").lower()
    tags = []
    for persona, pattern in patterns.items():
        score = 2 * len(pattern.findall(head)) + len(pattern.findall(body))
        if score >= min_score:
            tags.append(persona)
    return tags
