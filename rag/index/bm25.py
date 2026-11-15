import math
import re
from collections import Counter

TOKEN = re.compile(r"[a-z0-9][a-z0-9+#]*(?:[.\-][a-z0-9+#]+)*")


def tokenize(text: str) -> list[str]:
    """Lowercase words; keeps c++, c#, node.js."""
    return TOKEN.findall(text.lower())


class BM25:
    """Okapi BM25 over a small in-memory corpus."""

    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tfs = [Counter(tokenize(d)) for d in docs]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avg = sum(self.lens) / len(self.lens) if self.lens else 0.0
        df = Counter(t for tf in self.tfs for t in tf)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = [t for t in set(tokenize(query)) if t in self.idf]
        out = []
        for tf, length in zip(self.tfs, self.lens, strict=True):
            norm = self.k1 * (1 - self.b + self.b * length / self.avg) if self.avg else self.k1
            out.append(sum(self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + norm) for t in terms if t in tf))
        return out
