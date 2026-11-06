"""B2C classification: does this site sell products or services directly to consumers?

A homepage is NOT assumed to be B2C. We only report consumer-facing evidence we actually
observed on the page. Ownership (does the site belong to the company?) is judged separately
by verify.py; b2c_status() combines both and never claims more than the weaker of the two.

Scoring (consumer evidence): >=5 strong, 3-4 moderate, <3 insufficient.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urlparse

from . import NOT_APPLICABLE, NOT_FOUND, PARTIAL, UNVERIFIED, VERIFIED
from .discovery import site_kind
from .pagefacts import PageFacts
from .text import host_of, same_site

CART_PATH = re.compile(r"/(panier|cart|basket|checkout|caisse|commande)(/|$|\?|-)", re.I)
CATALOG_PATH = re.compile(r"/(boutique|shop|store|e-shop|eshop|webshop|produits?|products?|collections?)(/|$|\?|-)", re.I)
ADD_TO_CART = re.compile(
    r"ajouter au panier|add to (cart|basket)|acheter maintenant|buy now|commander en ligne|achat en ligne|"
    r"livraison (offerte|gratuite)|frais de livraison|click ?(&|and|et) ?collect|retrait en magasin|paiement s[eé]curis[eé]",
    re.I,
)
BOOKING = re.compile(
    r"r[eé]server|r[eé]servation|prendre (un )?rendez-vous|book (a |your )?(table|now|online|appointment)|booking",
    re.I,
)
PRICE = re.compile(r"\d[\d\s.,]{0,8}\s?(€|eur\b|euros?\b)", re.I)
CONSUMER_WORDS = re.compile(r"\b(particuliers?|consommateurs?|nos clients|pour vous|cadeaux?)\b", re.I)
B2B_SIGNALS = [
    ("professionals_only", re.compile(r"r[eé]serv[eé] aux professionnels|professionnels uniquement|pour les professionnels|espace pro(fessionnel)?s?\b", re.I)),
    ("demo_request", re.compile(r"demander (une )?d[eé]mo|request a demo|book a demo|planifier une d[eé]mo", re.I)),
    ("business_solutions", re.compile(r"solutions? (pour|aux) (les )?(entreprises|professionnels)|\bb2b\b", re.I)),
    ("wholesale", re.compile(r"\bgrossiste\b|vente en gros|\bwholesale\b", re.I)),
]
PLATFORM_MARKERS = {
    "shopify": ("cdn.shopify.com", "myshopify.com"),
    "woocommerce": ("woocommerce", "wc-ajax"),
    "prestashop": ("prestashop",),
    "magento": ("magento", "mage/"),
    "shopware": ("shopware",),
    "bigcommerce": ("bigcommerce",),
    "wix_stores": ("wixstores", "wix-ecommerce"),
}
PRODUCT_TYPES = {"Product", "Offer", "AggregateOffer", "ProductGroup", "ProductModel"}
CONSUMER_VENUE_TYPES = {
    "Store", "Restaurant", "Hotel", "Bakery", "CafeOrCoffeeShop", "BarOrPub", "FoodEstablishment",
    "HairSalon", "BeautySalon", "HealthAndBeautyBusiness", "ClothingStore", "FurnitureStore",
    "Florist", "BookStore", "ShoeStore", "JewelryStore", "Optician", "AutoDealer", "LodgingBusiness",
}
SHOP_LABEL = re.compile(
    r"\b(shop|store|boutique|webshop|e-shop|eshop|boutique en ligne|commander|acheter|achat en ligne|"
    r"online shop|buy online|shop online)\b",
    re.I,
)
SHOP_HOST_PREFIX = re.compile(r"^(shop|boutique|store|eshop|e-shop|webshop|commande|order)\.", re.I)
SHOP_PLATFORM_HOSTS = ("myshopify.com",)


@dataclass
class SiteAssessment:
    site_type: str = "unknown"  # b2c | b2b | marketplace | social | directory | unknown
    score: int = 0
    b2b_score: int = 0
    evidence: list[dict[str, str]] = field(default_factory=list)


def assess_site(facts: PageFacts) -> SiteAssessment:
    kind = site_kind(facts.url)
    if kind:
        return SiteAssessment(site_type=kind, evidence=[{"type": kind, "detail": f"URL is a {kind} page, not the company's own site"}])

    out = SiteAssessment()

    def add(points: int, kind_: str, detail: str) -> None:
        out.score += points
        out.evidence.append({"type": kind_, "detail": detail})

    text = f"{facts.title} {facts.text}"
    urls = [u for u, _ in facts.links]

    product_types = facts.jsonld_types & PRODUCT_TYPES
    if product_types:
        add(3, "structured_product_data", f"Product/offer markup present ({', '.join(sorted(product_types))})")
    venue_types = facts.jsonld_types & CONSUMER_VENUE_TYPES
    if venue_types:
        add(1, "consumer_venue_markup", f"Consumer business markup ({', '.join(sorted(venue_types))})")

    if any(CART_PATH.search(urlparse(u).path or "") for u in urls) or CART_PATH.search(urlparse(facts.url).path or ""):
        add(3, "cart_or_checkout_link", "Link to a cart / checkout page")
    if any(CATALOG_PATH.search(urlparse(u).path or "") for u in urls):
        add(1, "catalog_link", "Link to a shop / product catalogue section")
    if ADD_TO_CART.search(text):
        add(2, "purchase_wording", "Purchase wording (add to cart, delivery, secure payment…)")
    if BOOKING.search(text):
        add(2, "booking_wording", "Online booking / reservation wording")

    prices = len(PRICE.findall(text))
    if prices >= 3:
        add(2, "prices_shown", f"{prices} euro prices displayed")
    elif prices >= 1:
        add(1, "prices_shown", f"{prices} euro price displayed")

    generator = facts.meta.get("generator", "").lower()
    resources = " ".join(facts.resources).lower() + " " + generator
    for platform, markers in PLATFORM_MARKERS.items():
        if any(m in resources for m in markers):
            add(3, "shop_platform", f"E-commerce platform detected ({platform})")
            break

    if CONSUMER_WORDS.search(text):
        add(1, "consumer_wording", "Addresses consumers / private customers")

    for name, pattern in B2B_SIGNALS:
        if pattern.search(text):
            out.b2b_score += 1
            out.evidence.append({"type": f"b2b_{name}", "detail": "B2B signal: " + name.replace("_", " ")})

    if out.score >= 3:
        out.site_type = "b2c"
    elif out.b2b_score >= 2:
        out.site_type = "b2b"
    return out


def b2c_status(ownership: str, assessment: SiteAssessment) -> tuple[str, str, str]:
    """(status, confidence, explanation). Never stronger than the weaker of ownership and commerce evidence."""
    if assessment.site_type in ("marketplace", "social", "directory"):
        return NOT_FOUND, "low", f"Only a {assessment.site_type} page was found; that is not the company's own consumer website."
    consumer = assessment.score >= 3
    strong = assessment.score >= 5

    if ownership == VERIFIED:
        if strong:
            return VERIFIED, "high", "Ownership verified on the site's legal notice and strong consumer-sales evidence found."
        if consumer:
            return PARTIAL, "medium", "Ownership verified; consumer-sales evidence is moderate."
        if assessment.site_type == "b2b":
            return NOT_APPLICABLE, "medium", "Verified company website shows business-to-business signals and no consumer sales evidence."
        return NOT_FOUND, "low", "Verified company website shows no evidence of selling to consumers."
    if ownership == PARTIAL:
        if strong:
            return PARTIAL, "medium", "Ownership only partly verified; strong consumer-sales evidence found."
        if consumer:
            return UNVERIFIED, "low", "Ownership only partly verified and consumer-sales evidence is moderate."
        if assessment.site_type == "b2b":
            return NOT_APPLICABLE, "low", "Partly verified website shows business-to-business signals."
        return NOT_FOUND, "low", "Partly verified website shows no evidence of selling to consumers."
    if consumer:
        return UNVERIFIED, "low", "Website shows consumer-sales evidence but its ownership could not be verified."
    return NOT_FOUND, "low", "No website for this company could be verified."


def find_shop_links(facts: PageFacts, limit: int = 2) -> list[str]:
    """Links from a (verified) company site to its online shop / booking pages.

    Accepts same-site links, shop-platform hosts, or external links with both a shop label and a
    shop-like path. Social networks, marketplaces and directories are never returned.
    """
    here = urldefrag(facts.url)[0].rstrip("/")
    scored: dict[str, int] = {}
    for url, label in facts.links:
        url = urldefrag(url)[0]
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or site_kind(url):
            continue
        if url.rstrip("/") == here:
            continue
        host = host_of(url)
        score = 0
        if SHOP_LABEL.search(label):
            score += 3
        if CATALOG_PATH.search(parsed.path or ""):
            score += 2
        if SHOP_HOST_PREFIX.match(host) or any(host.endswith(h) for h in SHOP_PLATFORM_HOSTS):
            score += 3
        trusted_host = same_site(facts.url, url) or any(host.endswith(h) for h in SHOP_PLATFORM_HOSTS)
        needed = 3 if trusted_host else 5
        if score >= needed:
            scored[url] = max(score, scored.get(url, 0))
    return [u for u, _ in sorted(scored.items(), key=lambda item: -item[1])][:limit]
