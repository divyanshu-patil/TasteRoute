"""Moves every run made without signing in (all anonymous workspaces in this database) into one account. For your own
database, after logging in once: on a shared database it would take other people's runs. Demo runs stay put.

    uv run python scripts/claim_runs.py <account email>
"""

import asyncio
import sys

from tasteroute_api import db
from tasteroute_api.routes.core import absorb
from tasteroute_api.settings import get_settings


async def main(email: str) -> None:
    s = get_settings()
    pool = await db.open_pool(s.database_url, s.db_statement_cache_size)
    try:
        async with pool.acquire() as con, con.transaction():
            mine = await con.fetchval("select id from workspaces where lower(email) = lower($1)", email)
            if mine is None:
                print("No account with that email yet: log in once in the app, then run this again.")
                return
            others = [r["id"] for r in await con.fetch("select id from workspaces where kind = 'anon' and user_id is null")]
            runs = await con.fetchval("select count(*) from runs where workspace_id = any($1::uuid[])", others)
            await absorb(con, others, mine)
        print(f"Moved {runs} runs from {len(others)} workspaces into {email}.")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
