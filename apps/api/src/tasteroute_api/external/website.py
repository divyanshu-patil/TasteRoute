"""Website reader with SSRF guard (F01, SEC-02) and published-email finder for venue sites (F06, D-08)."""

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import tldextract

from ..errors import AppError

MAX_BYTES = 1_500_000
MAX_REDIRECTS = 3
MAX_CHARS = 12_000
PAGE_HINTS = re.compile(r"about|shop|product|menu|story|range|our-", re.I)
CONTACT_HINTS = re.compile(r"contact|wholesale|trade|stockist|info", re.I)
LINK = re.compile(r"<a\b[^>]*href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
MAILTO = re.compile(r"mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", re.I)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
JUNK_EMAIL = re.compile(
    r"(^example@|example\.|mysite\.|yoursite|yourdomain|yourname|sentry|wixpress|godaddy|domain\.com|email\.com"
    r"|^no-?reply@|^donotreply@|\.(png|jpg|jpeg|gif|webp|svg)$)", re.I)
# Bundled public-suffix list, no network. ".test" is the RFC 2606 name our fixtures use.
_SUFFIXES = tldextract.TLDExtract(suffix_list_urls=(), extra_suffixes=("test",))

Resolver = Callable[[str], Awaitable[list[str]]]


class UrlNotAllowed(AppError):
    code, status, title = "url_not_allowed", 422, "That address is not allowed"


class WebsiteUnreadable(AppError):
    code, status, title = "website_unreadable", 422, "We couldn't read that site. Describe your brand instead."


# A 403 or a Cloudflare challenge: the owner turned automated readers away. We respect that and never work around it.
BLOCKED = "That site blocks automated readers like ours"


async def system_resolver(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return list({str(i[4][0]) for i in infos})


def ip_allowed(ip: str) -> bool:
    a = ipaddress.ip_address(ip.split("%")[0])
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    return not (
        a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified
        or a in ipaddress.ip_network("100.64.0.0/10")
    )


async def check_url(url: str, resolver: Resolver | None = None) -> str:
    if len(url) > 2048:
        raise UrlNotAllowed("URL is too long")
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise UrlNotAllowed("Only http and https addresses are allowed")
    host = p.hostname
    try:
        ips = [host] if _is_ip(host) else await (resolver or system_resolver)(host)
    except OSError as e:
        raise WebsiteUnreadable("The site's address could not be resolved") from e
    if not ips or not all(ip_allowed(ip) for ip in ips):
        raise UrlNotAllowed("That address points to a private or reserved network")
    return url


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


@dataclass
class Page:
    url: str
    html: str
    status: int


@dataclass
class SiteText:
    pages: list[str] = field(default_factory=list)
    text: str = ""


class WebsiteReader:
    def __init__(self, http: httpx.AsyncClient, resolver: Resolver | None = None, timeout: float = 12.0) -> None:
        self.http = http
        self.resolver = resolver
        self.timeout = timeout
        self._robots: dict[str, RobotFileParser | None] = {}

    async def fetch(self, url: str, *, check_robots: bool = True) -> Page:
        """GET with SSRF checks on every hop, at most 3 redirects, html only, 1.5 MB cap."""
        for _ in range(MAX_REDIRECTS + 1):
            await check_url(url, self.resolver)
            if check_robots and not await self._robots_ok(url):
                raise WebsiteUnreadable("robots.txt disallows reading this page")
            try:
                async with self.http.stream("GET", url, timeout=self.timeout, follow_redirects=False) as r:
                    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                        url = urljoin(url, r.headers["location"])
                        continue
                    ctype = r.headers.get("content-type", "")
                    if r.status_code == 403 or r.headers.get("cf-mitigated"):
                        raise WebsiteUnreadable(f"{BLOCKED}. Describe your brand instead.")
                    if r.status_code != 200 or "html" not in ctype:
                        raise WebsiteUnreadable(f"Site returned {r.status_code} {ctype.split(';')[0]}".strip())
                    buf = b""
                    async for chunk in r.aiter_bytes():
                        buf += chunk
                        if len(buf) > MAX_BYTES:
                            break
                    return Page(str(r.url), buf[:MAX_BYTES].decode(r.encoding or "utf-8", "replace"), 200)
            except httpx.HTTPError as e:
                raise WebsiteUnreadable(f"Could not fetch the site ({type(e).__name__})") from e
        raise WebsiteUnreadable("Too many redirects")

    async def _robots_ok(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp: RobotFileParser | None = None
            try:
                await check_url(base + "/robots.txt", self.resolver)
                r = await self.http.get(base + "/robots.txt", timeout=self.timeout, follow_redirects=False)
                if r.status_code == 200 and len(r.content) < 500_000:
                    rp = RobotFileParser()
                    rp.parse(r.text.splitlines())
            except (httpx.HTTPError, AppError):
                rp = None
            self._robots[base] = rp
        rp = self._robots[base]
        return True if rp is None else rp.can_fetch("TasteRoute", url)

    async def read_site(self, url: str) -> SiteText:
        """Homepage plus at most 2 same-domain about/shop/product/menu pages; at most 12,000 characters (INT-01)."""
        home = await self.fetch(url)
        pages = [home]
        for link in pick_links(home, PAGE_HINTS, 2):
            try:
                pages.append(await self.fetch(link))
            except AppError:
                continue
        out = SiteText(pages=[p.url for p in pages])
        out.text = "\n\n".join([site_name(home.html)] + [extract_text(p.html) for p in pages]).strip()[:MAX_CHARS]
        if len(out.text.strip()) < 40:
            raise WebsiteUnreadable("The site has too little readable text")
        return out

    async def find_emails(self, url: str) -> list[tuple[str, str]]:
        """Business emails published on the venue's own site: (email, page url). Never constructed (CON-05)."""
        home = await self.fetch(url)
        found = emails_in(home)
        if not found:
            for link in pick_links(home, CONTACT_HINTS, 2):
                try:
                    found += emails_in(await self.fetch(link))
                except AppError:
                    continue
        first: dict[str, str] = {}
        for e, u in found:
            first.setdefault(e, u)
        return list(first.items())


def same_site(a: str, b: str) -> bool:
    ha, hb = urlparse(a).hostname or "", urlparse(b).hostname or ""
    return ha.removeprefix("www.") == hb.removeprefix("www.")


def pick_links(page: Page, hints: re.Pattern[str], limit: int) -> list[str]:
    out: list[str] = []
    for href, text in LINK.findall(page.html):
        url = urljoin(page.url, href.strip())
        if (
            url.startswith(("http://", "https://")) and same_site(url, page.url) and url.rstrip("/") != page.url.rstrip("/")
            and (hints.search(href) or hints.search(re.sub(r"<[^>]+>", "", text))) and url not in out
        ):
            out.append(url)
        if len(out) >= limit:
            break
    return out


def clean_email(raw: str) -> str | None:
    """A published address as written, minus page text glued after it ('info@x.com.Hours' -> 'info@x.com').
    None for placeholders, no-reply inboxes and anything without a real domain suffix."""
    local, _, domain = raw.strip().lower().partition("@")
    labels = domain.split(".")
    for n in range(len(labels), 1, -1):
        d = ".".join(labels[:n])
        ext = _SUFFIXES(d)
        if local and ext.domain and ext.suffix and d.endswith("." + ext.suffix):
            e = f"{local}@{d}"
            return None if JUNK_EMAIL.search(e) else e
    return None


def emails_in(page: Page) -> list[tuple[str, str]]:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", page.html)  # library credits live in scripts
    raw = MAILTO.findall(html) + EMAIL.findall(re.sub(r"<[^>]+>", " ", unescape(html)))
    cleaned = (clean_email(e) for e in raw)
    return [(e, page.url) for e in dict.fromkeys(c for c in cleaned if c)]


def site_name(html: str) -> str:
    """The brand's name usually lives only in <title> or og:site_name, which body-text extraction drops."""
    og = re.search(r"<meta[^>]+property=[\"']og:site_name[\"'][^>]+content=[\"']([^\"']+)", html, re.I)
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    parts = [unescape(m.group(1)).strip() for m in (og, title) if m]
    return "Site name: " + " | ".join(dict.fromkeys(p for p in parts if p)) if any(parts) else ""


def extract_text(html: str) -> str:
    try:
        import trafilatura

        text = trafilatura.extract(html, include_comments=False) or ""
    except Exception:  # pragma: no cover - trafilatura edge cases
        text = ""
    if len(text) < 40:
        text = re.sub(r"(?s)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
        text = unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).strip()
