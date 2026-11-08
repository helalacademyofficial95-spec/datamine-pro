"""Queue recovery, bounded retry, honest 'done' marking, OSM discovery and resume behaviour."""
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("httpx")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.enrichment import NOT_FOUND, VERIFIED, runner  # noqa: E402
from app.enrichment.discovery import osm_search_url, parse_osm_response  # noqa: E402
from app.enrichment.pipeline import FetchedPage, enrich_company  # noqa: E402

TODAY = date(2026, 11, 6)
COMPANY = {"name": "MAISON LILAS", "siren": "123456789", "country": "France",
           "address": "5 place du Marche 69001 LYON", "website": ""}
SHOP = """<html><head><title>Maison Lilas</title></head><body><a href="/mentions-legales">Mentions légales</a>
<a href="/cart">Panier</a><button>Ajouter au panier</button><p>A 12,00 € B 29,00 € C 6,00 €</p></body></html>"""
LEGAL = "<html><title>Mentions légales</title><body>Maison Lilas SARL, 5 place du Marche, 69001 Lyon. RCS Lyon 123 456 789</body></html>"


class Web:
    def __init__(self, pages):
        self.pages = pages

    async def get(self, url):
        for key, html in self.pages.items():
            if url.rstrip("/") == key.rstrip("/"):
                return FetchedPage(url=key, html=html)
        return None


def run(coro):
    return asyncio.run(coro)


# ---- discovery -------------------------------------------------------------------------
def test_osm_candidate_is_found_and_verified_on_the_site_itself():
    async def osm(company):
        return ["https://lilas-boutique.fr"]

    web = Web({"https://lilas-boutique.fr": SHOP, "https://lilas-boutique.fr/mentions-legales": LEGAL})
    r = run(enrich_company(COMPANY, web, osm=osm, today=TODAY))
    assert r["officialWebsiteSource"] == "openstreetmap" and r["officialWebsiteStatus"] == VERIFIED
    assert r["discoveryComplete"] is True and r["b2cWebsite"] == "https://lilas-boutique.fr"


def test_osm_parser_requires_name_overlap_and_ignores_unrelated_places():
    payload = [
        {"name": "Maison Lilas", "display_name": "Maison Lilas, Lyon", "extratags": {"website": "https://lilas.example"}},
        {"name": "Garage Dupont", "display_name": "Garage Dupont, Lyon", "extratags": {"website": "https://dupont.example"}},
    ]
    assert parse_osm_response(payload, "MAISON LILAS") == ["https://lilas.example"]
    assert parse_osm_response("garbage", "MAISON LILAS") == []
    assert "countrycodes=fr" in osm_search_url("MAISON LILAS", "69001", "LYON")


def test_failed_source_makes_discovery_inconclusive_not_a_clean_not_found():
    async def broken(siren):
        raise RuntimeError("wikidata HTTP 503")

    r = run(enrich_company(COMPANY, Web({}), wikidata=broken, today=TODAY))
    assert r["officialWebsiteStatus"] == NOT_FOUND
    assert r["discoveryComplete"] is False and "wikidata HTTP 503" in r["sourceErrors"][0]


def test_clean_not_found_is_conclusive():
    async def empty(siren):
        return []

    r = run(enrich_company(COMPANY, Web({}), wikidata=empty, today=TODAY))
    assert r["officialWebsiteStatus"] == NOT_FOUND and r["discoveryComplete"] is True


def test_unreachable_registry_website_is_inconclusive():
    r = run(enrich_company({**COMPANY, "website": "https://down.example"}, Web({}), today=TODAY))
    assert r["discoveryComplete"] is False


# ---- worker: honest done / retry ----------------------------------------------------------
class FakeQueue:
    def __init__(self, batches):
        self.batches = list(batches)
        self.done, self.failed = [], []

    def claim_batch(self, url, limit):
        return self.batches.pop(0) if self.batches else []

    def mark_done(self, url, record):
        self.done.append(record["siren"])

    def mark_failed(self, url, record, error):
        self.failed.append((record["siren"], error))

    def touch(self, url, records):
        return len(records)

    def has_ready_work(self, url):
        return bool(self.batches)


@pytest.fixture
def worker(monkeypatch):
    runner.state.update(running=False, startedAt=None, finishedAt=None, target=0, processed=0,
                        failed=0, officialWebsitesFound=0, b2cMatches=0, lastError=None)
    saved = {}
    monkeypatch.setattr(runner.store, "save_one", lambda url, key, data: saved.__setitem__(key, data))
    from app.enrichment import queue as q
    fake = FakeQueue([])
    for name in ("claim_batch", "mark_done", "mark_failed", "touch", "has_ready_work"):
        monkeypatch.setattr(q, name, getattr(fake, name))

    async def no_lookup(arg):
        return []

    monkeypatch.setattr(runner, "make_wikidata_lookup", lambda c, ua: no_lookup)
    monkeypatch.setattr(runner, "make_osm_lookup", lambda c, ua: no_lookup)
    monkeypatch.setattr(runner, "HttpFetcher", lambda c, ua: Web({}))
    return fake, saved


def test_worker_drains_every_batch_and_marks_done(worker):
    fake, saved = worker
    fake.batches = [[{**COMPANY, "siren": "100000001"}, {**COMPANY, "siren": "100000002", "name": "ATELIER ROSE"}],
                    [{**COMPANY, "siren": "100000003", "name": "BOULANGERIE SOLEIL"}]]
    run(runner.run_queue(database_url="x", user_agent="t"))
    assert sorted(fake.done) == ["100000001", "100000002", "100000003"] and fake.failed == []
    assert len(saved) == 3 and runner.state["running"] is False and runner.state["target"] == 3


def test_worker_never_marks_done_when_discovery_was_inconclusive(worker, monkeypatch):
    fake, saved = worker

    async def boom(arg):
        raise RuntimeError("openstreetmap HTTP 429")

    monkeypatch.setattr(runner, "make_osm_lookup", lambda c, ua: boom)
    fake.batches = [[{**COMPANY, "siren": "100000001"}]]
    run(runner.run_queue(database_url="x", user_agent="t"))
    assert fake.done == []
    assert fake.failed and "discovery inconclusive" in fake.failed[0][1] and "429" in fake.failed[0][1]
    assert runner.state["failed"] == 1


def test_worker_exception_goes_to_mark_failed_with_details(worker, monkeypatch):
    fake, _ = worker

    async def explode(*a, **k):
        raise ValueError("bad record")

    monkeypatch.setattr(runner, "enrich_company", explode)
    fake.batches = [[{**COMPANY, "siren": "100000001"}]]
    run(runner.run_queue(database_url="x", user_agent="t"))
    assert fake.failed[0][1].startswith("ValueError: bad record") and fake.done == []


def test_resume_only_when_idle_and_work_is_ready(worker):
    fake, _ = worker

    async def go():
        assert await runner.resume_if_needed(database_url="x", user_agent="t") is False  # nothing ready
        fake.batches = [[{**COMPANY, "siren": "100000001"}]]
        started = await runner.resume_if_needed(database_url="x", user_agent="t")
        await asyncio.sleep(0.2)
        runner.state["running"] = True
        again = await runner.resume_if_needed(database_url="x", user_agent="t")
        return started, again

    started, again = run(go())
    assert started is True and again is False and fake.done == ["100000001"]


# ---- real SQL (needs TEST_DATABASE_URL pointing at a throwaway Postgres) ------------------
DB = os.environ.get("TEST_DATABASE_URL", "")


@pytest.mark.skipif(not DB, reason="TEST_DATABASE_URL not set")
def test_stale_recovery_sql_is_safe_and_bounded():
    psycopg = pytest.importorskip("psycopg")
    from app.enrichment import queue as q

    q.init_table(DB)
    with psycopg.connect(DB) as c:
        c.execute("DELETE FROM enrichment_queue WHERE country='ZZ'")
        rows = [("1", "processing", 1, "2 days"), ("2", "processing", 3, "2 days"),
                ("3", "processing", 1, "2 minutes"), ("4", "pending", 0, None), ("5", "done", 1, None)]
        for number, status, attempts, age in rows:
            c.execute("""INSERT INTO enrichment_queue (country, registration_number, record, status, attempts, locked_at)
                         VALUES ('ZZ', %s, '{"country":"ZZ"}'::jsonb, %s, %s,
                                 CASE WHEN %s::text IS NULL THEN NULL ELSE NOW() - %s::interval END)""",
                      (number, status, attempts, age, age))
    out = q.recover_stale(DB)
    assert out["requeued"] >= 1 and out["failed"] >= 1
    with psycopg.connect(DB) as c:
        state = dict(c.execute("SELECT registration_number, status FROM enrichment_queue WHERE country='ZZ'").fetchall())
        c.execute("DELETE FROM enrichment_queue WHERE country='ZZ'")
    assert state == {"1": "pending", "2": "failed", "3": "processing", "4": "pending", "5": "done"}
