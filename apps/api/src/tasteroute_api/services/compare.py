"""An LLM's ranking of a run's venues, shown next to Qloo's for comparison (EVL-06). Same prompt and inputs as the
stockist backtest (docs/evaluation-stockists.md): the products, the comparables and each venue's name, type and
neighbourhood, never the brand's name. One call per run, stored on the run. It never changes a score."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from ..agent.context import Services
from ..evaluation import hash_order
from ..llm.prompts import load
from ..llm.structured import structured


class _Score(BaseModel):
    id: str
    score: int = Field(ge=0, le=100)


class _Scores(BaseModel):
    scores: list[_Score]


async def llm_ranking(s: Services, run_id: str) -> dict[str, int]:
    rid = uuid.UUID(run_id)
    run = await s.pool.fetchrow("select r.llm_ranking, r.settings, r.city, b.profile from runs r "
                                "join brands b on b.id = r.brand_id where r.id = $1", rid)
    if run["llm_ranking"]:
        return {k: int(v) for k, v in run["llm_ranking"]["ranks"].items()}
    venues = {str(v["id"]): v for v in await s.pool.fetch(
        "select vs.venue_id as id, v.name, vs.venue_type, v.properties->>'neighborhood' as nb "
        "from venue_scores vs join venues v on v.id = vs.venue_id where vs.run_id = $1", rid)}
    products = [p["name"] for p in await s.pool.fetch(
        "select p.name from run_products rp join products p on p.id = rp.product_id where rp.run_id = $1 order by p.name", rid)]
    comps = [x["name"] for x in (run["settings"] or {}).get("signal") or []]
    order = hash_order(list(venues), run_id)
    lines = "\n".join(f"v{j}: {venues[i]['name']} ({venues[i]['venue_type']}{', ' + venues[i]['nb'] if venues[i]['nb'] else ''})"
                      for j, i in enumerate(order))
    about = (run["profile"] or {}).get("one_liner") or ""
    user = (f"Products: {about} ({', '.join(products)})\nBrands with a similar following: {', '.join(comps)}\n"
            f"City: {(run['city'] or {}).get('name', '')}\n\nVenues:\n{lines}")
    system, version = load("eval_rank_stockists")
    out = await structured(s.llm, _Scores, system, user, purpose="llm_ranking", prompt_version=version, run_id=run_id,
                           temperature=0.0, max_tokens=3000)
    got = {x.id: x.score for x in out.scores}
    ranked = sorted(range(len(order)), key=lambda j: (-got.get(f"v{j}", -1), j))
    ranks = {order[j]: n for n, j in enumerate(ranked, 1)}
    await s.pool.execute("update runs set llm_ranking = $2 where id = $1", rid,
                         {"prompt_version": version, "ranks": ranks, "created_at": datetime.now(UTC).isoformat()})
    return ranks
