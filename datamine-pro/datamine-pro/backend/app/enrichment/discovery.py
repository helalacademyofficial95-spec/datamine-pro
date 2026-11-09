"""Candidate website discovery from legitimate, free, automation-friendly sources.

Sources, in order of trust:
1. registry   - a website published by the official registry (the French API publishes none today).
2. wikidata   - 'official website' (P856) of the item carrying this SIREN (P1616). CC0 data,
                public SPARQL endpoint; coverage is small (mostly larger companies).
3. osm       - 'website' tag of a matching OpenStreetMap place (name + postcode), via Nominatim.
                ODbL data; mostly shops, restaurants and services, i.e. consumer-facing businesses.
4. domain_guess - domains derived from the legal/trade name (e.g. petitbistrot.fr). These are only
                  CANDIDATES: they are fetched and must pass verification before being reported.

We deliberately do not scrape search-engine result pages or commercial company directories.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote, urlparse

from .text import core_tokens, host_matches, name_variants

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
DEFAULT_TLDS = ("fr", "com")
COUNTRY_TLDS = {
    "france": ("fr", "com", "eu"),
    "belgium": ("be", "com", "eu"),
    "belgique": ("be", "com", "eu"),
    "belgië": ("be", "com", "eu"),
    "luxembourg": ("lu", "com", "eu"),
}
MAX_GUESSES = 6

# Hosts that are never a company's own website.
SOCIAL_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "pinterest.com", "youtube.com", "youtu.be",
    "tiktok.com", "x.com", "twitter.com", "snapchat.com", "whatsapp.com", "wa.me", "t.me",
}
MARKETPLACE_DOMAINS = {
    "amazon.fr", "amazon.com", "amazon.de", "ebay.fr", "ebay.com", "etsy.com", "cdiscount.com",
    "leboncoin.fr", "vinted.fr", "rakuten.com", "fr.shopping.rakuten.com", "aliexpress.com",
    "fnac.com", "darty.com", "booking.com", "airbnb.fr", "airbnb.com", "tripadvisor.fr",
    "tripadvisor.com", "thefork.fr", "ubereats.com", "deliveroo.fr", "doctolib.fr",
    "planity.com", "treatwell.fr", "tooltyp.com",
}
DIRECTORY_DOMAINS = {
    "pagesjaunes.fr", "societe.com", "pappers.fr", "infogreffe.fr", "verif.com", "manageo.fr",
    "kompass.com", "europages.fr", "europages.com", "annuaire-entreprises.data.gouv.fr",
    "data.gouv.fr", "entreprises.lefigaro.fr", "bfmtv.com", "yelp.fr", "yelp.com",
    "trustpilot.com", "google.com", "g.page", "goo.gl", "maps.app.goo.gl", "wikipedia.org",
    "opencorporates.com", "bodacc.fr", "ellisphere.fr", "score3.fr", "lagazettefrance.fr",
    "mappy.com", "foursquare.com", "cylex.fr", "hotfrog.fr", "kbo-bce.be", "lbr.lu",
}
EXCLUDED_DOMAINS = SOCIAL_DOMAINS | MARKETPLACE_DOMAINS | DIRECTORY_DOMAINS


def site_kind(url: str) -> str | None:
    """'social' | 'marketplace' | 'directory' when the URL is such a page, else None."""
    host = (urlparse(url).hostname or "").lower()
    if host_matches(host, SOCIAL_DOMAINS):
        return "social"
    if host_matches(host, MARKETPLACE_DOMAINS):
        return "marketplace"
    if host_matches(host, DIRECTORY_DOMAINS):
        return "directory"
    return None


def normalize_website(raw: str) -> str:
    """Return a clean https URL root for a website string, or '' if it is not a usable site."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not host or "." not in host or not re.match(r"^[a-z0-9.-]+$", host):
        return ""
    if site_kind(raw):
        return ""
    return f"{parsed.scheme.lower()}://{host}"


def guess_domains(
    raw_name: str,
    tlds: tuple[str, ...] | None = None,
    limit: int = MAX_GUESSES,
    country: str | None = None,
) -> list[str]:
    """Candidate domains from a registry name, preferring the company country TLD.

    These are untrusted candidates only; the enrichment pipeline fetches and verifies each site
    before reporting it. An explicit ``tlds`` argument preserves the original override behavior.
    """
    if tlds is None:
        tlds = COUNTRY_TLDS.get((country or "").strip().lower(), DEFAULT_TLDS)
    slugs: list[str] = []

    def add(slug: str) -> None:
        slug = slug.strip("-")
        if 4 <= len(slug) <= 40 and re.match(r"^[a-z0-9-]+$", slug) and slug not in slugs:
            slugs.append(slug)

    for variant in name_variants(raw_name):
        tokens = core_tokens(variant)
        if not tokens:
            continue
        if len(tokens) == 1:
            add(tokens[0])
        else:
            add("".join(tokens))
            add("-".join(tokens))
            if len(tokens) > 2:
                add("".join(tokens[:2]))
                add("-".join(tokens[:2]))
    urls: list[str] = []
    for tld in tlds:
        for slug in slugs:
            url = f"https://{slug}.{tld}"
            if url not in urls:
                urls.append(url)
    return urls[:limit]


def wikidata_query(siren: str) -> str:
    """SPARQL for the official website of the item whose SIREN (P1616) is given."""
    if not re.fullmatch(r"\d{9}", siren or ""):
        raise ValueError("SIREN must be exactly nine digits.")
    return (
        "SELECT ?site WHERE { ?item wdt:P1616 \"%s\" . ?item wdt:P856 ?site . } LIMIT 3" % siren
    )


def wikidata_url(siren: str) -> str:
    return f"{WIKIDATA_ENDPOINT}?format=json&query={quote(wikidata_query(siren))}"


def parse_wikidata_response(payload: Any) -> list[str]:
    """Official-website URLs from a SPARQL JSON response (ignores social/marketplace/directory)."""
    sites: list[str] = []
    try:
        bindings = payload["results"]["bindings"]
    except (KeyError, TypeError):
        return sites
    for binding in bindings:
        value = (binding.get("site") or {}).get("value") if isinstance(binding, dict) else None
        site = normalize_website(value or "")
        if site and site not in sites:
            sites.append(site)
    return sites


def parse_wikidata_text(text: str) -> list[str]:
    try:
        return parse_wikidata_response(json.loads(text))
    except ValueError:
        return []


NOMINATIM_ENDPOINT = "https://nominatim.openstreetmap.org/search"


def osm_search_url(name: str, postal: str, city: str, country: str = "France") -> str:
    """Nominatim query scoped to the company's country when it is one of our supported markets."""
    query = " ".join(part for part in (name_variants(name)[0] if name_variants(name) else name, postal, city) if part)
    country_code = {"france": "fr", "belgium": "be", "belgië": "be", "belgique": "be",
                    "luxembourg": "lu"}.get((country or "").strip().lower())
    country_filter = f"&countrycodes={country_code}" if country_code else ""
    return (
        f"{NOMINATIM_ENDPOINT}?q={quote(query)}&format=jsonv2&extratags=1&limit=3{country_filter}"
    )


def parse_osm_response(payload: Any, company_name: str) -> list[str]:
    """Website URLs from Nominatim results whose place name shares a core token with the company.

    Only a candidate list: every URL is still fetched and must pass ownership verification.
    """
    tokens = set(core_tokens(company_name))
    sites: list[str] = []
    if not isinstance(payload, list) or not tokens:
        return sites
    for place in payload:
        if not isinstance(place, dict):
            continue
        label = f"{place.get('name') or ''} {place.get('display_name') or ''}"
        if not tokens & set(core_tokens(label)):
            continue
        tags = place.get("extratags") or {}
        if not isinstance(tags, dict):
            continue
        for key in ("website", "contact:website", "url"):
            site = normalize_website(str(tags.get(key) or ""))
            if site and site not in sites:
                sites.append(site)
    return sites
