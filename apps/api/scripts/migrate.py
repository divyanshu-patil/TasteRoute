"""Apply supabase/migrations/*.sql in order to DATABASE_URL (or --url). Works on local Postgres and Supabase.

Usage: uv run python scripts/migrate.py [--url postgresql://...] [--reset]
"""

import argparse
import asyncio
from pathlib import Path

import asyncpg

from stockist_api.settings import get_settings

MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"


async def migrate(url: str, reset: bool = False) -> list[str]:
    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        if reset:
            await conn.execute("drop schema public cascade; create schema public;")
        await conn.execute(
            "create table if not exists schema_migrations (name text primary key, applied_at timestamptz default now());"
            "alter table schema_migrations enable row level security;"
        )
        done = {r["name"] for r in await conn.fetch("select name from schema_migrations")}
        applied = []
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.name in done:
                continue
            async with conn.transaction():
                await conn.execute(f.read_text())
                await conn.execute("insert into schema_migrations(name) values ($1)", f.name)
            applied.append(f.name)
        return applied
    finally:
        await conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=None)
    p.add_argument("--reset", action="store_true")
    a = p.parse_args()
    print(asyncio.run(migrate(a.url or get_settings().database_url, a.reset)) or "up to date")
