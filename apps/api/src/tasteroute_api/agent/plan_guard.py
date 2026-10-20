"""Plan guard: enforces safety, not a script (AGT-01, AGT-08). A call must be allowed in this phase, come after what it
needs, use only ids the run already holds, stay within the caps and not repeat an identical call. Which tools to call,
and with which of the known ids, is the agent's decision."""

import json
from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import rules

PHASE_TOOLS: dict[str, list[str]] = {
    "scout": ["resolve_entities", "suggest_more_comparables", "rank_venues", "add_venue_type", "match_products",
              "attach_evidence", "finish_phase"],
    "outreach": ["find_contacts", "draft_pitches", "finish_phase"],
}
REQUIRED: dict[str, list[str]] = {  # every phase runs these, in this order; the deterministic plan finishes them
    "scout": ["resolve_entities", "rank_venues", "match_products", "attach_evidence"],
    "outreach": ["find_contacts", "draft_pitches"],
}
REQUIRES: dict[str, dict[str, set[str]]] = {
    "scout": {
        "suggest_more_comparables": {"resolve_entities"},
        "rank_venues": {"resolve_entities"},
        "add_venue_type": {"rank_venues"},
        "match_products": {"rank_venues"},
        "attach_evidence": {"match_products"},
        "finish_phase": {"attach_evidence"},
    },
    "outreach": {"draft_pitches": {"find_contacts"}, "finish_phase": {"find_contacts"}},
}
NOT_AFTER = {"suggest_more_comparables": "rank_venues", "add_venue_type": "match_products"}  # they change what those used


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResolveArgs(_Args):
    product_ids: list[str] | None = None


class SuggestArgs(_Args):
    product_id: str
    reason: str = Field(default="", max_length=300)


class RankArgs(_Args):
    venue_types: list[str] | None = None
    max_venues: int | None = Field(default=None, ge=10, le=60)


class AddTypeArgs(_Args):
    type_id: str
    reason: str = Field(default="", max_length=300)


class NoArgs(_Args):
    pass


class EvidenceArgs(_Args):
    top_n: int = Field(default=30, ge=5, le=40)


class VenueIdsArgs(_Args):
    venue_ids: list[str] | None = None


class FinishArgs(_Args):
    summary: str = Field(default="", max_length=500)


ARGS: dict[str, type[_Args]] = {
    "resolve_entities": ResolveArgs,
    "suggest_more_comparables": SuggestArgs,
    "rank_venues": RankArgs,
    "add_venue_type": AddTypeArgs,
    "match_products": NoArgs,
    "attach_evidence": EvidenceArgs,
    "find_contacts": VenueIdsArgs,
    "draft_pitches": VenueIdsArgs,
    "finish_phase": FinishArgs,
}


class PlanGuard:
    def __init__(self, phase: str, known: dict[str, set[str]]) -> None:
        self.phase = phase
        self.known = known  # product_ids, venue_types (the run's), pack_types, venue_ids (selected), draft_venue_ids
        self.done: list[str] = []
        self.seen: set[str] = set()
        self.suggested: Counter[str] = Counter()

    def check(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        """Returns (validated args, None) or (None, error message for the model)."""
        if name not in PHASE_TOOLS[self.phase]:
            return None, f"Unknown tool '{name}' for the {self.phase} phase. Allowed: {PHASE_TOOLS[self.phase]}."
        missing = REQUIRES[self.phase].get(name, set()) - set(self.done)
        if missing:
            return None, f"Call {sorted(missing)} before {name}."
        if NOT_AFTER.get(name) in self.done:
            return None, f"{name} must come before {NOT_AFTER[name]}."
        try:
            parsed = ARGS[name].model_validate(args or {}).model_dump()
        except ValidationError as e:
            return None, f"Invalid arguments for {name}: {e.errors()[0]['msg']}"
        err = self._ids(name, parsed)
        if err:
            return None, err
        key = name + json.dumps(parsed, sort_keys=True)
        if key in self.seen:
            return None, f"{name} was already called with these arguments. Call the next tool."
        return parsed, None

    def _ids(self, name: str, a: dict[str, Any]) -> str | None:
        """No invented ids: every id must be one the run state or an earlier tool output gave the agent."""
        subsets = {"resolve_entities": ("product_ids", "product_ids"), "rank_venues": ("venue_types", "venue_types"),
                   "find_contacts": ("venue_ids", "venue_ids"), "draft_pitches": ("venue_ids", "draft_venue_ids")}
        if name in subsets and a.get(subsets[name][0]) is not None:
            field, key = subsets[name]
            allowed = self.known.get(key, set())
            if not a[field] or not set(a[field]) <= allowed:
                return f"{field} must be a non-empty subset of {sorted(allowed)}."
        if name == "suggest_more_comparables":
            if a["product_id"] not in self.known.get("product_ids", set()):
                return f"product_id must be one of {sorted(self.known.get('product_ids', set()))}."
            if self.suggested[a["product_id"]] >= rules.MAX_SUGGEST_ROUNDS:
                return f"At most {rules.MAX_SUGGEST_ROUNDS} suggestion rounds per product."
        if name == "add_venue_type":
            free = self.known.get("pack_types", set()) - self.known.get("venue_types", set())
            if a["type_id"] not in free:
                return f"type_id must be one of {sorted(free)}."
            if self.done.count("add_venue_type") >= rules.MAX_ADDED_TYPES:
                return f"At most {rules.MAX_ADDED_TYPES} venue types can be added."
        return None

    def record(self, name: str, args: dict[str, Any]) -> None:
        self.done.append(name)
        self.seen.add(name + json.dumps(args, sort_keys=True))
        if name == "suggest_more_comparables":
            self.suggested[args["product_id"]] += 1
        if name == "add_venue_type":
            self.known["venue_types"] = self.known.get("venue_types", set()) | {args["type_id"]}

    def remaining(self) -> list[str]:
        """Required tools not yet done, in order (used by the deterministic fallback)."""
        return [t for t in REQUIRED[self.phase] if t not in self.done]
