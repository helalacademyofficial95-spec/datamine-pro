"""Polite, SSRF-safe HTTP fetching for enrichment (the only module here that needs httpx).

Rules enforced on every request: public IPs only, robots.txt honoured, at most one request per
host per `host_delay` seconds, redirects followed manually (each hop re-checked), HTML only,
response size capped, every error becomes "no page" rather than an exception.
"""
from __future__ import annotations

import asyncio
import ipaddress
import time
from typing import Awaitable, Callable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .discovery import osm_search_url, parse_osm_response, parse_wikidata_text, wikidata_url
from .pipeline import FetchedPage

Resolver = Callable[[str, int], Awaitable[list[str]]]
REDIRECT_CODES = {301, 302, 303, 307, 308}


async def _system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=0)
    return [info[4][0] for info in infos]


class HttpFetcher:
    def __init__(
        self,
        client: httpx.AsyncClient,
        user_agent: str,
        host_delay: float = 1.0,
        resolver: Resolver | None = None,
        max_redirects: int = 3,
        max_bytes: int = 1_000_000,
    ) -> None:
        self.client = client
        self.user_agent = user_agent
        self.host_delay = host_delay
        self.resolver = resolver or _system_resolver
        self.max_redirects = max_redirects
        self.max_bytes = max_bytes
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}  # None = fetching robots.txt failed -> disallow

    async def _public(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https") or not host:
            return False
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return False
        try:
            addresses = await self.resolver(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except OSError:
            return False
        try:
            return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)
        except ValueError:
            return False

    async def _throttle(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self.host_delay - (time.monotonic() - self._last.get(host, 0.0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[host] = time.monotonic()

    async def _request(self, url: str) -> tuple[int, dict[str, str], str] | None:
        """One GET without following redirects. Returns (status, headers, text) or None."""
        if not await self._public(url):
            return None
        await self._throttle((urlparse(url).hostname or "").lower())
        try:
            async with self.client.stream(
                "GET", url, headers={"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"},
                follow_redirects=False,
            ) as response:
                headers = {k.lower(): v for k, v in response.headers.items()}
                if response.status_code != 200:
                    return response.status_code, headers, ""
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= self.max_bytes:
                        break
                raw = b"".join(chunks)[: self.max_bytes]
                try:
                    text = raw.decode(response.charset_encoding or "utf-8", errors="replace")
                except LookupError:
                    text = raw.decode("utf-8", errors="replace")
                return response.status_code, headers, text
        except (httpx.HTTPError, OSError, ValueError):
            return None

    async def _robots_parser(self, url: str) -> RobotFileParser | None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        parser: RobotFileParser | None = RobotFileParser()
        current = f"{origin}/robots.txt"
        result = None
        for _ in range(self.max_redirects + 1):
            result = await self._request(current)
            if result and result[0] in REDIRECT_CODES and result[1].get("location"):
                current = urljoin(current, result[1]["location"])
                continue
            break
        if result is None:
            parser = None  # unreachable robots.txt: be conservative
        elif result[0] == 404:
            parser.parse([])  # no robots.txt: everything allowed
        elif result[0] == 200:
            parser.parse(result[2].splitlines())
        else:
            parser = None  # 401/403/5xx: be conservative
        self._robots[origin] = parser
        return parser

    async def allowed(self, url: str) -> bool:
        parser = await self._robots_parser(url)
        return parser is not None and parser.can_fetch(self.user_agent, url)

    async def get(self, url: str) -> FetchedPage | None:
        current = url
        for _ in range(self.max_redirects + 1):
            if not await self.allowed(current):
                return None
            result = await self._request(current)
            if result is None:
                return None
            status, headers, text = result
            if status in REDIRECT_CODES:
                location = headers.get("location")
                if not location:
                    return None
                current = urljoin(current, location)
                continue
            if status != 200:
                return None
            content_type = headers.get("content-type", "").lower()
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return None
            return FetchedPage(url=current, html=text)
        return None


class LookupFailed(Exception):
    """An external discovery source failed (as opposed to legitimately finding nothing).

    permanent=True means the source refuses us (401/403/451): retrying cannot help, and the
    refusal is not evidence that the company has no website.
    """

    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}
PERMANENT_STATUS = {401, 403, 451}


async def _get_source(client: httpx.AsyncClient, label: str, url: str, headers: dict[str, str],
                      pause: float, tries: int = 3) -> httpx.Response:
    """GET one public source with bounded exponential backoff on transient failures.

    Raises LookupFailed (permanent for 401/403/451, transient otherwise); never loops forever.
    """
    delay = 2.0
    last = "unknown error"
    for attempt in range(tries):
        try:
            response = await client.get(url, headers=headers, timeout=15.0)
        except httpx.HTTPError as exc:
            last = f"{label} unreachable: {type(exc).__name__}"
        else:
            await asyncio.sleep(pause)
            code = response.status_code
            if code == 200:
                return response
            if code in PERMANENT_STATUS:
                raise LookupFailed(f"{label} HTTP {code}", permanent=True)
            last = f"{label} HTTP {code}"
            if code not in TRANSIENT_STATUS:
                raise LookupFailed(last, permanent=True)
            try:
                delay = min(20.0, max(delay, float(response.headers.get("Retry-After", delay))))
            except (TypeError, ValueError):
                pass
        if attempt < tries - 1:
            await asyncio.sleep(delay)
            delay = min(20.0, delay * 2)
    raise LookupFailed(last)


def make_wikidata_lookup(client: httpx.AsyncClient, user_agent: str) -> Callable[[str], Awaitable[list[str]]]:
    """Free, keyless Wikidata SPARQL lookup (official website by SIREN). Serialised: one query at a time."""
    gate = asyncio.Semaphore(1)
    blocked: dict[str, bool] = {"value": False}

    async def lookup(siren: str) -> list[str]:
        if blocked["value"]:  # the host refuses us: do not hammer it for every company
            raise LookupFailed("wikidata HTTP 403", permanent=True)
        async with gate:
            try:
                response = await _get_source(
                    client, "wikidata", wikidata_url(siren),
                    {"User-Agent": user_agent, "Accept": "application/sparql-results+json"}, 0.5)
            except LookupFailed as exc:
                blocked["value"] = exc.permanent
                raise
            return parse_wikidata_text(response.text)

    return lookup


def make_osm_lookup(client: httpx.AsyncClient, user_agent: str) -> Callable[[dict], Awaitable[list[str]]]:
    """OpenStreetMap Nominatim lookup. Public-instance policy: identified User-Agent, at most one
    request per second, no bulk hammering - so queries are strictly serialised and spaced."""
    from .verify import _postal_and_city  # local import: avoids a module cycle

    gate = asyncio.Semaphore(1)

    async def lookup(company: dict) -> list[str]:
        name = str(company.get("name") or "")
        postal, city = _postal_and_city(str(company.get("address") or ""))
        if not name or not (postal or city):
            return []
        async with gate:
            response = await _get_source(
                client, "openstreetmap",
                osm_search_url(name, postal, city, str(company.get("country") or "France")),
                {"User-Agent": user_agent, "Accept": "application/json"}, 1.1)
            try:
                return parse_osm_response(response.json(), name)
            except ValueError as exc:
                raise LookupFailed("openstreetmap returned invalid JSON") from exc

    return lookup
