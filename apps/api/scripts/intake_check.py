"""Check what step 2 drafts for a brand before a demo: reads the site as the app does (or a saved text) and prints the
profile. One LLM call, plus the site's pages when given a URL.

    uv run python scripts/intake_check.py https://stagrestis.com/
    uv run python scripts/intake_check.py --text-file page.txt   # e.g. text a hosted read stored
"""

import argparse
import asyncio
from pathlib import Path

from tasteroute_api import db
from tasteroute_api.main import build_services, close_services
from tasteroute_api.services import intake
from tasteroute_api.settings import get_settings


async def main(url: str | None, text_file: str | None) -> None:
    s = get_settings()
    pool = await db.open_pool(s.database_url, s.db_statement_cache_size)
    svc = build_services(s, pool)
    try:
        if text_file:
            profile = (await intake.draft_profile(svc, Path(text_file).read_text()[:12_000])).model_dump()
        else:
            out = await intake.propose(svc, url, None)
            profile = out["profile"]
            print("pages read:", out["pages"])
        print(profile["brand_name"], "-", profile["one_liner"])
        for p in profile["products"]:
            print(f"  {p['name']}  ({p['kind']})")
    finally:
        await close_services(svc)
        await db.close_pool()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--text-file")
    a = ap.parse_args()
    if not (a.url or a.text_file):
        ap.error("give a URL or --text-file")
    asyncio.run(main(a.url, a.text_file))
