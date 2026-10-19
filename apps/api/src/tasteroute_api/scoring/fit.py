"""Best product per venue (F04)."""

from dataclasses import dataclass
from typing import Literal

Label = Literal["clear", "close", "tie", "single_product", "unscored"]
CLEAR, CLOSE = 0.15, 0.05


@dataclass(frozen=True)
class ProductFit:
    best: str | None
    margin: float | None
    label: Label
    runner_up: str | None = None


def best_product(percentiles: dict[str, float]) -> ProductFit:
    """percentiles: product_id -> this venue's percentile for that product (scored products only)."""
    if not percentiles:
        return ProductFit(None, None, "unscored")
    ordered = sorted(percentiles.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ordered) == 1:
        return ProductFit(ordered[0][0], None, "single_product")
    margin = round(ordered[0][1] - ordered[1][1], 4)
    label: Label = "clear" if margin >= CLEAR else "close" if margin >= CLOSE else "tie"
    return ProductFit(ordered[0][0], margin, label, ordered[1][0])
