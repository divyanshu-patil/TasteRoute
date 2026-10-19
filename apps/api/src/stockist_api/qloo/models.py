"""Models for compacted Qloo responses, built from tests/fixtures/qloo (docs/qloo-contract.md)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _M(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Tag(_M):
    id: str
    name: str


class Location(_M):
    lat: float
    lon: float


class ExplainItem(_M):
    entity_id: str
    score: float


class EntityQuery(_M):
    affinity: float | None = None
    distance: float | None = None
    explainability: dict[str, list[ExplainItem]] | None = None


class Place(_M):
    entity_id: str
    name: str
    subtype: str | None = None
    popularity: float = 0.0
    location: Location | None = None
    query: EntityQuery | None = None
    tags: list[Tag] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)

    @property
    def affinity(self) -> float | None:
        return self.query.affinity if self.query else None

    def explain(self) -> list[ExplainItem]:
        if not self.query or not self.query.explainability:
            return []
        return self.query.explainability.get("signal.interests.entities", [])


class Brand(_M):
    entity_id: str
    name: str
    types: list[str] = Field(default_factory=list)
    popularity: float = 0.0
    tags: list[Tag] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class SearchBody(_M):
    results: list[Brand] = Field(default_factory=list)


class PlaceResults(_M):
    entities: list[Place] = Field(default_factory=list)


class InsightsBody(_M):
    success: bool = True
    results: PlaceResults = Field(default_factory=PlaceResults)
    query: dict[str, Any] = Field(default_factory=dict)


class TagAffinity(_M):
    tag_id: str | None = None
    id: str | None = None
    name: str
    query: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        return self.tag_id or self.id or ""

    @property
    def affinity(self) -> float:
        return float(self.query.get("affinity") or 0.0)


class TagResults(_M):
    tags: list[TagAffinity] = Field(default_factory=list)


class TagInsightsBody(_M):
    results: TagResults = Field(default_factory=TagResults)
