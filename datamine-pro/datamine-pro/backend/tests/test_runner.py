"""Batch runner orchestration with fakes for fetching and storage (fictional companies)."""
import asyncio
import sys
from pathlib import Path

import pytest

pytest.importorskip("httpx")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.enrichment import runner  # noqa: E402
from app.enrichment.pipeline import FetchedPage  # noqa: E402

LEGAL_TMPL = "<html><title>Mentions légales</title><body>{name} SARL, {addr}. RCS Lyon {siren_spaced}</body></html>"
HOME_TMPL = """<html><head><title>{name}</title></head><body>
<a href="/mentions-legales">Mentions légales</a><a href="/cart">Panier</a>
<button>Ajouter au panier</button><p>Produit 10,00 € Produit 20,00 € Produit 30,00 €</p></body></html>"""


def company(i: int, name: str) -> dict:
    siren = f"10000000{i}"
    return {"id": f"fr-{siren}", "siren": siren, "country": "France", "name": name,
            "address": "5 place du Marche 69001 LYON", "website": ""}


class FakeWeb:
    def __init__(self, pages):
        self.pages = pages

    async def get(self, url):
        for key, html in self.pages.items():
            if url.rstrip("/") == key.rstrip("/"):
                return FetchedPage(url=key, html=html)
        return None


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    runner.state.update(running=False, startedAt=None, finishedAt=None, target=0, processed=0,
                        failed=0, officialWebsitesFound=0, b2cMatches=0, lastError=None)
    saved: dict = {}
    existing: dict = {}
    monkeypatch.setattr(runner.store, "load_map", lambda url: dict(existing))
    monkeypatch.setattr(runner.store, "save_one", lambda url, key, data: saved.__setitem__(key, data))

    async def no_wikidata(siren):
        return []

    monkeypatch.setattr(runner, "make_wikidata_lookup", lambda client, ua: no_wikidata)
    return saved, existing


def install_web(monkeypatch, pages):
    web = FakeWeb(pages)
    monkeypatch.setattr(runner, "HttpFetcher", lambda client, ua: web)


def go(records, limit=10, force=False):
    asyncio.run(runner.run_batch(database_url="postgres://x", user_agent="t", load_records=lambda: records, limit=limit, force=force))


def test_batch_saves_each_result_and_counts(monkeypatch, reset_state):
    saved, _ = reset_state
    a, b = company(1, "MAISON LILAS"), company(2, "ATELIER ROSE")
    pages = {
        "https://maisonlilas.fr": HOME_TMPL.format(name="Maison Lilas"),
        "https://maisonlilas.fr/mentions-legales": LEGAL_TMPL.format(name="Maison Lilas", addr="5 place du Marche, 69001 Lyon", siren_spaced="100 000 001"),
    }
    install_web(monkeypatch, pages)
    go([a, b])
    assert set(saved) == {("France", "100000001"), ("France", "100000002")}
    assert saved[("France", "100000001")]["officialWebsiteStatus"] == "Verified"
    assert saved[("France", "100000002")]["officialWebsiteStatus"] == "Not Found"
    assert runner.state["processed"] == 2 and runner.state["officialWebsitesFound"] == 1
    assert runner.state["running"] is False and runner.state["finishedAt"]


def test_already_enriched_and_limit_are_respected(monkeypatch, reset_state):
    saved, existing = reset_state
    existing[("France", "100000001")] = {"x": 1}
    install_web(monkeypatch, {})
    go([company(i, f"SOCIETE NUMERO{i}") for i in range(1, 6)], limit=2)
    assert set(saved) == {("France", "100000002"), ("France", "100000003")}
    assert runner.state["target"] == 2


def test_one_failing_company_does_not_stop_the_batch(monkeypatch, reset_state):
    saved, _ = reset_state
    install_web(monkeypatch, {})
    original = runner.enrich_company

    async def flaky(record, fetcher, wikidata=None, today=None):
        if record["siren"] == "100000001":
            raise RuntimeError("boom")
        return await original(record, fetcher, wikidata, today)

    monkeypatch.setattr(runner, "enrich_company", flaky)
    go([company(1, "ALPHA SOCIETE"), company(2, "BETA SOCIETE")])
    assert set(saved) == {("France", "100000002")}
    assert runner.state["failed"] == 1 and runner.state["processed"] == 1
    assert "RuntimeError" in runner.state["lastError"]


def test_second_batch_is_ignored_while_running(monkeypatch, reset_state):
    saved, _ = reset_state
    runner.state["running"] = True
    go([company(1, "ALPHA SOCIETE")])
    assert saved == {} and runner.state["running"] is True


def test_load_failure_is_reported_and_running_flag_released(reset_state):
    def broken():
        raise OSError("db down")

    asyncio.run(runner.run_batch(database_url="postgres://x", user_agent="t", load_records=broken, limit=5))
    assert runner.state["running"] is False and "OSError" in runner.state["lastError"]
