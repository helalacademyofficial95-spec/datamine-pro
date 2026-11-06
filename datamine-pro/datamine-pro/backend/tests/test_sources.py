"""What a submitted URL is: listing, single company, or unsupported (fictional fixtures only)."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("bs4")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.enrichment.merge import record_key  # noqa: E402
from app.sources import classify_page, is_unsupported_registry  # noqa: E402

LISTING = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"Bakery","name":"Boulangerie Alpha","telephone":"+32 2 000 00 01","url":"https://annuaire.test/alpha",
  "address":{"@type":"PostalAddress","streetAddress":"1 rue A","postalCode":"1000","addressLocality":"Bruxelles"}},
 {"@type":"Florist","name":"Fleurs Beta","email":"mailto:beta@beta.test","url":"https://annuaire.test/beta"},
 {"@type":["LocalBusiness"],"name":"Garage Gamma"},
 {"@type":"Bakery","name":"boulangerie alpha"}]}
</script></head><body>Annuaire</body></html>"""
SINGLE_MARKUP = '<script type="application/ld+json">{"@type":"Organization","name":"Maison Lilas"}</script>'
SINGLE_CONTACT = '<html><body><h1>Maison Lilas</h1><a href="tel:+33478000000">Appeler</a></body></html>'
DIRECTORY_NO_DATA = "<html><body>" + "".join(f'<a href="/c/{i}">Company {i}</a>' for i in range(60)) + "</body></html>"


def test_listing_is_split_into_deduplicated_records_with_source_urls():
    kind, recs = classify_page(LISTING, "https://annuaire.test/liste", "Belgium")
    assert kind == "listing" and [r["name"] for r in recs] == ["Boulangerie Alpha", "Fleurs Beta", "Garage Gamma"]
    alpha, beta, _ = recs
    assert alpha["phone"] == "+32 2 000 00 01" and alpha["address"] == "1 rue A 1000 Bruxelles"
    assert beta["email"] == "beta@beta.test" and beta["sourceUrl"] == "https://annuaire.test/beta"
    assert alpha["website"] == "" and alpha["b2cWebsite"] is None  # directory page is never the company's website
    assert alpha["origin"] == "extracted" and alpha["country"] == "Belgium" and alpha["id"].startswith("gen-")


def test_single_company_pages_are_recognised():
    assert classify_page(f"<html>{SINGLE_MARKUP}</html>", "https://x.test", "France")[0] == "single"
    assert classify_page(SINGLE_CONTACT, "https://x.test", "France")[0] == "single"


def test_directory_without_structured_data_is_unsupported_not_one_company():
    assert classify_page(DIRECTORY_NO_DATA, "https://dir.test", "France") == ("unsupported", [])


def test_be_lu_registries_are_reported_unsupported():
    assert is_unsupported_registry("https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html")
    assert is_unsupported_registry("https://www.lbr.lu/mjrcs/jsp/DisplayConsultDetailAction.action")
    assert not is_unsupported_registry("https://annuaire-entreprises.data.gouv.fr/rechercher")


def test_listing_records_get_a_stable_enrichment_key_but_other_ids_do_not():
    _, recs = classify_page(LISTING, "https://annuaire.test/liste", "Belgium")
    assert record_key(recs[0]) == ("Belgium", recs[0]["id"])
    assert record_key({"id": "x-1", "country": "Belgium"}) is None
