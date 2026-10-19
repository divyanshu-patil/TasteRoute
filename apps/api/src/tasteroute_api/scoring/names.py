"""Name matching for entity resolution (F02, ENT-03)."""

import re
import unicodedata

from rapidfuzz import fuzz

STOP = {"the", "co", "company", "inc", "ltd", "llc", "and"}
# Words a brand name can drop without becoming another brand ('Fieldnote Coffee' ~ 'Fieldnote').
GENERIC = {"coffee", "roasters", "roastery", "roasting", "tea", "kombucha", "brewing", "brewery", "drinks", "beverages",
           "foods", "distillery", "spirits", "wines", "cider", "bakery", "chocolate", "creamery"}
THRESHOLD = 0.85


def normalise(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("'", "").replace("’", "")
    words = [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in STOP]
    return " ".join(words)


def _stems(text: str) -> set[str]:
    return {w.rstrip("s") for w in normalise(text).split()}


def similarity(query: str, candidate: str, context: str | None = None) -> float:
    """Word-boundary prefix matches score 0.9: the candidate may extend the query ('blue bottle' -> 'blue bottle coffee');
    the query may extend the candidate only by generic words ('fieldnote coffee' -> 'fieldnote', not 'health ade' -> 'health').
    With `context` (the product's own words), the candidate's extra words must be generic or in it:
    'bubbies' -> 'bubbies pickles' for a pickle, not 'bubbies ice cream'."""
    x, y = normalise(query), normalise(candidate)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    if len(x) >= 4 and y.startswith(x + " ") and (context is None or _stems(y[len(x):]) <= _stems(" ".join(GENERIC) + " " + context)):
        return 0.9
    if len(y) >= 4 and x.startswith(y + " ") and _stems(x[len(y):]) <= _stems(" ".join(GENERIC) + " " + (context or "")):
        return 0.9
    return float(fuzz.ratio(x, y)) / 100.0


def is_match(query: str, candidate: str, context: str | None = None, threshold: float = THRESHOLD) -> bool:
    return similarity(query, candidate, context) >= threshold
