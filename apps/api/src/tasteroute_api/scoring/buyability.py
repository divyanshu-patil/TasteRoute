"""Would a founder pitch this venue? (RNK-09, D-25). Flags only: Qloo scores never change. Chains and the venues of
brands in your own taste signal are hidden by default and counted; a venue that makes what you make gets a warning;
alcohol at a café, deli or bakery is a licence question. A positive Qloo audience growth reads "Rising" (RNK-10)."""

import re
from collections import Counter

from .names import is_match, normalise

HIDDEN = ("chain", "signal_brand_venue")


def chains(places: dict[str, str], known: list[str]) -> set[str]:
    """places: venue id -> name, every venue Qloo returned for the run. A chain's name appears twice or more in the city,
    or matches the pack's chain list."""
    counts = Counter(normalise(n) for n in places.values())
    return {vid for vid, n in places.items() if counts[normalise(n)] >= 2 or any(is_match(c, n) for c in known)}


def own_brand(name: str, signal_names: list[str]) -> bool:
    """The venue is one of the brands in your taste signal (yours or a comparable): pitching it is pitching a rival."""
    return any(is_match(s, name) for s in signal_names)


def _has(text: str, words: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(w.lower())}(?:s|es)?\b", text.lower()) for w in words)


def maker(venue_tags: set[str], product_text: str, makers: list[tuple[list[str], list[str]]]) -> bool:
    """makers: (product kind words, Qloo place tags of a venue that makes them), e.g. coffee -> coffee roastery."""
    return any(venue_tags & set(tags) and _has(product_text, kinds) for kinds, tags in makers)


def alcoholic(product_text: str, keywords: list[str]) -> bool:
    return _has(product_text, keywords)
