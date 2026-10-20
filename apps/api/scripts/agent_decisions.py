"""How often the scout agent's decisions fire on real brands (score plan F7). Drives the wizard path over HTTP against a
live API, like scripts/e2e_smoke.py. Spends live calls: about 15 Qloo and 10 LLM per brand, plus one city lookup.

    uv run python scripts/agent_decisions.py [--api http://localhost:8000]
"""

import argparse
import asyncio
import json
from pathlib import Path

import httpx
from e2e_smoke import wait_for

OUT = Path(__file__).resolve().parents[3] / "docs/eval/agent-decisions.json"
BRANDS = [
    ("Petit Clos Imports is an importer of low-intervention wines from small growers in the Jura and Austria, sold to wine bars and restaurants.",
     "Brooklyn", ["bar", "restaurant"]),
    ("Ember Row is a tiny hot sauce maker using Hudson Valley peppers: a smoky chipotle sauce and a green habanero sauce, for delis, "
     "bars and cafés.", "Hudson, New York", ["deli", "bar"]),
    ("Ledge Coffee is a small specialty coffee roaster making single-origin espresso and a decaf, for cafés and restaurants.",
     "Portland, Maine", ["cafe", "restaurant"]),
]


async def one(c: httpx.AsyncClient, description: str, city_q: str, types: list[str]) -> dict:
    prof = (await c.post("/v1/brands/intake", json={"description": description})).json()["profile"]
    prods = [{k: p.get(k) or "" for k in ("name", "kind", "notes")} for p in prof.get("products") or []][:3]
    keys = ("category", "one_liner", "price_tier", "prospects_are_consumer_facing", "style_words", "unsupported_reason")
    r = await c.post("/v1/brands", json={"name": prof.get("brand_name") or "Test brand",
                                         "profile": {k: prof.get(k) for k in keys}, "products": prods})
    brand_id = r.json()["brand_id"]
    res = (await c.post(f"/v1/brands/{brand_id}/resolve")).json()
    hit = (await c.get("/v1/cities/search", params={"q": city_q})).json()[0]
    city = {k: v for k, v in hit.items() if k not in ("label", "detail")}
    r = await c.post("/v1/runs", json={"brand_id": brand_id, "product_ids": [x["product_id"] for x in res], "city": city,
                                       "venue_types": types})
    if r.status_code != 202:
        return {"brand": prof.get("brand_name"), "city": city_q, "types": types, "status": "not started",
                "error": r.text[:300], "orchestration": None, "decisions": [], "venue_types_after": [], "agent_steps": 0,
                "qloo_live": 0}
    run_id = r.json()["run_id"]
    run = await wait_for(c, run_id, {"scouted"})
    trace = (await c.get(f"/v1/runs/{run_id}/trace")).json()
    return {
        "brand": prof.get("brand_name"), "city": city_q, "types": types, "run_id": run_id, "status": run["status"],
        "error": run.get("error_code"), "orchestration": run["orchestration"], "reason": run.get("orchestration_reason"),
        "wizard": {x["product_id"][:8]: [e["name"] for e in x["entities"]] for x in res},
        "decisions": [{"by": t["detail"]["by"], "tool": t["name"], "reason": t["detail"]["reason"], "saw": t["detail"]["saw"]}
                      for t in trace if t["step"] == "decision"],
        "venue_types_after": run["venue_types"], "agent_steps": sum(t["kind"] == "llm" and t["step"] == "agent_step" for t in trace),
        "qloo_live": run["counters"].get("qloo_live"), "warnings": run.get("warnings", []),
    }


async def main(api: str, only: int | None) -> None:
    async with httpx.AsyncClient(base_url=api, timeout=180) as c:
        c.headers["X-Workspace-Token"] = (await c.post("/v1/workspaces/session", json={})).json()["workspace_token"]
        out = json.loads(OUT.read_text()) if only is not None and OUT.exists() else []
        for i, (d, city, types) in enumerate(BRANDS):
            if only is not None and i != only:
                continue
            r = await one(c, d, city, types)
            if only is not None and i < len(out):
                out[i] = r
            else:
                out.append(r)
            print(json.dumps({k: r[k] for k in ("brand", "city", "status", "orchestration", "decisions", "venue_types_after",
                                                "agent_steps", "qloo_live")}, ensure_ascii=False))
        OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
        fired = {t: sum(any(x["tool"] == t for x in r["decisions"]) for r in out)
                 for t in ("suggest_more_comparables", "add_venue_type")}
        print(f"wrote {OUT.name}; runs with each decision: {fired}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--only", type=int, help="re-run one brand by index and keep the others' results")
    a = ap.parse_args()
    asyncio.run(main(a.api, a.only))
