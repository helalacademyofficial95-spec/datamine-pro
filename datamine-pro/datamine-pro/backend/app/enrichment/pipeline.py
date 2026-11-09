"""Per-company enrichment: discover candidate sites, verify ownership, classify B2C.

The network is injected (a Fetcher), so the whole flow is testable offline. Per company the
work is bounded: at most MAX_CANDIDATES candidate sites, each with a homepage and up to two
legal/contact pages, plus up to two shop pages.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable, Protocol
from urllib.parse import urlparse

from . import ENRICHMENT_VERSION, NOT_FOUND, PARTIAL, UNVERIFIED, VERIFIED
from .classify import assess_site, b2c_status, find_shop_links
from .contacts import find_contacts
from .discovery import guess_domains, normalize_website
from .pagefacts import PageFacts, parse_html
from .text import same_site
from .verify import Verification, registration_ids, registry_published, verify_candidate

MAX_CANDIDATES = 8
LEGAL_LINK = re.compile(
    r"mentions[ -]?l[eé]gales?|legal[ -]?notice|\blegal\b|imprint|impressum|cgv|conditions[ -]g[eé]n[eé]rales|"
    r"a[ -]propos|\babout\b|qui[ -]sommes|\bcontact",
    re.I,
)
LEGAL_PRIORITY = re.compile(r"mentions|legal|imprint|impressum", re.I)
STATUS_RANK = {NOT_FOUND: 0, UNVERIFIED: 1, PARTIAL: 2, VERIFIED: 3}


@dataclass
class FetchedPage:
    url: str  # final URL after redirects
    html: str


class Fetcher(Protocol):
    async def get(self, url: str) -> FetchedPage | None: ...


WikidataLookup = Callable[[str], Awaitable[list[str]]]
OsmLookup = Callable[[dict[str, Any]], Awaitable[list[str]]]


def pick_legal_links(home: PageFacts, limit: int = 2) -> list[str]:
    """Same-site links most likely to hold the legal notice / contact details."""
    scored: dict[str, int] = {}
    for url, label in home.links:
        if urlparse(url).scheme not in ("http", "https") or not same_site(home.url, url):
            continue
        haystack = f"{label} {urlparse(url).path}"
        if not LEGAL_LINK.search(haystack):
            continue
        scored[url.split("#")[0]] = max(scored.get(url.split("#")[0], 0), 2 if LEGAL_PRIORITY.search(haystack) else 1)
    ordered = sorted(scored.items(), key=lambda item: -item[1])
    return [u for u, _ in ordered if u.rstrip("/") != home.url.rstrip("/")][:limit]


async def collect_pages(fetcher: Fetcher, url: str) -> list[PageFacts]:
    home = await fetcher.get(url)
    if not home:
        return []
    home_facts = parse_html(home.html, home.url)
    pages = [home_facts]
    for legal_url in pick_legal_links(home_facts):
        page = await fetcher.get(legal_url)
        if page and same_site(page.url, home.url):
            pages.append(parse_html(page.html, page.url))
    return pages


def _site_root(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{(parsed.hostname or '').lower()}"


def _cap_ownership(status: str, same: bool) -> str:
    """A shop on another domain inherits at most one level less trust than the site linking to it."""
    if same:
        return status
    return {VERIFIED: PARTIAL, PARTIAL: UNVERIFIED}.get(status, status)


def _record_source_failure(exc: Exception, errors: list[str] | None, blocked: list[str] | None) -> None:
    """Transient failures make discovery inconclusive (retry); a source that refuses us is only
    noted - its refusal is neither proof that no website exists nor a reason to retry forever."""
    text = str(exc)[:120] or type(exc).__name__
    target = blocked if getattr(exc, "permanent", False) else errors
    if target is not None:
        target.append(text)


async def _candidate_urls(
    company: dict[str, Any], wikidata: WikidataLookup | None, osm: OsmLookup | None = None,
    errors: list[str] | None = None,
    blocked: list[str] | None = None,
) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen_hosts: set[str] = set()

    def add(url: str, source: str) -> None:
        root = normalize_website(url)
        host = urlparse(root).hostname or ""
        if root and host not in seen_hosts and len(candidates) < MAX_CANDIDATES:
            seen_hosts.add(host)
            candidates.append((root, source))

    add(str(company.get("website") or ""), "registry")
    siren = registration_ids(company).get("siren")
    if wikidata and siren:
        try:
            for site in await wikidata(siren):
                add(site, "wikidata")
        except Exception as exc:  # a source failure never fails the company, but is recorded
            _record_source_failure(exc, errors, blocked)
    if osm:
        try:
            for site in await osm(company):
                add(site, "openstreetmap")
        except Exception as exc:
            _record_source_failure(exc, errors, blocked)
    for guess in guess_domains(str(company.get("name") or "")):
        add(guess, "domain_guess")
    return candidates


def _empty_result(today: date) -> dict[str, Any]:
    return {
        "enrichmentVersion": ENRICHMENT_VERSION,
        "checkedAt": today.isoformat(),
        "officialWebsite": None,
        "officialWebsiteStatus": NOT_FOUND,
        "officialWebsiteSource": None,
        "officialWebsiteCandidate": None,
        "officialWebsiteEvidence": [],
        "b2cWebsite": None,
        "b2cCandidateUrl": None,
        "b2cStatus": NOT_FOUND,
        "b2cConfidence": "low",
        "b2cSiteType": "unknown",
        "b2cEvidence": [],
        "b2cExplanation": "",
        "contactEmail": None,
        "contactEmailSource": None,
        "contactPhone": None,
        "contactPhoneSource": None,
        "candidatesChecked": [],
        "sourceErrors": [],
        "sourcesBlocked": [],
        "discoveryComplete": True,
    }


async def enrich_company(
    company: dict[str, Any],
    fetcher: Fetcher,
    wikidata: WikidataLookup | None = None,
    today: date | None = None,
    osm: OsmLookup | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    result = _empty_result(today)
    candidates = await _candidate_urls(company, wikidata, osm, result["sourceErrors"], result["sourcesBlocked"])

    best: tuple[str, str, Verification, list[PageFacts]] | None = None  # url, source, verification, pages
    weak: tuple[str, Verification] | None = None
    for url, source in candidates:
        pages = await collect_pages(fetcher, url)
        if not pages:
            result["candidatesChecked"].append({"url": url, "source": source, "outcome": "unreachable_or_not_permitted"})
            continue
        root = _site_root(pages[0].url)
        verification = verify_candidate(company, pages)
        if source == "registry":
            verification = Verification(
                status=VERIFIED,
                evidence=registry_published(root).evidence + verification.evidence,
            )
        result["candidatesChecked"].append({"url": root, "source": source, "outcome": verification.status})
        if verification.accepted:
            # First accepted candidate wins: bounded cost beats an exhaustive search.
            best = (root, source, verification, pages)
            break
        if verification.evidence and weak is None:
            weak = (root, verification)

    if best is None:
        # A "not found" is only conclusive when the sources actually answered. If a lookup
        # failed, or the registry-listed site could not be reached, the caller must retry.
        registry_unreached = any(
            c["source"] == "registry" and c["outcome"] == "unreachable_or_not_permitted"
            for c in result["candidatesChecked"]
        )
        if result["sourceErrors"] or registry_unreached:
            result["discoveryComplete"] = False
        if weak:
            result["officialWebsiteStatus"] = UNVERIFIED
            result["officialWebsiteCandidate"] = weak[0]
            result["officialWebsiteEvidence"] = weak[1].evidence
        result["b2cExplanation"] = (
            "No website for this company could be verified "
            f"({len(result['candidatesChecked'])} candidate(s) checked); the registry lists none."
            if not company.get("website")
            else "The registry-listed website could not be reached or inspected."
        )
        if result["sourcesBlocked"]:
            result["b2cExplanation"] += (
                " Some public sources refused access (" + "; ".join(result["sourcesBlocked"])
                + "); that is not evidence that no website exists."
            )
        return result

    root, source, verification, pages = best
    result["officialWebsite"] = root
    result["officialWebsiteStatus"] = verification.status
    result["officialWebsiteSource"] = source
    result["officialWebsiteEvidence"] = verification.evidence
    if source == "domain_guess":
        result["officialWebsiteEvidence"] = [
            {"type": "domain_derived_from_name", "detail": "Domain derived from the company name, then verified on the site itself", "url": root}
        ] + verification.evidence

    result.update(find_contacts(pages))  # only from pages of the accepted site
    home_facts = pages[0]
    best_assessment = assess_site(home_facts)
    b2c_url = root
    ownership = verification.status
    extra_evidence: list[dict[str, str]] = []

    if best_assessment.score < 5:
        for shop_url in find_shop_links(home_facts):
            shop_page = await fetcher.get(shop_url)
            if not shop_page:
                continue
            shop_facts = parse_html(shop_page.html, shop_page.url)
            shop_assessment = assess_site(shop_facts)
            if shop_assessment.site_type == "b2c" and shop_assessment.score > best_assessment.score:
                best_assessment = shop_assessment
                b2c_url = shop_page.url
                ownership = _cap_ownership(verification.status, same_site(root, shop_page.url))
                extra_evidence = [{
                    "type": "linked_from_official_website",
                    "detail": "Shop page is linked from the company's verified/partly verified website",
                    "url": root,
                }]

    status, confidence, explanation = b2c_status(ownership, best_assessment)
    result["b2cStatus"] = status
    result["b2cConfidence"] = confidence
    result["b2cSiteType"] = best_assessment.site_type
    result["b2cEvidence"] = extra_evidence + best_assessment.evidence
    result["b2cExplanation"] = explanation
    if best_assessment.site_type == "b2c":
        if status in (VERIFIED, PARTIAL):
            result["b2cWebsite"] = b2c_url
        else:
            result["b2cCandidateUrl"] = b2c_url  # kept for audit; never counted as a match
    return result
