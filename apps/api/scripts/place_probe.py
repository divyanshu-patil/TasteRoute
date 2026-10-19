"""Check the business-location lookups through the running API, e.g. to find your demo brand's address.
Spends up to 2 live Nominatim calls (place search, then reverse at the first hit); repeats are cached for 30 days.

    uv run python scripts/place_probe.py "St. Agrestis" [--city Brooklyn] [--api http://localhost:8000]
"""

import argparse

import httpx


def main(q: str, city_q: str, api: str) -> None:
    with httpx.Client(base_url=api, timeout=60) as c:
        c.headers["X-Workspace-Token"] = c.post("/v1/workspaces/session", json={}).json()["workspace_token"]
        city = c.get("/v1/cities/search", params={"q": city_q}).raise_for_status().json()[0]
        print(f"city:   {city['label']} · {city['detail']}")
        hits = c.get("/v1/places/search", params={"q": q, "bbox": ",".join(map(str, city["bbox"]))}).raise_for_status().json()
        for h in hits:
            print(f"search: {h['label']} · {h['detail']}  ({h['lat']:.5f}, {h['lon']:.5f})")
        if hits:
            p = c.get("/v1/places/reverse", params={"lat": hits[0]["lat"], "lon": hits[0]["lon"]}).raise_for_status().json()
            print(f"pin:    {p['label']} · {p['detail']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("q")
    ap.add_argument("--city", default="Brooklyn")
    ap.add_argument("--api", default="http://localhost:8000")
    a = ap.parse_args()
    main(a.q, a.city, a.api)
