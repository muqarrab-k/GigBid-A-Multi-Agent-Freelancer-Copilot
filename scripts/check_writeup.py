"""Count forbidden punctuation (ignoring URLs), banned words and words in the blog."""

import re
import sys
from pathlib import Path

BANNED = ["delve", "leverage", "crucial", "robust", "seamless", "landscape", "tapestry", "unlock", "harness",
          "game changer", "furthermore", "moreover", "in conclusion", "it's worth noting", "navigate", "realm",
          "pivotal", "elevate", "streamline", "cutting edge"]

path = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/writeup.md")
text = re.sub(r"https?://\S+", "", path.read_text())
marks = {c: text.count(c) for c in ";:-–—"}
words = [b for b in BANNED if re.search(rf"\b{re.escape(b)}\w*", text, re.IGNORECASE)]
body = re.sub(r"[#*\[\]]", " ", text)
print(f"forbidden characters: {sum(marks.values())} {marks}")
print(f"banned words: {words or 'none'}")
print(f"words: {len(body.split())}")
