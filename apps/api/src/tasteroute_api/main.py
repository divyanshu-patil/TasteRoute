"""FastAPI app. Run with: uv run uvicorn tasteroute_api.main:app --reload"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__, db, errors
from .agent.context import Services
from .external.website import pinned_client
from .llm import LLM, make_provider
from .qloo.client import QlooClient
from .routes import brands, core, runs
from .services import runs as run_service
from .settings import Settings, get_settings


def build_services(s: Settings, pool: asyncpg.Pool) -> Services:
    qloo = QlooClient(
        api_key=s.qloo_api_key.get_secret_value(), base_url=s.qloo_base_url, pool=pool, rps=s.qloo_rps,
        timeout=s.qloo_timeout_seconds, cache_ttl_hours=s.qloo_cache_ttl_hours, max_calls_per_run=s.qloo_max_calls_per_run,
    )
    http = httpx.AsyncClient(timeout=20, headers={"User-Agent": s.osm_user_agent})
    return Services(settings=s, pool=pool, qloo=qloo, llm=LLM(make_provider(s), pool, s), http=http,
                    web=pinned_client(s.osm_user_agent))


async def close_services(svc: Services) -> None:
    await run_service.drain()
    await svc.qloo.aclose()
    await svc.llm.provider.aclose()
    await svc.http.aclose()
    await svc.web.aclose()


def check_production(s: Settings) -> None:
    """Refuse to boot production with the default session secret: anyone could sign workspace tokens (SEC-08)."""
    if s.app_env == "production" and s.session_secret.get_secret_value() in ("", "change-me"):
        raise RuntimeError("SESSION_SECRET is unset or 'change-me'. Set a long random value before starting in production.")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    logging.basicConfig(level=s.log_level.upper())
    check_production(s)
    pool = await db.open_pool(s.database_url, s.db_statement_cache_size)
    app.state.svc = build_services(s, pool)
    if n := await run_service.sweep_interrupted(app.state.svc):
        logging.getLogger("tasteroute").info("closed %d runs interrupted by a restart", n)
    yield
    await close_services(app.state.svc)
    await db.close_pool()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="TasteRoute API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origin_list, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Workspace-Token", "Last-Event-ID"], expose_headers=["Content-Disposition"],
    )
    errors.install(app)
    for r in (core.router, brands.router, runs.router):
        app.include_router(r)
    return app


app = create_app()
