"""Pipeline tests against a fake web (no network). All companies and sites are fictional."""
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.enrichment import NOT_APPLICABLE, NOT_FOUND, PARTIAL, UNVERIFIED, VERIFIED  # noqa: E402
from app.enrichment.pipeline import FetchedPage, enrich_company  # noqa: E402
from app.enrichment.discovery import guess_domains  # noqa: E402

TODAY = date(2026, 11, 6)


class FakeWeb:
    """Maps URL -> html; records every request so limits can be asserted."""

    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.requests: list[str] = []

    async def get(self, url: str):
        self.requests.append(url)
        for key, html in self.pages.items():
            if url.rstrip("/") == key.rstrip("/"):
                return FetchedPage(url=key, html=html)
        return None


def run(coro):
    return asyncio.run(coro)


COMPANY = {
    "name": "MAISON LILAS",
    "siren": "123456789",
    "siret": "12345678900012",
    "address": "5 place du Marche 69001 LYON",
    "website": "",
}

SHOP_HOME = """<html><head><title>Maison Lilas - Bougies artisanales</title>
<meta name="generator" content="Shopify"><script src="https://cdn.shopify.com/s/t.js"></script></head>
<body><a href="/mentions-legales">Mentions légales</a><a href="/cart">Panier</a>
<button>Ajouter au panier</button><p>Bougie 12,00 € Coffret 29,00 € Savon 6,00 €</p></body></html>"""
LEGAL = "<html><title>Mentions légales</title><body>Maison Lilas SARL, 5 place du Marche, 69001 Lyon. RCS Lyon 123 456 789</body></html>"


def test_verified_site_with_shop_evidence_is_verified_b2c():
    web = FakeWeb({"https://maisonlilas.fr": SHOP_HOME, "https://maisonlilas.fr/mentions-legales": LEGAL})
    r = run(enrich_company(COMPANY, web, today=TODAY))
    assert r["officialWebsite"] == "https://maisonlilas.fr"
    assert r["officialWebsiteStatus"] == VERIFIED
    assert r["officialWebsiteSource"] == "domain_guess"
    assert r["b2cStatus"] == VERIFIED and r["b2cWebsite"] == "https://maisonlilas.fr"
    assert r["b2cSiteType"] == "b2c" and r["b2cConfidence"] == "high"
    assert r["checkedAt"] == "2026-11-06"
    types = {e["type"] for e in r["officialWebsiteEvidence"]}
    assert {"domain_derived_from_name", "registration_number"} <= types
    assert r["b2cEvidence"], "B2C match must carry evidence"


def test_nothing_found_means_not_found_and_no_invented_fields():
    r = run(enrich_company(COMPANY, FakeWeb({}), today=TODAY))
    assert r["officialWebsite"] is None and r["officialWebsiteStatus"] == NOT_FOUND
    assert r["b2cWebsite"] is None and r["b2cStatus"] == NOT_FOUND
    assert "could be verified" in r["b2cExplanation"]
    assert all(c["outcome"] == "unreachable_or_not_permitted" for c in r["candidatesChecked"])


def test_lookalike_domain_with_other_content_is_not_reported():
    web = FakeWeb({"https://maisonlilas.fr": "<html><title>Casino en ligne</title><body>jackpot</body></html>"})
    r = run(enrich_company(COMPANY, web, today=TODAY))
    assert r["officialWebsite"] is None and r["b2cWebsite"] is None
    assert r["officialWebsiteStatus"] == NOT_FOUND


def test_name_only_match_is_kept_as_unverified_candidate_not_as_website():
    html = "<html><title>Maison Lilas</title><body>Bougies, Paris 75001</body></html>"
    r = run(enrich_company(COMPANY, FakeWeb({"https://maisonlilas.fr": html}), today=TODAY))
    assert r["officialWebsite"] is None
    assert r["officialWebsiteStatus"] == UNVERIFIED
    assert r["officialWebsiteCandidate"] == "https://maisonlilas.fr"
    assert r["b2cWebsite"] is None


def test_b2b_only_verified_site_is_not_applicable():
    home = """<html><head><title>Maison Lilas Pro</title></head><body>
    <a href="/mentions-legales">Mentions légales</a>
    <h1>Solutions pour les entreprises</h1><a href="/demo">Demander une démo</a><p>Plateforme B2B</p></body></html>"""
    web = FakeWeb({"https://maisonlilas.fr": home, "https://maisonlilas.fr/mentions-legales": LEGAL})
    r = run(enrich_company(COMPANY, web, today=TODAY))
    assert r["officialWebsiteStatus"] == VERIFIED
    assert r["b2cStatus"] == NOT_APPLICABLE and r["b2cWebsite"] is None
    assert r["b2cExplanation"]


def test_brochure_site_is_not_assumed_b2c():
    home = '<html><head><title>Maison Lilas</title></head><body><a href="/mentions-legales">Mentions légales</a>Notre histoire</body></html>'
    web = FakeWeb({"https://maisonlilas.fr": home, "https://maisonlilas.fr/mentions-legales": LEGAL})
    r = run(enrich_company(COMPANY, web, today=TODAY))
    assert r["officialWebsiteStatus"] == VERIFIED
    assert r["b2cStatus"] == NOT_FOUND and r["b2cWebsite"] is None


def test_separate_shop_domain_gets_reduced_trust():
    home = """<html><head><title>Maison Lilas</title></head><body>
    <a href="/mentions-legales">Mentions légales</a>
    <a href="https://maisonlilas.myshopify.com/">Boutique en ligne</a></body></html>"""
    shop = SHOP_HOME.replace('<a href="/mentions-legales">Mentions légales</a>', "")
    web = FakeWeb({
        "https://maisonlilas.fr": home,
        "https://maisonlilas.fr/mentions-legales": LEGAL,
        "https://maisonlilas.myshopify.com": shop,
    })
    r = run(enrich_company(COMPANY, web, today=TODAY))
    assert r["officialWebsiteStatus"] == VERIFIED
    assert r["b2cWebsite"] == "https://maisonlilas.myshopify.com/" or r["b2cWebsite"] == "https://maisonlilas.myshopify.com"
    assert r["b2cStatus"] == PARTIAL, "other-domain shop must not be 'Verified'"
    assert r["b2cEvidence"][0]["type"] == "linked_from_official_website"


def test_registry_website_is_used_first_and_marked_registry_sourced():
    company = {**COMPANY, "website": "https://www.lilas-officiel.fr"}
    web = FakeWeb({"https://www.lilas-officiel.fr": SHOP_HOME})
    r = run(enrich_company(company, web, today=TODAY))
    assert r["officialWebsite"] == "https://www.lilas-officiel.fr"
    assert r["officialWebsiteSource"] == "registry"
    assert r["officialWebsiteEvidence"][0]["type"] == "registry_published"
    assert web.requests[0].startswith("https://www.lilas-officiel.fr")


def test_wikidata_candidate_is_tried_and_failures_are_swallowed():
    async def good(siren):
        assert siren == "123456789"
        return ["https://lilas-groupe.com"]

    async def broken(siren):
        raise RuntimeError("endpoint down")

    web = FakeWeb({"https://lilas-groupe.com": SHOP_HOME, "https://lilas-groupe.com/mentions-legales": LEGAL})
    r = run(enrich_company(COMPANY, web, wikidata=good, today=TODAY))
    assert r["officialWebsiteSource"] == "wikidata" and r["officialWebsiteStatus"] == VERIFIED
    r2 = run(enrich_company(COMPANY, FakeWeb({}), wikidata=broken, today=TODAY))
    assert r2["officialWebsiteStatus"] == NOT_FOUND


def test_request_budget_per_company_is_bounded():
    web = FakeWeb({})
    run(enrich_company({**COMPANY, "name": "UN DEUX TROIS QUATRE CINQ SIX SEPT HUIT NEUF"}, web, today=TODAY))
    assert len(web.requests) <= 6, web.requests


def test_company_without_registration_number_cannot_reach_verified():
    company = {"name": "MAISON LILAS", "siren": "", "siret": "", "address": "5 place du Marche 69001 LYON"}
    web = FakeWeb({"https://maisonlilas.fr": SHOP_HOME, "https://maisonlilas.fr/mentions-legales": LEGAL})
    r = run(enrich_company(company, web, today=TODAY))
    assert r["officialWebsiteStatus"] != VERIFIED
    assert r["b2cStatus"] != VERIFIED



def test_country_specific_domain_candidates_prioritise_local_tld():
    belgium = guess_domains("MAISON LILAS", country="Belgium")
    luxembourg = guess_domains("MAISON LILAS", country="Luxembourg")
    france = guess_domains("MAISON LILAS", country="France")
    assert belgium and all(".be" in url or ".com" in url or ".eu" in url for url in belgium)
    assert belgium[0].endswith(".be")
    assert luxembourg[0].endswith(".lu")
    assert france[0].endswith(".fr")
    assert "https://maisonlilas.be" in belgium
    assert "https://maisonlilas.lu" in luxembourg
