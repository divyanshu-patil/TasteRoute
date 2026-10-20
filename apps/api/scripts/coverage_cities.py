"""Does it work outside the demo city? (score plan H2a). Runs the sample brand in more cities over HTTP and records venues
found, the high-confidence share and how many of the top 10 have a published contact. Spends live calls: about 12 Qloo and
20 LLM per city, plus website fetches.

    uv run python scripts/coverage_cities.py [--api http://localhost:8000]
"""

import argparse
import asyncio
import json
from pathlib import Path

import httpx
from agent_decisions import one
from e2e_smoke import wait_for
from seed_demo import DESCRIPTION, TYPES

OUT = Path(__file__).resolve().parents[3] / "docs/eval/coverage-cities.json"
CITIES = ["Brooklyn", "Chicago", "Los Angeles"]
TOP = 10


async def city(c: httpx.AsyncClient, q: str) -> dict:
    r = await one(c, DESCRIPTION, q, TYPES)
    row = {"city": q, "status": r["status"], "orchestration": r["orchestration"], "error": r.get("error")}
    if r["status"] != "scouted":
        return row
    rows = (await c.get(f"/v1/runs/{r['run_id']}/venues", params={"limit": 100})).json()["items"]
    await c.post(f"/v1/runs/{r['run_id']}/contacts", json={"venue_ids": [v["venue_id"] for v in rows[:TOP]]})
    await wait_for(c, r["run_id"], {"done"})
    contacts = (await c.get(f"/v1/runs/{r['run_id']}/contacts")).json()
    return {**row, "run_id": r["run_id"], "venues": len(rows),
            "high_confidence": sum(v["confidence"] == "high" for v in rows),
            "top10": [v["name"] for v in rows[:TOP]],
            "top10_with_contact": sum(bool(x["contacts"]) for x in contacts),
            "qloo_live": r["qloo_live"]}


async def main(api: str) -> None:
    async with httpx.AsyncClient(base_url=api, timeout=180) as c:
        c.headers["X-Workspace-Token"] = (await c.post("/v1/workspaces/session", json={})).json()["workspace_token"]
        out = []
        for q in CITIES:
            out.append(await city(c, q))
            print(json.dumps({k: v for k, v in out[-1].items() if k != "top10"}, ensure_ascii=False))
        OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    asyncio.run(main(ap.parse_args().api))
