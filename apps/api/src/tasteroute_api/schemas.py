"""Public API models (source of truth for openapi.json and packages/contracts)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from .categories import check_category, default_pack


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- workspaces, categories, cities
class SessionIn(In):
    workspace_token: str | None = None


class SessionOut(BaseModel):
    workspace_token: str
    workspace_id: str


class VenueTypeOut(BaseModel):
    id: str
    label: str


class CategoryOut(BaseModel):
    id: str
    label: str
    status: str
    venue_types: list[VenueTypeOut]


class City(In):
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    display_name: str | None = Field(default=None, max_length=300)
    country: str | None = Field(default=None, max_length=8)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    bbox: list[float] = Field(min_length=4, max_length=4)

    @field_validator("bbox")
    @classmethod
    def _bbox(cls, v: list[float]) -> list[float]:
        s, w, n, e = v
        if not (-90 <= s < n <= 90 and -180 <= w < e <= 180):
            raise ValueError("bbox must be [south, west, north, east]")
        return v


class CityHit(City):
    label: str
    detail: str


class Place(In):
    """A point with a plain-English name: the brand's own location (search result, map pin or a run's base)."""

    label: str = Field(min_length=1, max_length=160)
    detail: str = Field(default="", max_length=300)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


# ---------------------------------------------------------------- brands (F01, F02)
class IntakeIn(In):
    website_url: HttpUrl | None = None
    description: str | None = Field(default=None, max_length=1500)


class ProductIn(In):
    name: str = Field(min_length=1, max_length=120)
    kind: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=500)


class ProfileIn(In):
    one_liner: str = Field(default="", max_length=140)
    category: str = Field(default_factory=lambda: default_pack().id, max_length=40)
    prospects_are_consumer_facing: bool = True
    price_tier: Literal["budget", "mid", "premium", "unknown"] = "unknown"
    style_words: list[str] = Field(default_factory=list, max_length=6)
    sender_name: str | None = Field(default=None, max_length=80)
    unsupported_reason: str | None = None


    _category = field_validator("category")(check_category)


class BrandIn(In):
    name: str = Field(min_length=1, max_length=120)
    website_url: HttpUrl | None = None
    profile: ProfileIn
    products: list[ProductIn] = Field(min_length=1, max_length=5)
    unsupported_override: bool = False
    source_text: str | None = Field(default=None, max_length=13000)


class BrandPatch(In):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    profile: ProfileIn | None = None
    products: list[ProductIn] | None = Field(default=None, min_length=1, max_length=5)
    unsupported_override: bool | None = None


class EntityOut(BaseModel):
    entity_id: str
    name: str
    type: str
    role: Literal["self", "comparable"]
    similarity: float | None = None
    source_call_id: str | None = None


class ProductOut(BaseModel):
    id: str
    name: str
    kind: str | None
    notes: str | None
    entities: list[EntityOut] | None = None


class BrandOut(BaseModel):
    id: str
    name: str
    website_url: str | None
    category: str
    profile: dict[str, Any]
    unsupported_override: bool
    products: list[ProductOut]


class BrandCreated(BaseModel):
    brand_id: str
    product_ids: list[str]


class ResolutionOut(BaseModel):
    product_id: str
    status: Literal["resolved", "unresolved"]
    entities: list[EntityOut]
    dropped: list[str]
    message: str


class EntityRef(In):
    entity_id: str = Field(min_length=1, max_length=64)
    source_call_id: str = Field(min_length=1, max_length=64)


class EntitiesIn(In):
    entities: list[EntityRef] = Field(max_length=8)


class QlooSearchItem(BaseModel):
    entity_id: str
    name: str
    type: str
    popularity: float
    source_call_id: str


# ---------------------------------------------------------------- runs (F03-F05, F09)
class RunIn(In):
    brand_id: str
    product_ids: list[str] = Field(min_length=1, max_length=5)
    entity_ids_by_product: dict[str, list[str]] | None = None
    city: City
    venue_types: list[str] = Field(min_length=1, max_length=6)
    base: Place | None = None


class RunCreated(BaseModel):
    run_id: str


class RunOut(BaseModel):
    id: str
    status: str
    phase: str | None
    orchestration: str | None
    orchestration_reason: str | None
    brand: dict[str, Any]
    products: list[dict[str, Any]]
    city: dict[str, Any]
    venue_types: list[str]
    counters: dict[str, Any]
    warnings: list[str]
    resolution: dict[str, Any]
    scoring_version: str
    weights: dict[str, float]
    error_code: str | None
    error_message: str | None
    is_demo: bool
    created_at: datetime
    finished_at: datetime | None
    base: Place | None = None


class BestProduct(BaseModel):
    product_id: str
    name: str
    label: str | None
    margin: float | None


class VenueRow(BaseModel):
    venue_id: str
    rank: int
    name: str
    venue_type: str
    neighborhood: str | None
    lat: float | None = None
    lon: float | None = None
    fit: float
    lift: float
    target_pct: float
    baseline_pct: float
    confidence: str
    flags: list[str]
    best_product: BestProduct | None
    reason: str | None
    evidence_count: int
    contact_status: str


class VenuePage(BaseModel):
    items: list[VenueRow]
    total: int
    warnings: list[str]


class EvidenceOut(BaseModel):
    id: str
    type: str
    label: str
    value: dict[str, Any]
    source_kind: Literal["qloo", "external", "inference"]
    source_call_id: str | None
    captured_at: datetime
    stale: bool


class ContactOut(BaseModel):
    id: str
    email: str
    role: str | None
    type: str | None
    source: str
    confidence: int | None
    verification_status: str | None
    sources: list[dict[str, Any]]
    is_primary: bool


class VenueDetail(BaseModel):
    venue: VenueRow
    address: str | None
    website: str | None
    phone: str | None
    lat: float | None
    lon: float | None
    description: str | None
    product_fit: list[dict[str, Any]]
    evidence: list[EvidenceOut]
    contacts: list[ContactOut]
    checked_sources: list[str]
    base: Place | None = None


class Weights(In):
    target: float = Field(ge=0, le=1)
    lift: float = Field(ge=0, le=1)


class VenueIdsIn(In):
    venue_ids: list[str] = Field(min_length=1, max_length=60)


class Accepted(BaseModel):
    run_id: str
    status: str


class ContactStatusOut(BaseModel):
    venue_id: str
    name: str
    rank: int
    status: str
    checked_sources: list[str]
    website: str | None = None  # the venue's own site, when known
    contacts: list[ContactOut]


class DraftOut(BaseModel):
    id: str
    venue_id: str
    venue_name: str
    contact_id: str
    contact_email: str
    subject: str
    body: str
    cited_evidence_ids: list[str]
    source: Literal["llm", "template"]
    status: str
    model: str | None
    mailto: str | None
    updated_at: datetime
    approved_at: datetime | None


class DraftPatch(In):
    subject: str | None = Field(default=None, min_length=1, max_length=120)
    body: str | None = Field(default=None, min_length=1, max_length=4000)
    status: Literal["approved", "exported"] | None = None


class SuppressionIn(In):
    kind: Literal["email", "domain"]
    value: str = Field(min_length=3, max_length=254)
    reason: Literal["opt_out", "bounced", "claimed_email", "manual"] = "manual"


class SuppressionOut(BaseModel):
    id: str
    kind: str
    value: str
    reason: str
    created_at: datetime


class TraceRow(BaseModel):
    kind: Literal["qloo", "external", "llm", "tool"]
    id: str
    at: datetime
    step: str | None = None
    name: str
    detail: dict[str, Any]


class DemoOut(BaseModel):
    run_id: str | None
    available: bool


class HealthOut(BaseModel):
    status: str
    db: str
    qloo: str
    llm: dict[str, Any]
    hunter: str
    version: str
