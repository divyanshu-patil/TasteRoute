"""How often LLM pitches pass the grounding validator (B2, DRF-08): writes pitches for a run's first N drafted venues
without saving them and counts first-pass, after-repair and template outcomes. Spends up to 2 LLM calls per venue.

    uv run python scripts/draft_pass_rate.py <run_id> [n=8]
"""

import asyncio
import sys
import uuid

from tasteroute_api import db
from tasteroute_api.agent.context import RunContext
from tasteroute_api.grounding import validate
from tasteroute_api.main import build_services, close_services
from tasteroute_api.services.drafts import build_bundle, write_pitch
from tasteroute_api.settings import get_settings


async def main(run_id: str, n: int) -> None:
    s = get_settings()
    pool = await db.open_pool(s.database_url, s.db_statement_cache_size)
    svc = build_services(s, pool)
    try:
        ctx = await RunContext.load(svc, run_id)
        rows = await pool.fetch(
            "select vs.venue_id, vs.venue_type, vs.reason, v.name, c.email, c.role from venue_scores vs "
            "join venues v on v.id = vs.venue_id join contacts c on c.run_id = vs.run_id and c.venue_id = vs.venue_id "
            "and c.is_primary where vs.run_id = $1 order by vs.rank limit $2", uuid.UUID(run_id), n)
        counts = {"first_pass": 0, "after_repair": 0, "template": 0}
        for r in rows:
            b = await build_bundle(ctx, dict(r), dict(r))
            t0 = await pool.fetchval("select now()")
            out, source, _, _ = await write_pitch(ctx, b)
            repaired = await pool.fetchval("select count(*) from llm_calls where purpose = 'repair' and created_at >= $1", t0)
            kind = "template" if source == "template" else "after_repair" if repaired else "first_pass"
            counts[kind] += 1
            assert not validate(out.subject, out.body, out.cited_evidence_ids, b)
            print(f"--- {r['name']}: {kind}\n{out.body}\n")
        print(counts, f"of {len(rows)}")
    finally:
        await close_services(svc)
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8))
