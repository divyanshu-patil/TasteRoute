"""Name matching for entity resolution (F02, ENT-03)."""

import re
import unicodedata

from rapidfuzz import fuzz

STOP = {"the", "co", "company", "inc", "ltd", "llc", "and"}
THRESHOLD = 0.85


def normalise(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("'", "").replace("’", "")
    words = [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in STOP]
    return " ".join(words)


def similarity(a: str, b: str) -> float:
    """Order-sensitive similarity. A word-boundary prefix match ('blue bottle' / 'blue bottle coffee') scores 0.9."""
    x, y = normalise(a), normalise(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    short, long_ = sorted((x, y), key=len)
    if len(short) >= 4 and long_.startswith(short + " "):
        return 0.9
    return float(fuzz.ratio(x, y)) / 100.0


def is_match(query: str, candidate: str, threshold: float = THRESHOLD) -> bool:
    return similarity(query, candidate) >= threshold
