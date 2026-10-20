"""Ground truth for the stockist backtest (docs/15-evaluation.md, EVL-03): each brand's Brooklyn accounts from its own
public account list, written to docs/eval/stockists.csv. No Qloo or LLM calls; about 100 plain HTTP requests.

    uv run python scripts/fetch_stockists.py
"""

import csv
import html
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs/eval/stockists.csv"
UA = "TasteRouteEval/1.0 (+https://github.com/; research backtest)"
BBOX = (40.5503390, -74.0566880, 40.7394340, -73.8329450)  # Brooklyn, south west north east
GRID = [(lat, lon) for lat in (40.57, 40.61, 40.65, 40.69, 40.73) for lon in (-74.03, -73.98, -73.93, -73.88)]
ZIPS = ["11201", "11205", "11206", "11211", "11215", "11216", "11217", "11222", "11225", "11231", "11237", "11238"]

BRANDS: list[dict[str, Any]] = [
    {"key": "kings_county", "brand": "Kings County Distillery", "split": "dev",
     "description": "A small-batch distillery making bourbon, rye and moonshine",
     "comparables": ["Widow Jane", "Hudson Whiskey", "Woodford Reserve", "Bulleit"], "backups": ["Maker's Mark"],
     "types": ["bar", "restaurant"], "source": ("stockist", "map_93gw94p3"),
     "page": "https://kingscountydistillery.com/pages/where-to-find-us"},
    {"key": "wolffer", "brand": "Wölffer Estate", "split": "dev",
     "description": "A Long Island estate making rosé wines and dry rosé cider",
     "comparables": ["Whispering Angel", "Château Miraval", "Kim Crawford"], "backups": ["Angry Orchard"],
     "types": ["bar", "restaurant"], "source": ("vip", ["Summer In A Bottle Rose", "Estate Rose", "Dry Rose Cider"]),
     "page": "https://wolffer.com/pages/find-us-near-you"},
    {"key": "steven_graf", "brand": "Steven Graf Wine", "split": "test",
     "description": "An importer of low-intervention wines from small European and American growers",
     "comparables": ["Gut Oggau", "Martha Stoumen", "Broc Cellars", "Kermit Lynch Wine Merchant"],
     "backups": ["Scribe Winery", "Donkey & Goat"], "types": ["bar", "restaurant"], "source": ("graf", None),
     "page": "https://www.stevengraf.wine/nyc"},
    {"key": "parlor", "brand": "Parlor Coffee", "split": "test",
     "description": "A Brooklyn specialty coffee roaster supplying cafés and restaurants",
     "comparables": ["Stumptown Coffee Roasters", "Blue Bottle Coffee", "Counter Culture Coffee", "Intelligentsia Coffee"],
     "backups": ["La Colombe Coffee Roasters"], "types": ["cafe", "restaurant"], "source": ("storemapper", "15750"),
     "page": "https://parlorcoffee.com/pages/where-to-find-us"},
    {"key": "st_agrestis", "brand": "St. Agrestis", "split": "test",
     "description": "Non-alcoholic bottled aperitivo cocktails and a booze-free amaro",
     "comparables": ["Ghia", "Lyre's", "Seedlip", "Campari"], "backups": ["Aperol"],
     "types": ["bar", "restaurant"], "source": ("stockist", "u25133"),
     "page": "https://stagrestis.com/pages/find-st-agrestis"},
    {"key": "casamara", "brand": "Casamara Club", "split": "test",
     "description": "Non-alcoholic botanical sodas inspired by Italian amari",
     "comparables": ["Fever-Tree", "Q Mixers", "Spindrift", "Sanpellegrino"], "backups": ["Ghia"],
     "types": ["bar", "restaurant", "deli"], "source": ("stockist", "u7378"),
     "page": "https://casamaraclub.com/pages/find"},
]


def get(c: httpx.Client, url: str, **params: Any) -> httpx.Response:
    """Polite: one request a second, and a back-off when the host says 429."""
    for wait in (0, 10, 30, 60):
        time.sleep(wait or 1.0)
        r = c.get(url, params=params or None)
        if r.status_code != 429:
            r.raise_for_status()
            return r
    r.raise_for_status()
    return r


def in_brooklyn(lat: float | None, lon: float | None, address: str) -> bool:
    if lat is not None and lon is not None and not (BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]):
        return False
    return bool(re.search(r"\bBrooklyn\b", address, re.I))


def stockist(c: httpx.Client, tag: str) -> list[dict[str, Any]]:
    """The search returns at most 100 nearest accounts, so a full circle is split into four smaller ones."""
    out: dict[str, dict[str, Any]] = {}
    todo = [(lat, lon, 4.0) for lat, lon in GRID]
    while todo:
        lat, lon, km = todo.pop()
        r = get(c, f"https://stockist.co/api/v1/{tag}/locations/search", latitude=lat, longitude=lon, distance=km, units="km")
        locs = r.json()["locations"]
        if len(locs) >= 100 and km > 0.5:
            d = km / 2 / 111
            todo += [(lat + a * d, lon + b * d * 1.32, km / 2) for a in (-1, 1) for b in (-1, 1)]
        for x in locs:
            addr = x.get("full_address") or ", ".join(
                p for p in (x.get("address_line_1"), x.get("city"), x.get("state"), x.get("postal_code")) if p)
            out[x["id"]] = {"name": x["name"], "address": addr, "lat": float(x["latitude"]), "lon": float(x["longitude"])}
    return list(out.values())


def storemapper(c: httpx.Client, user: str) -> list[dict[str, Any]]:
    s = get(c, f"https://www.storemapper.co/api/users/{user}/stores.js", callback="cb").text
    stores = json.loads(s[s.index("(") + 1:s.rindex(")")])["stores"]
    return [{"name": x["name"], "address": x["address"], "lat": x["latitude"], "lon": x["longitude"]} for x in stores]


def vip(c: httpx.Client, products: list[str]) -> list[dict[str, Any]]:
    """Distributor sales locator: accounts with a recorded sale; on-premise only (the feed labels them)."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for p in products:
        for z in ZIPS:
            s = get(c, "https://store-locator.wolffer-account.workers.dev/api", brand=p, zip=z).text
            for loc in re.findall(r'<location num="\d+">(.*?)</location>', s, re.S):
                f = {k: html.unescape(html.unescape(v)) for k, v in re.findall(r"<(\w+)>([^<]*)</\1>", loc)}
                if f.get("storeTypeRollup") != "on":
                    continue
                name = f["dba"].title()
                addr = f"{f['street'].title()}, {f['city'].title()}, {f['state']} {f['zip']}"
                out[(name, f["street"])] = {"name": name, "address": addr, "lat": float(f["lat"]), "lon": float(f["long"])}
    return list(out.values())


def graf(c: httpx.Client, url: str) -> list[dict[str, Any]]:
    """The partners page lists a bold name then its address; only the 'Restaurants & Bars' section counts."""
    s = get(c, url).text
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", re.sub(r"<br\s*/?>", "\n", s)))
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    start = next(i for i, ln in enumerate(lines) if re.fullmatch(r"Restaurants\s*&\s*Bars", ln))
    out = []
    for name, addr in zip(lines[start + 1:], lines[start + 2:], strict=False):
        if re.search(r"\b(NY|New York)\s+\d{5}\b", addr) and not re.search(r"\d{5}", name):
            out.append({"name": name, "address": addr, "lat": None, "lon": None})
    return out


def main() -> None:
    today = datetime.now(UTC).date().isoformat()
    rows = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as c:
        for b in BRANDS:
            kind, arg = b["source"]
            got = {"stockist": stockist, "storemapper": storemapper, "vip": vip, "graf": graf}[kind](c, arg or b["page"])
            seen, kept = set(), []
            for x in got:
                k = (re.sub(r"\W+", "", x["name"].lower()), re.sub(r"\W+", "", x["address"].lower())[:12])
                if k not in seen and in_brooklyn(x["lat"], x["lon"], x["address"]):
                    seen.add(k)
                    kept.append(x)
            print(f"{b['brand']}: {len(got)} accounts, {len(kept)} in Brooklyn")
            rows += [{"brand": b["brand"], "split": b["split"], "description": b["description"],
                      "comparables": "; ".join(b["comparables"]), "stockist_name": x["name"],
                      "stockist_address": x["address"], "lat": x["lat"] or "", "lon": x["lon"] or "",
                      "source_url": b["page"], "retrieved_on": today} for x in sorted(kept, key=lambda x: x["name"].lower())]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} rows")


if __name__ == "__main__":
    main()
