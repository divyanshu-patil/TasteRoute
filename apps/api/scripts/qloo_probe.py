"""Ad-hoc Qloo probe (Phase 0). Spends one live call per invocation.

Usage: uv run python scripts/qloo_probe.py /v2/insights filter.type=urn:entity:place ... [--save name]
Saves the raw response (never the key) to tests/fixtures/qloo/<name>.json and logs the call count.
"""

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "qloo"
LOG = ROOT / "scripts" / ".qloo_calls.log"


def env(name: str) -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"{name} missing in .env")


def main() -> None:
    args = sys.argv[1:]
    save = None
    if "--save" in args:
        i = args.index("--save")
        save = args[i + 1]
        del args[i : i + 2]
    path, *kv = args
    params = [tuple(p.split("=", 1)) for p in kv]
    t = time.perf_counter()
    r = httpx.get(
        env("QLOO_BASE_URL") + path,
        params=params,
        headers={"X-Api-Key": env("QLOO_API_KEY")},
        timeout=30,
    )
    ms = int((time.perf_counter() - t) * 1000)
    with LOG.open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {r.status_code} {path} {ms}ms\n")
    try:
        body = r.json()
    except ValueError:
        body = {"_raw": r.text[:2000]}
    if save:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        (FIXTURES / f"{save}.json").write_text(
            json.dumps({"request": {"path": path, "params": params}, "status": r.status_code, "body": body}, indent=1)
        )
    print(r.status_code, f"{ms}ms")
    print(json.dumps(body, indent=1)[:6000])


if __name__ == "__main__":
    main()
