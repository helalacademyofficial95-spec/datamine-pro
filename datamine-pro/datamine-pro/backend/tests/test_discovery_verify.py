"""Stage 1 tests: candidate discovery and ownership verification (offline, fictional data)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.enrichment import NOT_FOUND, PARTIAL, UNVERIFIED, VERIFIED  # noqa: E402
from app.enrichment.discovery import (  # noqa: E402
    guess_domains, normalize_website, parse_wikidata_response, parse_wikidata_text, site_kind,
    wikidata_query,
)
from app.enrichment.pagefacts import parse_html  # noqa: E402
from app.enrichment.text import core_tokens, normalize, same_site  # noqa: E402
from app.enrichment.verify import (  # noqa: E402
    find_registration_number, registry_published, verify_candidate,
)

COMPANY = {
    "name": "BOULANGERIE DUPONT",
    "siren": "123456789",
    "siret": "12345678900012",
    "address": "12 rue des Lilas 69003 LYON",
}


def page(html: str, url: str = "https://boulangerie-dupont.fr/"):
    return parse_html(html, url)


# ---------- text helpers ----------

def test_normalize_strips_accents_and_punctuation():
    assert normalize("Café  de l'Étoile & Fils!") == "cafe de l etoile fils"


def test_core_tokens_drop_legal_forms_and_articles():
    assert core_tokens("SARL LE PETIT BISTROT") == ["petit", "bistrot"]


def test_same_site_handles_subdomains_and_www():
    assert same_site("https://www.dupont.fr/", "https://boutique.dupont.fr/panier")
    assert not same_site("https://dupont.fr", "https://dupont.com")


# ---------- discovery ----------

def test_guess_domains_from_name():
    guesses = guess_domains("DUPONT BOULANGERIE SARL")
    assert "https://dupontboulangerie.fr" in guesses
    assert "https://dupont-boulangerie.fr" in guesses
    assert all(g.startswith("https://") for g in guesses)


def test_guess_domains_uses_trade_name_in_parentheses():
    guesses = guess_domains("SOCIETE ANONYME XYZ (LE FOURNIL DORE)")
    assert "https://fournildore.fr" in guesses or "https://fournil-dore.fr" in guesses


def test_guess_domains_bounded_and_skips_empty_or_tiny():
    assert guess_domains("SARL") == []
    assert guess_domains("AB") == []
    assert len(guess_domains("UN DEUX TROIS QUATRE CINQ SIX SEPT HUIT")) <= 10


def test_social_marketplace_directory_are_never_company_sites():
    assert site_kind("https://www.facebook.com/dupont") == "social"
    assert site_kind("https://www.amazon.fr/stores/x") == "marketplace"
    assert site_kind("https://www.societe.com/societe/x-123.html") == "directory"
    assert normalize_website("https://instagram.com/dupont") == ""
    assert normalize_website("not a url") == ""
    assert normalize_website("Boulangerie-Dupont.FR/accueil") == "https://boulangerie-dupont.fr"


def test_wikidata_query_requires_valid_siren():
    assert "123456789" in wikidata_query("123456789")
    for bad in ("", "12345", "12345678a", "123456789 OR 1=1"):
        try:
            wikidata_query(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted bad siren {bad!r}")


def test_parse_wikidata_response_filters_junk():
    payload = {"results": {"bindings": [
        {"site": {"value": "https://www.exemple-entreprise.fr/"}},
        {"site": {"value": "https://www.facebook.com/exemple"}},
        {"other": {"value": "x"}},
    ]}}
    assert parse_wikidata_response(payload) == ["https://www.exemple-entreprise.fr"]
    assert parse_wikidata_response({}) == []
    assert parse_wikidata_text("not json") == []
    assert parse_wikidata_text(json.dumps(payload)) == ["https://www.exemple-entreprise.fr"]


# ---------- registration number matching ----------

def test_registration_number_formats_and_boundaries():
    assert find_registration_number(COMPANY, "RCS Lyon 123 456 789") == "siren"
    assert find_registration_number(COMPANY, "SIREN : 123.456.789") == "siren"
    assert find_registration_number(COMPANY, "SIRET 123 456 789 00012") == "siret"
    assert find_registration_number(COMPANY, "SIRET 12345678900012") == "siret"
    # A different, longer number that merely contains ours must not match.
    assert find_registration_number(COMPANY, "Ref 1234567890") is None
    assert find_registration_number(COMPANY, "Ref 9123456789") is None
    # Another establishment of the same company (same SIREN, other SIRET) still proves the company.
    assert find_registration_number(COMPANY, "SIRET 123 456 789 00099") == "siren"
    assert find_registration_number({"name": "X"}, "123456789") is None


# ---------- verification statuses ----------

LEGAL = """<html><head><title>Mentions légales - Boulangerie Dupont</title></head>
<body><p>Boulangerie Dupont SARL, 12 rue des Lilas, 69003 Lyon. RCS Lyon 123 456 789.</p></body></html>"""
HOME = "<html><head><title>Boulangerie Dupont - Pain et pâtisseries</title></head><body>Bienvenue</body></html>"


def test_verified_needs_number_plus_name_or_postal():
    v = verify_candidate(COMPANY, [page(HOME), page(LEGAL, "https://boulangerie-dupont.fr/mentions-legales")])
    assert v.status == VERIFIED
    types = {e["type"] for e in v.evidence}
    assert {"registration_number", "name_match", "postal_code_match"} <= types
    assert all(e["url"].startswith("https://boulangerie-dupont.fr") for e in v.evidence)


def test_name_and_postal_without_number_is_only_partial():
    html = "<html><title>Boulangerie Dupont</title><body>12 rue des Lilas 69003 Lyon</body></html>"
    v = verify_candidate(COMPANY, [page(html)])
    assert v.status == PARTIAL
    assert "registration_number" not in {e["type"] for e in v.evidence}


def test_number_alone_is_partial():
    html = "<html><title>Autre enseigne</title><body>RCS 123 456 789</body></html>"
    assert verify_candidate(COMPANY, [page(html)]).status == PARTIAL


def test_name_only_is_unverified():
    html = "<html><title>Boulangerie Dupont</title><body>Pain frais, Paris 75001</body></html>"
    v = verify_candidate(COMPANY, [page(html)])
    assert v.status == UNVERIFIED
    assert not v.accepted


def test_unrelated_site_is_unverified_and_empty_pages_too():
    assert verify_candidate(COMPANY, [page("<html><title>Casino en ligne</title><body>jackpot</body></html>")]).status == UNVERIFIED
    assert verify_candidate(COMPANY, []).status == UNVERIFIED


def test_digits_in_longer_number_do_not_verify():
    html = "<html><title>Boulangerie Dupont</title><body>Tel 1234567890 69003 Lyon</body></html>"
    v = verify_candidate(COMPANY, [page(html)])
    assert "registration_number" not in {e["type"] for e in v.evidence}


def test_postal_code_must_stand_alone():
    html = "<html><body>commande 1690031 Lyon Boulangerie Dupont</body></html>"
    v = verify_candidate({**COMPANY, "siren": "", "siret": ""}, [page(html)])
    assert "postal_code_match" not in {e["type"] for e in v.evidence}


def test_registry_published_website_is_verified_with_evidence():
    v = registry_published("https://exemple.fr")
    assert v.status == VERIFIED and v.evidence[0]["type"] == "registry_published"


def test_not_found_constant_is_exported():
    assert NOT_FOUND == "Not Found"
