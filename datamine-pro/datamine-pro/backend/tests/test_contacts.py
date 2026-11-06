"""Public contact extraction and overlay (fictional companies, no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.enrichment import PARTIAL, VERIFIED  # noqa: E402
from app.enrichment.contacts import find_contacts  # noqa: E402
from app.enrichment.merge import overlay_enrichment  # noqa: E402
from app.enrichment.pagefacts import parse_html  # noqa: E402


def page(html, url="https://maisonlilas.fr/"):
    return parse_html(html, url)


def test_mailto_and_tel_are_read_with_their_source_page():
    p = page('<a href="mailto:Contact@MaisonLilas.fr?subject=hi">Mail</a><a href="tel:+33 4 78 00 00 00">Tel</a>')
    c = find_contacts([p])
    assert c["contactEmail"] == "contact@maisonlilas.fr" and c["contactEmailSource"] == "https://maisonlilas.fr/"
    assert c["contactPhone"] == "+33478000000" and c["contactPhoneSource"] == "https://maisonlilas.fr/"


def test_same_domain_email_preferred_and_placeholders_ignored():
    p = page('<p>Support: help@partner.com, email@example.com, nom@domain.com</p><a href="mailto:shop@maisonlilas.fr">x</a>'
             '<p>logo@2x.png</p>')
    assert find_contacts([p])["contactEmail"] == "shop@maisonlilas.fr"


def test_email_in_legal_notice_text_is_accepted_but_nothing_is_invented():
    legal = page("<p>Mentions légales. Écrire à legal@maisonlilas.fr</p>", "https://maisonlilas.fr/mentions-legales")
    assert find_contacts([page("<p>Bienvenue</p>"), legal])["contactEmail"] == "legal@maisonlilas.fr"
    empty = find_contacts([page("<p>Bienvenue</p>")])
    assert empty == {"contactEmail": None, "contactEmailSource": None, "contactPhone": None, "contactPhoneSource": None}


def test_short_or_invalid_phone_rejected():
    assert find_contacts([page('<a href="tel:123">x</a>')])["contactPhone"] is None


def test_overlay_fills_contacts_only_for_accepted_sites_and_keeps_existing():
    data = {"officialWebsite": "https://maisonlilas.fr", "officialWebsiteStatus": VERIFIED, "checkedAt": "2026-11-06",
            "officialWebsiteEvidence": [{"type": "registration_number", "url": "https://maisonlilas.fr/mentions"}],
            "contactEmail": "a@maisonlilas.fr", "contactEmailSource": "https://maisonlilas.fr/",
            "contactPhone": "+33478000000", "contactPhoneSource": "https://maisonlilas.fr/",
            "b2cWebsite": "https://maisonlilas.fr/boutique", "b2cStatus": PARTIAL}
    out = overlay_enrichment({"email": "", "phone": "0600000000", "website": ""}, data)
    assert out["email"] == "a@maisonlilas.fr" and out["emailSource"] == "https://maisonlilas.fr/"
    assert out["phone"] == "0600000000"  # existing value never overwritten
    assert out["websiteStatus"] == "verified" and out["websiteSourceUrl"] == "https://maisonlilas.fr/mentions"
    assert out["b2cSourceUrl"] == "https://maisonlilas.fr/boutique" and out["checkedAt"] == "2026-11-06"
    weak = overlay_enrichment({"email": "", "website": ""}, {**data, "officialWebsiteStatus": "Unverified"})
    assert weak["email"] == "" and weak["website"] == ""  # unverified site never contributes contacts
