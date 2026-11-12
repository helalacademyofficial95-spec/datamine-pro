"""Pure helpers that connect enrichment results to stored company records.

Enrichment lives in its own table keyed by (country, registration number). Stored extraction
records are never modified; results are overlaid when records are read.
"""
from __future__ import annotations

import re
from typing import Any

from . import NOT_APPLICABLE, NOT_FOUND, PARTIAL, UNVERIFIED, VERIFIED

STATUS_SLUG = {
    VERIFIED: "verified",
    PARTIAL: "partially_verified",
    UNVERIFIED: "unverified",
    NOT_FOUND: "not_found",
    NOT_APPLICABLE: "not_applicable",
}

Key = tuple[str, str]


def record_key(record: dict[str, Any]) -> Key | None:
    """(country, registration number). None when the record has no usable identifier."""
    registration = re.sub(r"\D", "", str(record.get("siren") or record.get("sourceRecordId") or ""))
    country = str(record.get("country") or "").strip()
    if len(registration) < 8 and str(record.get("id") or "").startswith("gen-"):
        registration = str(record["id"])  # records from structured-data listings have no registry number
    if (len(registration) < 8) or not country:
        return None
    return country, registration


def overlay_enrichment(record: dict[str, Any], data: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of the record with enrichment applied. Original values are not overwritten
    by anything unverified: only Verified / Partially Verified results change visible fields."""
    out = dict(record)
    if not data:
        return out
    out["enrichment"] = data

    site_status = data.get("officialWebsiteStatus")
    if data.get("officialWebsite") and site_status in (VERIFIED, PARTIAL):
        out["website"] = data["officialWebsite"]
        out["verification"] = "Verified" if site_status == VERIFIED else "Partially verified"

        if data.get("contactEmail") and not out.get("email"):
            out["email"] = data["contactEmail"]
            out["emailSource"] = data.get("contactEmailSource") or ""
        if data.get("contactPhone") and not out.get("phone"):
            out["phone"] = data["contactPhone"]
            out["phoneSource"] = data.get("contactPhoneSource") or ""
    evidence = data.get("officialWebsiteEvidence") or []
    out["websiteStatus"] = STATUS_SLUG.get(site_status or NOT_FOUND, "not_found")
    out["websiteSourceUrl"] = next((e.get("url") for e in evidence if e.get("url")), "") if out.get("website") else ""
    out["checkedAt"] = data.get("checkedAt") or ""

    b2c_status = data.get("b2cStatus") or NOT_FOUND
    b2c_url = data.get("b2cWebsite") if b2c_status in (VERIFIED, PARTIAL) else None
    out["b2cWebsite"] = b2c_url
    out["b2cSourceUrl"] = b2c_url or ""
    out["b2cWebsiteStatus"] = STATUS_SLUG.get(b2c_status, "not_found")
    return out


def select_pending(
    records: list[dict[str, Any]],
    enriched: set[Key],
    limit: int,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Records still to enrich, in stored order, without duplicates."""
    pending: list[dict[str, Any]] = []
    seen: set[Key] = set()
    for record in records:
        key = record_key(record)
        if key is None or key in seen:
            continue
        seen.add(key)
        if force or key not in enriched:
            pending.append(record)
        if len(pending) >= limit:
            break
    return pending


_RANK = {VERIFIED: 3, PARTIAL: 2, UNVERIFIED: 1}
_SITE_FIELDS = (
    "officialWebsite", "officialWebsiteStatus", "officialWebsiteSource", "officialWebsiteCandidate",
    "officialWebsiteEvidence", "b2cWebsite", "b2cCandidateUrl", "b2cStatus", "b2cConfidence",
    "b2cSiteType", "b2cEvidence", "b2cExplanation", "contactEmail", "contactEmailSource",
    "contactPhone", "contactPhoneSource", "checkedAt",
)


def preserve_better(existing: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    """A re-check must never replace a better stored result with a worse one.

    If the stored result has a stronger official-website status than the new run (e.g. a source
    was unavailable this time), keep the stored website/B2C/contact evidence. A new result that
    is as good or better wins; missing contacts are filled from the stored result only when it
    is for the very same website.
    """
    if not existing:
        return new
    old_rank = _RANK.get(existing.get("officialWebsiteStatus") or "", 0) if existing.get("officialWebsite") else 0
    new_rank = _RANK.get(new.get("officialWebsiteStatus") or "", 0) if new.get("officialWebsite") else 0
    merged = dict(new)
    if old_rank > new_rank:
        for field in _SITE_FIELDS:
            if field in existing:
                merged[field] = existing[field]
        merged["preservedFromPrevious"] = True
        return merged
    if old_rank and existing.get("officialWebsite") == new.get("officialWebsite"):
        for field in ("contactEmail", "contactEmailSource", "contactPhone", "contactPhoneSource"):
            if not merged.get(field) and existing.get(field):
                merged[field] = existing[field]
    return merged
