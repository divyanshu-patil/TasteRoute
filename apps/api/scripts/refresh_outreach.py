"""Re-run contacts and drafts for an existing run's selected venues, e.g. after a contact-ranking change.
Website and OSM lookups come from the 7-day cache when fresh; drafts spend LLM calls.

    uv run python scripts/refresh_outreach.py <run_id>
"""

import asyncio
import sys
import uuid

from tasteroute_api import db
from tasteroute_api.main import build_services, close_services
from tasteroute_api.services import runs as run_service
from tasteroute_api.settings import get_settings


async def main(run_id: str) -> None:
    s = get_settings()
    pool = await db.open_pool(s.database_url, s.db_statement_cache_size)
    svc = build_services(s, pool)
    try:
        t0 = await pool.fetchval("select now()")
        ids = [str(r["venue_id"]) for r in await pool.fetch(
            "select cc.venue_id from contact_checks cc join venue_scores vs on vs.venue_id = cc.venue_id and vs.run_id = cc.run_id "
            "where cc.run_id = $1 order by vs.rank", uuid.UUID(run_id))]
        await run_service.run_outreach(svc, run_id, ids)
        print(dict(await pool.fetchrow("select status, orchestration, counters from runs where id = $1", uuid.UUID(run_id))))
        spent = await pool.fetchrow(
            "select (select count(*) from qloo_calls where not cache_hit and created_at >= $1) qloo, "
            "(select count(*) from llm_calls where created_at >= $1) llm, "
            "(select coalesce(json_object_agg(service, n), '{}') from (select service, count(*) n from external_calls "
            " where not cache_hit and created_at >= $1 group by service) x) external", t0)
        print(f"live calls spent: {dict(spent)}")
    finally:
        await close_services(svc)
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
