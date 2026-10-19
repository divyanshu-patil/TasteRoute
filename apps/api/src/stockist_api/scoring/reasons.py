"""Template reasons over stored Qloo evidence (F05). The LLM never writes these."""

import re

# Identity tags stay in the evidence list but are not quoted in reasons or pitches.
SENSITIVE = re.compile(r"lgbt|owned|religio|ethnic|black|latin|asian|jewish|muslim|christian", re.I)


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def quotable(tags: list[str]) -> list[str]:
    return [t for t in tags if not SENSITIVE.search(t)]


def distinctive(overlap_by_venue: dict[str, list[str]], max_share: float = 0.5) -> dict[str, list[str]]:
    """Drop audience tags that most venues in the run share (e.g. 'Restaurant'): they explain nothing."""
    n = len(overlap_by_venue) or 1
    counts: dict[str, int] = {}
    for tags in overlap_by_venue.values():
        for t in set(tags):
            counts[t] = counts.get(t, 0) + 1
    common = {t for t, c in counts.items() if c / n > max_share}
    return {v: [t for t in tags if t not in common] for v, tags in overlap_by_venue.items()}


def reason(
    *,
    audience_overlap: list[str],
    crowd: list[str],
    interests: list[str],
    driver_names: list[str],
    best_product: str | None,
    runner_up: str | None,
    label: str,
) -> str:
    """Example: 'Guests here over-index on espresso bars and bakeries, like fans of Stumptown (Qloo).
    Crowd: foodies and young professionals, into specialty coffee (Qloo). Lead with Cold Brew (our inference).'"""
    parts: list[str] = []
    fans = _join(driver_names[:2])
    overlap = [t.lower() for t in quotable(audience_overlap)[:2]]
    if overlap:
        parts.append(f"Guests here over-index on {_join(overlap)}" + (f", like fans of {fans}" if fans else "") + " (Qloo).")
    elif fans:
        parts.append(f"Strong taste overlap with fans of {fans} (Qloo).")
    who = [c.lower() for c in quotable(crowd)[:2]]
    likes = [i.lower() for i in quotable(interests)[:2]]
    if who or likes:
        crowd_txt = "Crowd: " + _join(who) if who else "Guests"
        parts.append(crowd_txt + (f", into {_join(likes)}" if likes else "") + " (Qloo).")
    if not parts:
        parts.append("Strong taste match for your products (Qloo).")
    if best_product:
        if label == "close" and runner_up:
            parts.append(f"Lead with {best_product}; {runner_up} also fits (our inference).")
        elif label == "tie" and runner_up:
            parts.append(f"{best_product} and {runner_up} fit equally well (our inference).")
        else:
            parts.append(f"Lead with {best_product} (our inference).")
    return " ".join(parts)
