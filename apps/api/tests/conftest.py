"""Test harness: local test database, fixture-backed fakes for every external service, no network."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", "postgresql://localhost:5432/stockist_test"),
    "LLM_PROVIDER": "fake",
    "QLOO_API_KEY": "test-key",
    "QLOO_RPS": "1000",
    "OLLAMA_API_KEY": "",
    "HUNTER_API_KEY": "",
    "SESSION_SECRET": "test-secret",
    "DEMO_RUN_ID": "",
    "PUBLIC_RUNS_PER_IP_PER_DAY": "50",
    "OSM_USER_AGENT": "StockistScout/test",
})

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402

from stockist_api import db  # noqa: E402
from stockist_api.external import website  # noqa: E402
from stockist_api.llm import LLMResult  # noqa: E402
from stockist_api.main import app, build_services, close_services  # noqa: E402
from stockist_api.routes import deps  # noqa: E402
from stockist_api.services import runs as run_service  # noqa: E402
from stockist_api.settings import get_settings  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
SORTED_LISTS = {"signal.interests.entities", "filter.results.entities"}
SPECIALTY = ["22B1BC87-CDFE-4340-86F8-8E0E6E1E6A7D", "E6BC1B43-71EA-4CAD-9CF5-BCADD6951F31", "D012BBB3-EA3F-45E6-BA69-1710C0947A7D"]


def load(rel: str) -> Any:
    return json.loads((FIX / rel).read_text())


def norm(params: list[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((k, ",".join(sorted(v.split(","))) if k in SORTED_LISTS else v) for k, v in params))


class FakeQloo:
    """Serves recorded fixtures by normalised params. Two documented synthetic cases:
    /search for a name with no fixture returns no results; filter.results.entities (per-product fit) returns the
    requested recorded places with a deterministic affinity per (signal, venue). Anything else fails the test."""

    def __init__(self) -> None:
        self.exact: dict[Any, Any] = {}
        self.search: dict[str, Any] = {}
        self.places: dict[str, Any] = {}
        self.requests: list[dict[str, str]] = []
        self.status_override: int | None = None
        self.fail_next: list[int] = []
        self.fail_if: Any = None  # callable(params dict) -> status code or None
        for f in sorted((FIX / "qloo").glob("*.json")):
            d = json.loads(f.read_text())
            req = d["request"]
            if req["path"] == "/search":
                self.search[dict(req["params"])["query"].lower()] = d["body"]
            else:
                self.exact[(req["path"], norm([tuple(p) for p in req["params"]]))] = (d["status"], d["body"])
                for e in ((d["body"].get("results") or {}).get("entities") or []):
                    self.places.setdefault(e["entity_id"], e)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-api-key") == "test-key"
        params = parse_qsl(request.url.query.decode())
        self.requests.append(dict(params))
        if self.fail_next or self.status_override:
            return httpx.Response(self.fail_next.pop(0) if self.fail_next else self.status_override, json={"error": "fake"})
        path = request.url.path
        if self.fail_if and (code := self.fail_if(dict(params))):
            return httpx.Response(code, json={"error": "fake"})
        if path == "/search":
            return httpx.Response(200, json=self.search.get(dict(params)["query"].lower(), {"results": []}))
        hit = self.exact.get((path, norm(params)))
        if hit:
            return httpx.Response(hit[0], json=hit[1])
        p = dict(params)
        if path == "/v2/insights" and "filter.results.entities" in p:
            signal = ",".join(sorted(p["signal.interests.entities"].split(",")))
            out = []
            for vid in p["filter.results.entities"].split(","):
                if vid in self.places:
                    aff = int(hashlib.sha256(f"{signal}:{vid}".encode()).hexdigest()[:6], 16) / 0xFFFFFF
                    out.append({**self.places[vid], "query": {"affinity": aff}})
            return httpx.Response(200, json={"success": True, "results": {"entities": out}})
        raise AssertionError(f"No Qloo fixture for {path} {sorted(params)}")


SITE = '<html><body><h1>{host}</h1><p>Coffee, pastries and natural wine.</p><a href="mailto:hello@{host}">Email us</a></body></html>'


def fake_site(request: httpx.Request) -> httpx.Response:
    host = (request.url.host or "").removeprefix("www.")
    if "broken" in host:
        return httpx.Response(500)
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return httpx.Response(200, html=SITE.format(host=host))


@pytest.fixture
def fake_qloo() -> FakeQloo:
    return FakeQloo()


@pytest.fixture
def net(fake_qloo: FakeQloo, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Every outbound request is mocked; an unmocked request fails the test (assert_all_mocked)."""

    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(website, "system_resolver", resolver)
    s = get_settings()
    with respx.mock(assert_all_called=False) as m:
        m.route(host="hackathon.api.qloo.com").mock(side_effect=fake_qloo)
        m.route(url__startswith=s.overpass_base_url).mock(return_value=httpx.Response(200, json=load("overpass/brooklyn_cafe.json")))
        m.route(url__startswith=s.nominatim_base_url).mock(return_value=httpx.Response(200, json=load("nominatim/brooklyn.json")))
        m.route(host="ollama.com").mock(side_effect=AssertionError("no live LLM calls in tests"))
        m.route(host="api.hunter.io", name="hunter").mock(side_effect=AssertionError("no live Hunter calls in tests"))
        m.route().mock(side_effect=fake_site)
        yield m


@pytest.fixture
async def svc(net: Any) -> Any:
    s = get_settings()
    pool = await db.open_pool(s.database_url)
    tables = await pool.fetch(
        "select tablename from pg_tables where schemaname = 'public' and tablename <> 'schema_migrations'")
    await pool.execute("truncate " + ", ".join(t["tablename"] for t in tables) + " cascade")
    deps.limiter.hits.clear()
    services = build_services(s, pool)

    async def no_sleep(_: float) -> None:
        return None

    services.qloo.sleep = no_sleep  # retry backoff
    app.state.svc = services
    yield services
    await run_service.drain()
    await close_services(services)
    await db.close_pool()


@pytest.fixture
async def client(svc: Any) -> Any:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def new_workspace(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post("/v1/workspaces/session", json={})
    assert r.status_code == 200, r.text
    return {"X-Workspace-Token": r.json()["workspace_token"]}


@pytest.fixture
async def ws(client: httpx.AsyncClient) -> dict[str, str]:
    return await new_workspace(client)


BROOKLYN = {"name": "Brooklyn", "display_name": "Brooklyn, Kings County, New York, United States", "country": "us",
            "lat": 40.6526, "lon": -73.9497, "bbox": [40.5503390, -74.0566880, 40.7394340, -73.8329450]}
BRAND = {
    "name": "Fieldnote Coffee",
    "profile": {"one_liner": "Small-batch cold brew and espresso from Brooklyn", "category": "food_drink",
                "price_tier": "premium", "style_words": ["small-batch", "specialty"], "sender_name": "Mara"},
    "products": [{"name": "Cold Brew Concentrate", "kind": "cold brew"}, {"name": "House Espresso", "kind": "espresso"}],
}


def comparables(*names: str) -> LLMResult:
    return LLMResult(content=json.dumps({"names": list(names)}))


async def make_brand(client: httpx.AsyncClient, ws: dict[str, str], svc: Any, *, resolve: bool = True) -> dict[str, Any]:
    r = await client.post("/v1/brands", json=BRAND, headers=ws)
    assert r.status_code == 201, r.text
    out = r.json()
    if resolve:
        svc.llm.provider.script = [comparables("Blue Bottle Coffee", "Stumptown Coffee Roasters"), comparables("La Colombe")]
        r = await client.post(f"/v1/brands/{out['brand_id']}/resolve", headers=ws)
        assert r.status_code == 200, r.text
        out["resolution"] = r.json()
    return out


async def scout(client: httpx.AsyncClient, ws: dict[str, str], brand: dict[str, Any], types: list[str] | None = None) -> str:
    r = await client.post("/v1/runs", headers=ws, json={
        "brand_id": brand["brand_id"], "product_ids": brand["product_ids"], "city": BROOKLYN, "venue_types": types or ["cafe"]})
    assert r.status_code == 202, r.text
    await run_service.drain()
    return str(r.json()["run_id"])
