"""Plan guard: allowed tools per phase, required order, validated arguments, no repeated calls (AGT-01)."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

PHASE_TOOLS: dict[str, list[str]] = {
    "scout": ["resolve_entities", "rank_venues", "match_products", "attach_evidence", "finish_phase"],
    "outreach": ["find_contacts", "draft_pitches", "finish_phase"],
}
REQUIRES: dict[str, dict[str, set[str]]] = {
    "scout": {
        "rank_venues": {"resolve_entities"},
        "match_products": {"rank_venues"},
        "attach_evidence": {"match_products"},
        "finish_phase": {"attach_evidence"},
    },
    "outreach": {"draft_pitches": {"find_contacts"}, "finish_phase": {"find_contacts"}},
}


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResolveArgs(_Args):
    product_ids: list[str] | None = None


class RankArgs(_Args):
    venue_types: list[str] | None = None
    max_venues: int | None = Field(default=None, ge=10, le=60)


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
    "rank_venues": RankArgs,
    "match_products": NoArgs,
    "attach_evidence": EvidenceArgs,
    "find_contacts": VenueIdsArgs,
    "draft_pitches": VenueIdsArgs,
    "finish_phase": FinishArgs,
}


class PlanGuard:
    def __init__(self, phase: str, expected: dict[str, set[str]]) -> None:
        self.phase = phase
        self.expected = expected  # product_ids, venue_types, venue_ids, draft_venue_ids
        self.done: list[str] = []
        self.seen: set[str] = set()

    def check(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        """Returns (validated args, None) or (None, error message for the model)."""
        if name not in PHASE_TOOLS[self.phase]:
            return None, f"Unknown tool '{name}' for the {self.phase} phase. Allowed: {PHASE_TOOLS[self.phase]}."
        missing = REQUIRES[self.phase].get(name, set()) - set(self.done)
        if missing:
            return None, f"Call {sorted(missing)} before {name}."
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
        checks = {
            ("resolve_entities", "product_ids"): "product_ids",
            ("rank_venues", "venue_types"): "venue_types",
            ("find_contacts", "venue_ids"): "venue_ids",
        }
        for (tool, field), exp_key in checks.items():
            if name == tool and a.get(field) is not None and set(a[field]) != self.expected.get(exp_key, set()):
                return f"{field} must be exactly {sorted(self.expected.get(exp_key, set()))}."
        if name == "draft_pitches" and a.get("venue_ids") is not None:
            allowed = self.expected.get("draft_venue_ids", set())
            if not a["venue_ids"] or not set(a["venue_ids"]) <= allowed:
                return f"venue_ids must be a non-empty subset of the venues with contacts: {sorted(allowed)}."
        return None

    def record(self, name: str, args: dict[str, Any]) -> None:
        self.done.append(name)
        self.seen.add(name + json.dumps(args, sort_keys=True))

    def remaining(self) -> list[str]:
        """Required tools not yet done, in plan order (used by the deterministic fallback)."""
        return [t for t in PHASE_TOOLS[self.phase] if t != "finish_phase" and t not in self.done]
