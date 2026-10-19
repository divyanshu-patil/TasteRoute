"""Category packs: the only place category names live (CAT-01). Validated at import time."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from ..settings import get_settings


class OsmTag(BaseModel):
    key: str
    value: str


class VenueType(BaseModel):
    id: str
    label: str
    qloo_tags: list[str] = Field(min_length=1)
    osm: OsmTag


class PitchStyle(BaseModel):
    noun: str = "stockist"
    ask_examples: list[str] = Field(min_length=1)
    avoid: list[str] = Field(default_factory=list)


class Pack(BaseModel):
    id: str
    label: str
    status: Literal["full", "secondary", "roadmap"]
    product_entity_types: list[str] = Field(min_length=1)
    venue_types: list[VenueType] = Field(min_length=1)
    baseline_signal: Literal["none", "fixed_entities"] = "none"
    baseline_entities: list[str] = Field(default_factory=list)
    reason_tag_kinds: list[str] = Field(min_length=1)
    pitch_style: PitchStyle

    def venue_type(self, vid: str) -> VenueType | None:
        return next((v for v in self.venue_types if v.id == vid), None)


@lru_cache
def all_packs() -> dict[str, Pack]:
    packs = {}
    for f in sorted(Path(__file__).parent.glob("*.yaml")):
        p = Pack.model_validate(yaml.safe_load(f.read_text()))
        packs[p.id] = p
    return packs


def enabled_packs() -> dict[str, Pack]:
    s = get_settings()
    return {k: p for k, p in all_packs().items() if p.status == "full" or (p.status == "secondary" and s.pack_fashion_enabled)}


UNSUPPORTED = "unsupported"


def default_pack() -> Pack:
    return next(p for p in all_packs().values() if p.status == "full")


def pack_for(category: str) -> Pack:
    return all_packs().get(category) or default_pack()


def check_category(v: str) -> str:
    """Pydantic validator: a known pack id or 'unsupported'."""
    if v not in all_packs() and v != UNSUPPORTED:
        raise ValueError(f"category must be one of {[*all_packs(), UNSUPPORTED]}")
    return v


def get_pack(pack_id: str) -> Pack | None:
    return enabled_packs().get(pack_id)
