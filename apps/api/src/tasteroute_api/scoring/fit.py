"""Best product per venue (F04, FIT-04, D-24): each product's Qloo affinity is standardised across the venue type's
ranked venues, and the product this venue stands out most for leads. Percentiles are kept for the 0-100 display."""

from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import Literal

Label = Literal["clear", "close", "tie", "single_product", "unscored"]


@dataclass(frozen=True)
class FitThresholds:
    clear_z: float = 0.75  # z-gap between the best and the runner-up product
    clear_raw: float = 0.01  # and the best product's raw affinity must beat the runner-up's by this much
    close_z: float = 0.25


@dataclass(frozen=True)
class ProductFit:
    best: str | None
    margin: float | None  # z-gap to the runner-up
    label: Label
    runner_up: str | None = None


def zscores(values: dict[str, float]) -> dict[str, float]:
    """venue -> (affinity - mean) / sd across the set; all 0 when the set has no spread."""
    if not values:
        return {}
    mean, sd = fmean(values.values()), pstdev(values.values())
    return {k: (v - mean) / sd if sd > 0 else 0.0 for k, v in values.items()}


def best_product(z: dict[str, float], raw: dict[str, float] | None = None, th: FitThresholds = FitThresholds()) -> ProductFit:
    """z: product_id -> this venue's z-score for that product; raw: product_id -> its raw Qloo affinity here."""
    if not z:
        return ProductFit(None, None, "unscored")
    ordered = sorted(z.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ordered) == 1:
        return ProductFit(ordered[0][0], None, "single_product")
    (best, zb), (second, zs) = ordered[0], ordered[1]
    gap = round(min(zb - zs, 9.9999), 4)
    raw_gap = (raw or {}).get(best, 0.0) - (raw or {}).get(second, 0.0) if raw else th.clear_raw
    label: Label = "clear" if gap >= th.clear_z and raw_gap >= th.clear_raw else "close" if gap >= th.close_z else "tie"
    return ProductFit(best, gap, label, second)
