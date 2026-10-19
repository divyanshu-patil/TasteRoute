"""The Qloo calls Stockist Scout makes, with verified parameters (docs/qloo-contract.md)."""

from .client import Params, QlooClient, Trace
from .models import Brand, InsightsBody, SearchBody, TagAffinity, TagInsightsBody

PLACE = "urn:entity:place"
MAX_TAKE = 50  # D-02: live API rejects take > 50


async def search(
    client: QlooClient, name: str, types: list[str], trace: Trace | None = None, take: int = 5
) -> tuple[list[Brand], str]:
    r = await client.get("/search", [("query", name), ("types", ",".join(types)), ("take", str(take))], trace)
    brands = SearchBody.model_validate(r.body).results
    # Type guard: /search may return other types; treat them as no match.
    return [b for b in brands if not b.types or set(b.types) & set(types)], r.call_id


async def place_insights(
    client: QlooClient,
    *,
    city_query: str | None = None,
    tags: list[str] | None = None,
    signal_ids: list[str] | None = None,
    results_ids: list[str] | None = None,
    explain: bool = False,
    take: int = MAX_TAKE,
    trace: Trace | None = None,
) -> tuple[InsightsBody, str, bool]:
    params: list[tuple[str, str]] = [("filter.type", PLACE)]
    if results_ids:
        params.append(("filter.results.entities", ",".join(results_ids)))
    if city_query:
        params += [("filter.location.query", city_query), ("filter.location.radius", "0")]
    if tags:
        params.append(("filter.tags", ",".join(tags)))
    if signal_ids:
        params.append(("signal.interests.entities", ",".join(signal_ids)))
    if explain:
        params.append(("feature.explainability", "true"))
    params.append(("take", str(min(take, MAX_TAKE))))
    r = await client.get("/v2/insights", params, trace)
    return InsightsBody.model_validate(r.body), r.call_id, r.cache_hit


async def audience_tags(
    client: QlooClient, signal_ids: list[str], trace: Trace | None = None, take: int = MAX_TAKE
) -> tuple[list[TagAffinity], str]:
    params: Params = [
        ("filter.type", "urn:tag"),
        ("signal.interests.entities", ",".join(signal_ids)),
        ("filter.parents.types", PLACE),
        ("take", str(take)),
    ]
    r = await client.get("/v2/insights", params, trace)
    return TagInsightsBody.model_validate(r.body).results.tags, r.call_id
