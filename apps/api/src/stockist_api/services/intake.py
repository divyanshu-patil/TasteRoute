"""F01: brand intake from a website or a description. The LLM proposes; the user confirms."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..agent.context import Services
from ..categories import UNSUPPORTED, all_packs, default_pack
from ..errors import AppError, LLMBadResponse, LLMUnavailable
from ..external import cached_call
from ..external.website import WebsiteReader, WebsiteUnreadable, check_url
from ..llm.prompts import load
from ..llm.structured import structured

MAX_PRODUCTS = 5


class ProductDraft(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=500)


class BrandProfile(BaseModel):
    brand_name: str = Field(default="", max_length=120)
    one_liner: str = Field(default="", max_length=200)
    category: str = Field(default_factory=lambda: default_pack().id, max_length=40)
    prospects_are_consumer_facing: bool = True
    price_tier: Literal["budget", "mid", "premium", "unknown"] = "unknown"
    style_words: list[str] = Field(default_factory=list)
    products: list[ProductDraft] = Field(default_factory=list)
    unsupported_reason: str | None = None


    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        return v if v in all_packs() else UNSUPPORTED


def unsupported(p: BrandProfile) -> bool:
    return p.category == UNSUPPORTED or not p.prospects_are_consumer_facing


UNSUPPORTED_MESSAGE = (
    "Stockist Scout ranks businesses by what their customers like. Your prospects seem to be chosen on company "
    "size and industry, which Qloo does not cover. A company-data tool (for example Apollo or Clay) fits better."
)


async def propose(svc: Services, website_url: str | None, description: str | None) -> dict[str, Any]:
    text, pages, notice = "", [], None
    if website_url:
        await check_url(website_url)  # url_not_allowed before any network call (SEC-02)
        reader = WebsiteReader(svc.http, timeout=svc.settings.website_fetch_timeout_seconds)

        async def fetch() -> tuple[int, Any]:
            try:
                site = await reader.read_site(website_url)
                return 200, {"pages": site.pages, "text": site.text}
            except WebsiteUnreadable as e:
                return 422, {"error": e.detail}

        status, body, _, _ = await cached_call(svc.pool, "website", website_url, {"url": website_url}, timedelta(days=7), fetch)
        if status == 200 and body:
            text, pages = body["text"], body["pages"]
        elif not description:
            raise WebsiteUnreadable((body or {}).get("error", "") or WebsiteUnreadable.title)
        else:
            notice = "We couldn't read that site, so we used your description."
    if description:
        text = (text + "\n\n" if text else "") + description[:1500]
    prompt, version = load("brand_profile")
    tag = "website" if website_url and pages else "description"
    profile: BrandProfile
    source = "llm"
    try:
        profile = await structured(svc.llm, BrandProfile, prompt, f"<{tag}>\n{text}\n</{tag}>", purpose="brand_profile",
                                   prompt_version=version, max_tokens=900)
    except (LLMUnavailable, LLMBadResponse):
        profile, source = BrandProfile(), "empty"
        notice = "We couldn't draft a profile automatically. Fill in the form below."
    profile.products = profile.products[:MAX_PRODUCTS]
    profile.style_words = profile.style_words[:6]
    profile.one_liner = profile.one_liner[:140]
    return {
        "profile": profile.model_dump(),
        "source": source,
        "pages": pages,
        "notice": notice,
        "unsupported": unsupported(profile),
        "unsupported_message": UNSUPPORTED_MESSAGE if unsupported(profile) else None,
        "source_text": text[:12_000],
    }


class UnsupportedBusiness(AppError):
    code, status, title = "unsupported_business", 422, UNSUPPORTED_MESSAGE
