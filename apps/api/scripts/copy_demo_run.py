"""Copies the sample run, with everything its pages and trace read, from this database (DATABASE_URL) into another one,
such as the hosted database behind the public demo. Costs no Qloo or LLM calls. Safe to re-run: existing rows are kept.

    uv run python scripts/copy_demo_run.py                      # newest demo run -> $SUPABASE_DATABASE_URL
    uv run python scripts/copy_demo_run.py --run <id> --to-env OTHER_URL_VAR

The target URL is read from an environment variable (or apps/api/.env), never from the command line, so it stays out
of shell history. The target must already be migrated (scripts/migrate.py --url ...).
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import dotenv_values

from tasteroute_api.settings import get_settings

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

# (table, rows of this run). Order follows the foreign keys. Venues are shared across runs and unique by Qloo id, so
# they are matched on qloo_entity_id and the run's rows are re-pointed at the target's venue ids.
VENUE_IDS = """select venue_id from venue_scores where run_id = $1 union select venue_id from venue_evidence where run_id = $1
  union select venue_id from contact_checks where run_id = $1 union select venue_id from contacts where run_id = $1"""
TABLES = [
    ("workspaces", "select * from workspaces where id = (select workspace_id from runs where id = $1)"),
    ("brands", "select * from brands where id = (select brand_id from runs where id = $1)"),
    ("products", "select * from products where brand_id = (select brand_id from runs where id = $1)"),
    ("runs", "select * from runs where id = $1"),
    ("run_products", "select * from run_products where run_id = $1"),
    ("qloo_calls", "select * from qloo_calls where run_id = $1 or id in (select source_call_id from product_entities where run_id = $1)"),
    ("external_calls", "select * from external_calls where run_id = $1"),
    ("llm_calls", "select * from llm_calls where run_id = $1"),
    ("product_entities", "select * from product_entities where run_id = $1"),
    ("venues", f"select * from venues where id in ({VENUE_IDS})"),
    ("venue_scores", "select * from venue_scores where run_id = $1"),
    ("venue_product_fit", "select * from venue_product_fit where run_id = $1"),
    ("venue_evidence", "select * from venue_evidence where run_id = $1"),
    ("contact_checks", "select * from contact_checks where run_id = $1"),
    ("contacts", "select * from contacts where run_id = $1"),
    ("drafts", "select * from drafts where run_id = $1"),
    ("run_events", "select * from run_events where run_id = $1"),
]


async def read(con: asyncpg.Connection, sql: str, rid: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(await con.fetchval(f"select coalesce(json_agg(t), '[]') from ({sql}) t", rid))
    return rows


async def main(run_id: str | None, to_env: str) -> None:
    target = os.environ.get(to_env) or dotenv_values(ENV_FILE).get(to_env)
    if not target:
        raise SystemExit(f"Set {to_env} (environment or apps/api/.env) to the target database URL.")
    src = await asyncpg.connect(get_settings().database_url)
    dst = await asyncpg.connect(target, statement_cache_size=0)  # 0 also works through the Supabase transaction pooler
    try:
        rid = run_id or await src.fetchval(
            "select r.id::text from runs r join workspaces w on w.id = r.workspace_id where w.kind = 'demo' "
            "and r.status = 'done' order by r.created_at desc limit 1")
        if rid is None:
            raise SystemExit("No finished demo run in the source database.")
        data = {t: await read(src, sql, rid) for t, sql in TABLES}
        if not data["runs"]:
            raise SystemExit(f"Run {rid} not found in the source database.")
        for r in data["qloo_calls"]:
            if r["run_id"] != rid:  # cached call made by an earlier run that the target doesn't have
                r["run_id"] = None
        for r in data["run_events"]:
            del r["id"]  # bigserial: the target numbers its own
        remap: dict[str, str] = {}
        async with dst.transaction():
            if await dst.fetchval("select exists(select 1 from runs where id = $1::uuid)", rid):
                print(f"Run {rid} is already in the target; nothing copied.")
                return
            for table, rows in data.items():
                if table == "venues":
                    await dst.execute("insert into venues select * from json_populate_recordset(null::venues, $1::json) "
                                      "on conflict (qloo_entity_id) do nothing", json.dumps(rows))
                    ids = dict(await dst.fetch("select qloo_entity_id, id::text from venues where qloo_entity_id = any($1::text[])",
                                               [v["qloo_entity_id"] for v in rows]))
                    remap = {v["id"]: ids[v["qloo_entity_id"]] for v in rows}
                    continue
                if rows and "venue_id" in rows[0]:
                    for r in rows:
                        r["venue_id"] = remap[r["venue_id"]]
                cols = ", ".join(rows[0]) if rows else "*"
                await dst.execute(f"insert into {table} ({cols}) select {cols} from "
                                  f"json_populate_recordset(null::{table}, $1::json) on conflict do nothing", json.dumps(rows))
                print(f"{table}: {len(rows)}")
        print(f"Copied run {rid}. On the API, DEMO_RUN_ID={rid} (or leave it empty: /v1/demo serves the newest demo run).")
    finally:
        await src.close()
        await dst.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="run id (default: the newest finished demo run)")
    ap.add_argument("--to-env", default="SUPABASE_DATABASE_URL", help="environment variable holding the target URL")
    a = ap.parse_args()
    asyncio.run(main(a.run, a.to_env))
