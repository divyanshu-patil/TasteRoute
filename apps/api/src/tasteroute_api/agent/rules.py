"""Decision rules for the scout phase (AGT-07, AGT-09). The agent's prompt states them and tool outputs carry their inputs;
the deterministic plan applies the same rules, so both reach the same decisions."""

from typing import Any

MIN_COMPARABLES = 2  # a product known only through fewer similar brands than this gets more suggested
MAX_SUGGEST_ROUNDS = 2  # per product
MIN_VENUES_PER_TYPE = 15  # a venue type with fewer ranked venues than this -> add another type from the pack
MAX_ADDED_TYPES = 2  # per run


def weak(entities: list[dict[str, Any]]) -> bool:
    """Known only through fewer than MIN_COMPARABLES similar brands (none at all included). A product the user doesn't
    want is left out of the run, not emptied."""
    return not any(e.get("role") == "self" for e in entities) and len(entities) < MIN_COMPARABLES


def needs_comparables(resolution: dict[str, dict[str, Any]]) -> list[str]:
    return [pid for pid, r in resolution.items() if r.get("weak") and r.get("suggest_rounds", 0) < MAX_SUGGEST_ROUNDS]


def thin_types(by_type: dict[str, int], run_types: list[str]) -> dict[str, int]:
    return {t: by_type.get(t, 0) for t in run_types if by_type.get(t, 0) < MIN_VENUES_PER_TYPE}


def type_to_add(by_type: dict[str, int], run_types: list[str], pack_types: list[str], added: list[str]) -> str | None:
    """The first pack type not in the run, when a run type is thin and the cap allows."""
    if len(added) >= MAX_ADDED_TYPES or not thin_types(by_type, run_types):
        return None
    return next((t for t in pack_types if t not in run_types), None)
