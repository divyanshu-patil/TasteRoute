"""F02: resolve a product to Qloo entities (itself, else up to 3 comparable brands named by the LLM)."""

from typing import Any

from pydantic import BaseModel, Field

from ..agent.context import Services
from ..categories import Pack
from ..errors import AppError, LLMBadResponse, LLMUnavailable, QlooError
from ..llm.prompts import load
from ..llm.structured import structured
from ..qloo import api
from ..qloo.client import Trace
from ..qloo.models import Brand
from ..scoring.names import THRESHOLD, similarity

MAX_COMPARABLES = 3


class ComparableNames(BaseModel):
    names: list[str] = Field(default_factory=list, max_length=8)


def best_match(query: str, brands: list[Brand], context: str | None = None, query_may_extend: bool = True
               ) -> tuple[Brand, float] | None:
    scored = [(b, similarity(query, b.name, context, query_may_extend)) for b in brands]
    ok = [(b, s) for b, s in scored if s >= THRESHOLD]
    return max(ok, key=lambda bs: (bs[1], bs[0].popularity)) if ok else None


def entity(b: Brand, role: str, sim: float, call_id: str) -> dict[str, Any]:
    return {
        "entity_id": b.entity_id,
        "name": b.name,
        "type": (b.types or ["urn:entity:brand"])[0],
        "role": role,
        "similarity": round(sim, 3),
        "source_call_id": call_id,
    }


async def suggest_comparables(svc: Services, brand: dict[str, Any], product: dict[str, Any], run_id: str | None,
                              exclude: list[str] | None = None) -> list[str]:
    prompt, version = load("suggest_comparables")
    profile = brand.get("profile") or {}
    user = (
        f"Brand: {brand.get('name')}\nOne-liner: {profile.get('one_liner', '')}\nPrice tier: {profile.get('price_tier', 'unknown')}\n"
        f"Style: {', '.join(profile.get('style_words') or [])}\nProduct: {product.get('name')} ({product.get('kind') or ''})\n"
        f"Notes: {product.get('notes') or ''}"
        + (f"\nAlready tried, suggest different brands: {', '.join(exclude)}" if exclude else "")
    )
    out = await structured(svc.llm, ComparableNames, prompt, user, purpose="comparables", prompt_version=version,
                           run_id=run_id, max_tokens=300)
    return [n.strip() for n in out.names if n and n.strip()][:5]


async def resolve_product(
    svc: Services, brand: dict[str, Any], product: dict[str, Any], pack: Pack, trace: Trace, run_id: str | None = None
) -> dict[str, Any]:
    """Returns {product_id, status, entities, dropped, message}. Entity ids only ever come from Qloo (ENT-02)."""
    types = pack.product_entity_types
    pid = str(product["id"])
    queries = list(dict.fromkeys([product["name"], brand.get("name") or ""]))
    context = " ".join(str(product.get(k) or "") for k in ("name", "kind", "notes"))
    for q in [q for q in queries if q]:
        brands, call_id = await api.search(svc.qloo, q, types, trace)
        m = best_match(q, brands, context, query_may_extend=q != product["name"])
        if m:
            return {"product_id": pid, "status": "resolved", "entities": [entity(m[0], "self", m[1], call_id)],
                    "dropped": [], "message": "Qloo knows this"}

    entities: list[dict[str, Any]] = []
    dropped: list[str] = []
    try:
        names = await suggest_comparables(svc, brand, product, run_id)
    except (LLMUnavailable, LLMBadResponse):
        names = []
    for name in names:
        if len(entities) >= MAX_COMPARABLES:
            break
        try:
            brands, call_id = await api.search(svc.qloo, name, types, trace)
        except QlooError as e:
            if e.code in ("qloo_auth", "qloo_unconfigured", "qloo_budget_exceeded"):
                raise
            dropped.append(name)
            continue
        m = best_match(name, brands, context)
        if m and all(e["entity_id"] != m[0].entity_id for e in entities):
            entities.append(entity(m[0], "comparable", m[1], call_id))
        else:
            dropped.append(name)
    if entities:
        return {"product_id": pid, "status": "resolved", "entities": entities, "dropped": dropped,
                "message": "Using similar brands"}
    return {"product_id": pid, "status": "unresolved", "entities": [], "dropped": dropped,
            "message": "Qloo doesn't know this product or similar brands yet. Add a similar brand with Qloo search."}


async def validate_entity(svc: Services, entity_id: str, source_call_id: str) -> dict[str, Any]:
    """A user-added entity must appear in the stored Qloo response it came from (ENT-02, ENT-04)."""
    import uuid

    try:
        cid = uuid.UUID(source_call_id)
    except ValueError as e:
        raise AppError("Unknown Qloo call", code="validation_error", status=422) from e
    r = await svc.pool.fetchrow("select cache_key, response, endpoint from qloo_calls where id = $1", cid)
    body = r["response"] if r else None
    if r and body is None:
        body = await svc.pool.fetchval(
            "select response from qloo_calls where cache_key = $1 and response is not null order by created_at desc limit 1",
            r["cache_key"],
        )
    for b in (body or {}).get("results", []) if isinstance((body or {}).get("results"), list) else []:
        if b.get("entity_id") == entity_id:
            brand = Brand.model_validate(b)
            return entity(brand, "comparable", 1.0, source_call_id)
    raise AppError("That entity was not returned by Qloo", code="validation_error", status=422)
