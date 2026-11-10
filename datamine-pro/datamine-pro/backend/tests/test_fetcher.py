"""HttpFetcher behaviour using httpx.MockTransport (no real network)."""
import asyncio
import sys
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.enrichment.fetcher import HttpFetcher, LookupFailed, make_osm_lookup  # noqa: E402

PUBLIC = ["93.184.216.34"]


async def public_resolver(host, port):
    return PUBLIC


async def private_resolver(host, port):
    return ["10.0.0.5"]


def html(body="<html><title>ok</title></html>", ctype="text/html; charset=utf-8", status=200, headers=None):
    return httpx.Response(status, content=body.encode(), headers={"content-type": ctype, **(headers or {})})


def fetch(handler, url, resolver=public_resolver, **kwargs):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = HttpFetcher(client, "TestBot/1.0", host_delay=0, resolver=resolver, **kwargs)
            return await fetcher.get(url)

    return asyncio.run(go())


def test_fetches_html_when_robots_missing():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return html("<html><title>Bonjour</title></html>")

    page = fetch(handler, "https://exemple.fr/")
    assert page and "Bonjour" in page.html and page.url == "https://exemple.fr/"


def test_robots_disallow_blocks_fetch_and_page_is_never_requested():
    requested = []

    def handler(request):
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /")
        return html()

    assert fetch(handler, "https://exemple.fr/") is None
    assert requested == ["/robots.txt"]


def test_robots_errors_are_treated_conservatively():
    def handler(request):
        return httpx.Response(403) if request.url.path == "/robots.txt" else html()

    assert fetch(handler, "https://exemple.fr/") is None


def test_redirects_are_followed_and_final_url_reported():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "exemple.fr":
            return httpx.Response(301, headers={"location": "https://www.exemple.fr/accueil"})
        return html("<html><title>Final</title></html>")

    page = fetch(handler, "https://exemple.fr")
    assert page and page.url == "https://www.exemple.fr/accueil" and "Final" in page.html


def test_redirect_loops_are_cut_off():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "https://exemple.fr/again"})

    assert fetch(handler, "https://exemple.fr/") is None


def test_private_addresses_are_never_requested():
    calls = []

    def handler(request):
        calls.append(request.url)
        return html()

    assert fetch(handler, "https://interne.exemple.fr/", resolver=private_resolver) is None
    assert calls == []


def test_non_http_and_localhost_are_refused():
    def handler(request):
        raise AssertionError("must not be called")

    assert fetch(handler, "ftp://exemple.fr/") is None
    assert fetch(handler, "http://localhost/") is None


def test_non_html_content_is_ignored():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return html("%PDF-1.4", ctype="application/pdf")

    assert fetch(handler, "https://exemple.fr/doc") is None


def test_response_size_is_capped():
    big = "a" * 50_000

    def handler(request):
        return httpx.Response(404) if request.url.path == "/robots.txt" else html(big)

    page = fetch(handler, "https://exemple.fr/", max_bytes=1_000)
    assert page and len(page.html) <= 1_000


def test_network_errors_become_none():
    def handler(request):
        raise httpx.ConnectError("down")

    assert fetch(handler, "https://exemple.fr/") is None



def test_osm_429_opens_worker_local_circuit_breaker(monkeypatch):
    calls = 0

    async def limited_source(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise LookupFailed("openstreetmap HTTP 429")

    monkeypatch.setattr("app.enrichment.fetcher._get_source", limited_source)

    async def go():
        async with httpx.AsyncClient() as client:
            lookup = make_osm_lookup(client, "DataMineProTest/1.0")
            company = {"name": "Example Shop", "address": "75001 Paris", "country": "France"}
            assert await lookup(company) == []
            assert await lookup(company) == []

    asyncio.run(go())
    assert calls == 1
