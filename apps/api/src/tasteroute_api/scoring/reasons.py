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


def plain_tags(tags: list[str], drop: list[str]) -> list[str]:
    """Tags minus those that only say what kind of venue it is ('Cafe' for a café explains nothing), EVD-05."""
    gone = {d.lower() for d in drop}
    return [t for t in tags if t.lower() not in gone]


def _phrase(tag: str, phrases: dict[str, str]) -> str:
    return phrases.get(tag.lower(), tag.lower())


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
    phrases: dict[str, str] | None = None,
) -> str:
    """Example: 'Known for brunch and Italian food, which fans of Stumptown over-index on (Qloo). Crowd: foodies and
    young professionals, into specialty coffee (Qloo). Lead with Cold Brew (Qloo, per product).'
    audience_overlap = tags your brands' fans over-index on that this venue carries (not the guests' own scores)."""
    ph = phrases or {}
    parts: list[str] = []
    fans = _join(driver_names[:2])
    overlap = [_phrase(t, ph) for t in quotable(audience_overlap)[:2]]
    if overlap:
        parts.append(f"Known for {_join(overlap)}, which fans of {fans or 'your brands'} over-index on (Qloo).")
    elif fans:
        parts.append(f"Strong taste overlap with fans of {fans} (Qloo).")
    who = [_phrase(c, ph) for c in quotable(crowd)[:2]]
    likes = [_phrase(i, ph) for i in quotable(interests)[:2]]
    if who:
        parts.append("Crowd: " + _join(who) + (f", into {_join(likes)}" if likes else "") + " (Qloo).")
    elif likes:
        parts.append(f"Guests here are into {_join(likes)} (Qloo).")
    if not parts:
        parts.append("Strong taste match for your products (Qloo).")
    if best_product:
        if label == "close" and runner_up:
            parts.append(f"Lead with {best_product}; {runner_up} also fits (Qloo).")
        elif label == "tie" and runner_up:
            parts.append(f"{best_product} and {runner_up} fit about equally (Qloo).")
        else:
            parts.append(f"Lead with {best_product} (Qloo).")
    return " ".join(p[:1].upper() + p[1:] for p in parts)
