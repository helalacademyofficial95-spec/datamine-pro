"""Decide what a submitted URL is, so a directory is never silently stored as one company.

classify_page() returns one of:
- "listing":     the page itself publishes several companies as structured data (schema.org
                 JSON-LD organisations / an ItemList). Records are returned.
- "single":      the page describes one company (one organisation entity, or published contact
                 details). One record is built by the caller.
- "unsupported": neither. The caller must fail the job with UNSUPPORTED_MESSAGE.

Only structured data and published contact links are used; nothing is guessed. Directories that
render their company list with JavaScript, or that publish no structured data, are reported as
unsupported instead of being mis-parsed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

ORG_TYPES = {
    "Organization", "Corporation", "LocalBusiness", "Store", "Restaurant", "Hotel", "Bakery",
    "CafeOrCoffeeShop", "BarOrPub", "FoodEstablishment", "HairSalon", "BeautySalon",
    "HealthAndBeautyBusiness", "ClothingStore", "FurnitureStore", "Florist", "BookStore",
    "ShoeStore", "JewelryStore", "Optician", "AutoDealer", "LodgingBusiness", "ProfessionalService",
    "OnlineStore", "Dentist", "Physician", "LegalService", "RealEstateAgent", "TravelAgency",
}
MIN_LISTING_ITEMS = 3
MAX_LISTING_RECORDS = 250

UNSUPPORTED_MESSAGE = (
    "This web address was not recognised as a supported company source. DataMine Pro can read the "
    "French Annuaire des Entreprises search, pages that publish several companies as structured "
    "data (schema.org), and single company websites. Directories that load their list with "
    "JavaScript or publish no structured data are not supported yet."
)
UNSUPPORTED_REGISTRY_MESSAGE = (
    "Belgian (KBO/BCE) and Luxembourg (LBR/RCS) registries are not supported yet: their terms "
    "restrict automated extraction of search pages, so no connector has been built."
)
REGISTRY_HOSTS = {"kbopub.economie.fgov.be", "economie.fgov.be", "kbo-bce.be", "lbr.lu", "www.lbr.lu", "rcsl.lu"}


def is_unsupported_registry(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in REGISTRY_HOSTS or any(host.endswith("." + h) for h in REGISTRY_HOSTS)


def _types(node: dict[str, Any]) -> set[str]:
    value = node.get("@type")
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {v for v in value if isinstance(v, str)}
    return set()


def _walk(node: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(node, list):
        for child in node:
            _walk(child, out)
    elif isinstance(node, dict):
        if _types(node) & ORG_TYPES and node.get("name"):
            out.append(node)
        for key, child in node.items():
            if key != "@context":
                _walk(child, out)


def jsonld_organisations(soup: BeautifulSoup) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            _walk(json.loads(script.string or script.get_text() or ""), found)
        except ValueError:
            continue
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in found:
        key = str(item.get("name", "")).strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _address(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()[:240]
    if isinstance(value, dict):
        parts = [value.get(k) for k in ("streetAddress", "postalCode", "addressLocality")]
        return " ".join(str(p).strip() for p in parts if p)[:240]
    return ""


def record_from_jsonld(item: dict[str, Any], page_url: str, country: str) -> dict[str, Any]:
    name = str(item.get("name", "")).strip()[:180]
    link = str(item.get("url") or "").strip()
    # An item's own url on a directory is the directory's detail page, not the company's site.
    source_url = link if link.startswith(("http://", "https://")) else page_url
    digest = hashlib.sha1(f"{country}|{name.lower()}|{_address(item.get('address'))}".encode()).hexdigest()[:12]
    return {
        "id": f"gen-{digest}",
        "name": name,
        "director": "",
        "email": str(item.get("email") or "").replace("mailto:", "").strip(),
        "phone": str(item.get("telephone") or "").strip(),
        "employees": 0,
        "turnover": 0,
        "country": country,
        "address": _address(item.get("address")),
        "website": "",
        "b2cWebsite": None,
        "b2cWebsiteStatus": "not_checked",
        "sourceName": urlparse(page_url).hostname or "",
        "sourceUrl": source_url,
        "sourceType": "structured_data_listing",
        "emailVerified": False,
        "phoneVerified": False,
        "verification": "Unverified",
        "origin": "extracted",
        "extractedAt": date.today().isoformat(),
    }


def classify_page(html: str, url: str, country: str) -> tuple[str, list[dict[str, Any]]]:
    soup = BeautifulSoup(html, "html.parser")
    orgs = jsonld_organisations(soup)
    if len(orgs) >= MIN_LISTING_ITEMS:
        records = [record_from_jsonld(o, url, country) for o in orgs[:MAX_LISTING_RECORDS]]
        return "listing", records
    has_contact = bool(soup.select('a[href^="tel:"], a[href^="mailto:"], address'))
    if len(orgs) in (1, 2) or has_contact:
        return "single", []
    return "unsupported", []
