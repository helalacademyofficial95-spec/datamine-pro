"""Discovery yield (legal-page fallback), never downgrading stored results, and real coverage counts."""
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.enrichment import NOT_FOUND, PARTIAL, UNVERIFIED, VERIFIED  # noqa: E402
from app.enrichment.merge import preserve_better  # noqa: E402
from app.enrichment.pipeline import FetchedPage, enrich_company  # noqa: E402

TODAY = date(2026, 11, 10)
COMPANY = {"name": "MAISON LILAS", "siren": "123456789", "country": "France",
           "address": "5 place du Marche 69001 LYON", "website": ""}
# Home page whose menu is rendered by JavaScript: it contains no link to the legal notice.
HOME_NO_LINKS = "<html><head><title>Maison Lilas</title></head><body><div id='app'>Maison Lilas, bougies</div></body></html>"
LEGAL = "<html><title>Mentions légales</title><body>Maison Lilas SARL, 5 place du Marche, 69001 Lyon. RCS Lyon 123 456 789</body></html>"


class Web:
    def __init__(self, pages):
        self.pages, self.requests = pages, []

    async def get(self, url):
        self.requests.append(url)
        for key, html in self.pages.items():
            if url.rstrip("/") == key.rstrip("/"):
                return FetchedPage(url=key, html=html)
        return None


def test_legal_notice_found_at_standard_path_when_home_has_no_footer_link():
    web = Web({"https://maisonlilas.fr": HOME_NO_LINKS, "https://maisonlilas.fr/mentions-legales": LEGAL})
    r = asyncio.run(enrich_company(COMPANY, web, today=TODAY))
    assert r["officialWebsite"] == "https://maisonlilas.fr" and r["officialWebsiteStatus"] == VERIFIED
    assert r["officialWebsiteSource"] == "domain_guess"


def test_site_without_any_registration_evidence_stays_unverified_not_accepted():
    web = Web({"https://maisonlilas.fr": HOME_NO_LINKS})
    r = asyncio.run(enrich_company(COMPANY, web, today=TODAY))
    assert r["officialWebsite"] is None and r["officialWebsiteStatus"] in (NOT_FOUND, UNVERIFIED)


# ---- never replace a better stored result with a worse one --------------------------------
GOOD = {"officialWebsite": "https://a.fr", "officialWebsiteStatus": VERIFIED, "officialWebsiteSource": "wikidata",
        "officialWebsiteEvidence": [{"type": "siren", "url": "https://a.fr/mentions"}], "b2cWebsite": "https://a.fr",
        "b2cStatus": VERIFIED, "contactEmail": "contact@a.fr", "contactEmailSource": "https://a.fr/contact",
        "checkedAt": "2026-11-01"}
WORSE = {"officialWebsite": None, "officialWebsiteStatus": NOT_FOUND, "b2cWebsite": None, "b2cStatus": NOT_FOUND,
         "contactEmail": None, "checkedAt": "2026-11-10", "discoveryComplete": False, "sourceErrors": ["x"]}


def test_worse_recheck_keeps_stored_verified_website_and_contacts():
    out = preserve_better(GOOD, WORSE)
    assert out["officialWebsite"] == "https://a.fr" and out["officialWebsiteStatus"] == VERIFIED
    assert out["contactEmail"] == "contact@a.fr" and out["b2cWebsite"] == "https://a.fr"
    assert out["preservedFromPrevious"] is True and out["sourceErrors"] == ["x"]


def test_better_or_equal_result_wins_and_fills_missing_contacts_for_same_site():
    better = {**GOOD, "officialWebsiteStatus": VERIFIED, "contactEmail": None, "contactEmailSource": None,
              "contactPhone": "+33 4 00 00 00 00", "contactPhoneSource": "https://a.fr/c", "checkedAt": "2026-11-10"}
    out = preserve_better(GOOD, better)
    assert out["checkedAt"] == "2026-11-10" and out["contactPhone"] == "+33 4 00 00 00 00"
    assert out["contactEmail"] == "contact@a.fr"      # same website: stored email is kept
    other_site = {**better, "officialWebsite": "https://b.fr"}
    assert not preserve_better(GOOD, other_site).get("contactEmail")
    assert preserve_better(None, WORSE) == WORSE
    partial_up = {**WORSE, "officialWebsite": "https://z.fr", "officialWebsiteStatus": PARTIAL}
    assert preserve_better({**GOOD, "officialWebsiteStatus": UNVERIFIED}, partial_up)["officialWebsite"] == "https://z.fr"


# ---- real SQL: coverage counts and save_one preservation -----------------------------------
DB = os.environ.get("TEST_DATABASE_URL", "")


@pytest.mark.skipif(not DB, reason="TEST_DATABASE_URL not set")
def test_coverage_counts_and_save_one_preserve_against_real_postgres():
    psycopg = pytest.importorskip("psycopg")
    from app.enrichment import store

    store.init_table(DB)
    with psycopg.connect(DB) as c:
        c.execute("DELETE FROM company_enrichment WHERE country='ZX'")
    before = store.coverage(DB)
    store.save_one(DB, ("ZX", "900000001"), GOOD)
    store.save_one(DB, ("ZX", "900000002"), {**WORSE})
    after = store.coverage(DB)
    assert after["enriched"] - before["enriched"] == 2
    assert after["officialWebsites"] - before["officialWebsites"] == 1
    assert after["b2cWebsites"] - before["b2cWebsites"] == 1
    assert after["emails"] - before["emails"] == 1
    store.save_one(DB, ("ZX", "900000001"), WORSE)          # worse re-check must not erase it
    kept = store.load_map(DB)[("ZX", "900000001")]
    with psycopg.connect(DB) as c:
        c.execute("DELETE FROM company_enrichment WHERE country='ZX'")
    assert kept["officialWebsite"] == "https://a.fr" and kept["preservedFromPrevious"] is True
