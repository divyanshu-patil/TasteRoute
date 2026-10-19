"""Venue ranking: percentile, lift over a popularity baseline, fit, confidence (F03; D-03, D-13)."""

from dataclasses import dataclass, field
from typing import Literal

Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class Weights:
    target: float = 0.7
    lift: float = 0.3


@dataclass(frozen=True)
class Thresholds:
    high_target: float = 0.8
    high_lift: float = 0.15
    high_support: int = 2
    medium_target: float = 0.6
    medium_lift: float = 0.05
    min_venues: int = 15


@dataclass(frozen=True)
class Candidate:
    """One venue from the target query: Qloo affinity, Qloo popularity, and explainability support."""

    venue_id: str
    affinity: float | None
    popularity: float
    support: int = 0


@dataclass
class Scored:
    venue_id: str
    venue_type: str
    target_pct: float
    baseline_pct: float
    lift: float
    fit: float
    confidence: Confidence
    flags: list[str] = field(default_factory=list)
    rank: int = 0


def percentiles(values: dict[str, float]) -> dict[str, float]:
    """Highest value -> 1.0, lowest -> 1/n. Ties share the better rank. pct = 1 - (rank - 1) / n."""
    n = len(values)
    if n == 0:
        return {}
    ordered = sorted(values.items(), key=lambda kv: -kv[1])
    out: dict[str, float] = {}
    rank = 1
    for i, (k, v) in enumerate(ordered):
        if i > 0 and v < ordered[i - 1][1]:
            rank = i + 1
        out[k] = 1 - (rank - 1) / n
    return out


def order_percentiles(ids_in_order: list[str]) -> dict[str, float]:
    n = len(ids_in_order)
    return {vid: 1 - i / n for i, vid in enumerate(ids_in_order)} if n else {}


def lift(target_pct: float, baseline_pct: float) -> float:
    return round(target_pct - baseline_pct, 4)


def fit(target_pct: float, lift_value: float, w: Weights = Weights()) -> float:
    return round(w.target * target_pct + w.lift * max(lift_value, 0.0), 4)


def confidence(target_pct: float, lift_value: float, support: int, th: Thresholds = Thresholds(), signals: int = 2) -> Confidence:
    """`signals` = brands in the taste signal. A brand Qloo knows by itself is one signal, so it can't need two (D-13)."""
    if target_pct >= th.high_target and lift_value >= th.high_lift and support >= min(th.high_support, max(signals, 1)):
        return "high"
    if target_pct >= th.medium_target and lift_value >= th.medium_lift:
        return "medium"
    return "low"


def support(explain: list[tuple[str, float]]) -> int:
    """Signal entities contributing at least half their fair share of the explanation (D-13)."""
    k = len(explain)
    return sum(1 for _, s in explain if s >= 0.5 / k) if k else 0


def score_type(
    venue_type: str,
    target: list[Candidate],
    baseline_ids: list[str],
    baseline_popularity: dict[str, float],
    w: Weights = Weights(),
    th: Thresholds = Thresholds(),
    signals: int = 2,
) -> list[Scored]:
    """Score one venue type. Baseline percentile = percentile of Qloo popularity within target ∪ baseline (D-03)."""
    if not target:
        return []
    if all(c.affinity is not None for c in target):
        tpct = percentiles({c.venue_id: float(c.affinity or 0.0) for c in target})
    else:
        tpct = order_percentiles([c.venue_id for c in target])
    pool = dict(baseline_popularity)
    pool.update({c.venue_id: c.popularity for c in target})
    bpct = percentiles(pool)
    in_baseline = set(baseline_ids)
    out = []
    for c in target:
        t, b = round(tpct[c.venue_id], 4), round(bpct[c.venue_id], 4)
        lv = lift(t, b)
        flags = [] if c.venue_id in in_baseline else ["not_in_baseline"]
        out.append(Scored(c.venue_id, venue_type, t, b, lv, fit(t, lv, w), confidence(t, lv, c.support, th, signals), flags))
    return out


def merge(per_type: list[list[Scored]], max_venues: int) -> list[Scored]:
    """De-duplicate across venue types (keep the best fit), sort by fit, keep the top N, assign ranks."""
    best: dict[str, Scored] = {}
    for rows in per_type:
        for s in rows:
            if s.venue_id not in best or s.fit > best[s.venue_id].fit:
                best[s.venue_id] = s
    ranked = sorted(best.values(), key=lambda s: (-s.fit, -s.target_pct, s.venue_id))[:max_venues]
    for i, s in enumerate(ranked, 1):
        s.rank = i
    return ranked


def coverage_warnings(n_venues: int, baseline_counts: dict[str, int], th: Thresholds = Thresholds()) -> list[str]:
    out = []
    if n_venues < th.min_venues:
        out.append(f"Low coverage: only {n_venues} venues found in this city for the chosen types.")
    thin = [t for t, n in baseline_counts.items() if n < th.min_venues]
    if thin:
        out.append(f"Low coverage for {', '.join(sorted(thin))}: the popularity baseline returned few venues.")
    return out
