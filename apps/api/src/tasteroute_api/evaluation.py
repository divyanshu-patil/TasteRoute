"""Metrics for the Qloo-on vs Qloo-off evaluation (docs/15-evaluation.md). Pure functions; scripts/evaluate.py does the IO."""

import random
from typing import Any


def jaccard(a: list[str], b: list[str]) -> float:
    x, y = set(a), set(b)
    return round(len(x & y) / len(x | y), 3) if x | y else 0.0


def spearman(a: list[str], b: list[str]) -> float | None:
    """Rank correlation over the items both lists share, re-ranked 1..k within each list. None below 3 shared items."""
    shared = [k for k in a if k in set(b)]
    n = len(shared)
    if n < 3:
        return None
    rb = {k: i for i, k in enumerate(sorted(shared, key=b.index))}
    d2 = sum((i - rb[k]) ** 2 for i, k in enumerate(shared))
    return round(1 - 6 * d2 / (n * (n * n - 1)), 3)


def blind_pairs(a_only: list[dict[str, Any]], c_only: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """Pair A-only with C-only venues in rank order; shuffle which side is shown first. Returns rows with the hidden label."""
    rng = random.Random(seed)
    rows = []
    for i, (va, vc) in enumerate(zip(a_only[:n], c_only[:n], strict=False)):
        a_first = rng.random() < 0.5
        first, second = (va, vc) if a_first else (vc, va)
        rows.append({"pair": i + 1, "venue_1": first, "venue_2": second, "a_is": 1 if a_first else 2})
    return rows


def a_wins(answers: dict[int, int], key: dict[int, int]) -> tuple[int, int]:
    """answers: pair -> chosen side (1 or 2). Returns (A wins, pairs judged)."""
    judged = [p for p in answers if p in key and answers[p] in (1, 2)]
    return sum(answers[p] == key[p] for p in judged), len(judged)
