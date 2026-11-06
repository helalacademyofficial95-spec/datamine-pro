"""Stage 2 tests: B2C classification and status mapping (offline, fictional sites)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.enrichment import NOT_APPLICABLE, NOT_FOUND, PARTIAL, UNVERIFIED, VERIFIED  # noqa: E402
from app.enrichment.classify import assess_site, b2c_status, find_shop_links  # noqa: E402
from app.enrichment.pagefacts import parse_html  # noqa: E402

SHOPIFY_SHOP = """<html><head><title>Maison Lilas - Bougies</title>
<meta name="generator" content="Shopify">
<script src="https://cdn.shopify.com/s/files/theme.js"></script>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Bougie","offers":{"@type":"Offer","price":"12.00","priceCurrency":"EUR"}}</script>
</head><body>
<a href="/cart">Panier</a><a href="/collections/bougies">Bougies</a>
<button>Ajouter au panier</button><p>Bougie lavande 12,00 € - Bougie rose 14,00 € - Coffret 29,00 €</p>
</body></html>"""

RESTAURANT = """<html><head><title>Le Petit Bistrot</title>
<script type="application/ld+json">{"@type":"Restaurant","name":"Le Petit Bistrot"}</script></head>
<body><h1>Le Petit Bistrot</h1><a href="/reservation">Réserver une table</a>
<p>Menu du jour 18 € - Formule 24 €</p></body></html>"""

B2B_SAAS = """<html><head><title>Acme Logiciels</title></head>
<body><h1>Solutions pour les entreprises</h1><a href="/demo">Demander une démo</a>
<p>Plateforme B2B pour vos équipes. Espace pro réservé aux professionnels.</p></body></html>"""

BROCHURE = "<html><head><title>Dupont Conseil</title></head><body><h1>Notre cabinet</h1><p>Contactez-nous.</p></body></html>"


def facts(html, url="https://exemple.fr/"):
    return parse_html(html, url)


# ---------- assessment ----------

def test_shopify_shop_is_strong_b2c_with_evidence():
    a = assess_site(facts(SHOPIFY_SHOP))
    assert a.site_type == "b2c" and a.score >= 5
    kinds = {e["type"] for e in a.evidence}
    assert {"structured_product_data", "cart_or_checkout_link", "shop_platform", "purchase_wording"} <= kinds


def test_restaurant_booking_is_consumer_facing():
    a = assess_site(facts(RESTAURANT))
    assert a.site_type == "b2c" and a.score >= 3
    assert "booking_wording" in {e["type"] for e in a.evidence}


def test_b2b_software_is_not_b2c():
    a = assess_site(facts(B2B_SAAS))
    assert a.site_type == "b2b" and a.score < 3 and a.b2b_score >= 2


def test_plain_brochure_site_is_not_assumed_b2c():
    a = assess_site(facts(BROCHURE))
    assert a.site_type == "unknown" and a.score == 0


def test_social_and_marketplace_pages_are_never_b2c():
    assert assess_site(facts(SHOPIFY_SHOP, "https://www.facebook.com/maisonlilas")).site_type == "social"
    assert assess_site(facts(SHOPIFY_SHOP, "https://www.amazon.fr/stores/maison")).site_type == "marketplace"
    assert assess_site(facts(RESTAURANT, "https://www.pagesjaunes.fr/pros/123")).site_type == "directory"


def test_copyright_wording_does_not_count_as_booking():
    a = assess_site(facts("<html><body>© 2024 Tous droits réservés</body></html>"))
    assert "booking_wording" not in {e["type"] for e in a.evidence}


# ---------- status mapping ----------

def test_status_matrix_never_exceeds_weaker_evidence():
    strong = assess_site(facts(SHOPIFY_SHOP))
    moderate = assess_site(facts(RESTAURANT))
    b2b = assess_site(facts(B2B_SAAS))
    none = assess_site(facts(BROCHURE))

    assert b2c_status(VERIFIED, strong)[0] == VERIFIED
    assert b2c_status(VERIFIED, moderate)[0] == PARTIAL
    assert b2c_status(VERIFIED, b2b)[0] == NOT_APPLICABLE
    assert b2c_status(VERIFIED, none)[0] == NOT_FOUND

    assert b2c_status(PARTIAL, strong)[0] == PARTIAL
    assert b2c_status(PARTIAL, moderate)[0] == UNVERIFIED
    assert b2c_status(PARTIAL, none)[0] == NOT_FOUND

    # Unverified ownership can never produce Verified or Partially Verified
    for assessment in (strong, moderate, b2b, none):
        assert b2c_status(UNVERIFIED, assessment)[0] in (UNVERIFIED, NOT_FOUND)


def test_marketplace_result_is_not_found_with_explanation():
    status, confidence, why = b2c_status(VERIFIED, assess_site(facts(SHOPIFY_SHOP, "https://www.etsy.com/shop/x")))
    assert status == NOT_FOUND and "marketplace" in why and confidence == "low"


def test_explanations_present_for_every_outcome():
    for ownership in (VERIFIED, PARTIAL, UNVERIFIED):
        for html in (SHOPIFY_SHOP, RESTAURANT, B2B_SAAS, BROCHURE):
            status, confidence, why = b2c_status(ownership, assess_site(facts(html)))
            assert status and confidence in ("high", "medium", "low") and len(why) > 20


# ---------- shop links ----------

HOME_WITH_LINKS = """<html><body>
<a href="https://boutique.exemple.fr/">Boutique en ligne</a>
<a href="https://www.facebook.com/exemple">Facebook</a>
<a href="https://www.amazon.fr/stores/exemple">Amazon</a>
<a href="https://partenaire-externe.com/">Notre partenaire</a>
<a href="https://exemple.myshopify.com/">Shop</a>
<a href="/contact">Contact</a>
<a href="mailto:a@b.fr">Mail</a>
</body></html>"""


def test_find_shop_links_prefers_own_shop_and_skips_social_marketplace_partners():
    links = find_shop_links(facts(HOME_WITH_LINKS))
    assert "https://boutique.exemple.fr/" in links
    assert not any("facebook" in l or "amazon" in l or "partenaire-externe" in l for l in links)
    assert len(links) <= 2


def test_external_site_needs_label_and_path_not_just_a_label():
    html = '<html><body><a href="https://autre-site.com/accueil">Boutique</a></body></html>'
    assert find_shop_links(facts(html)) == []
    html = '<html><body><a href="https://autre-site.com/boutique/">Boutique</a></body></html>'
    assert find_shop_links(facts(html)) == ["https://autre-site.com/boutique/"]
