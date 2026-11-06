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
    if len(registration) < 8 or not country:
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

    b2c_status = data.get("b2cStatus") or NOT_FOUND
    b2c_url = data.get("b2cWebsite") if b2c_status in (VERIFIED, PARTIAL) else None
    out["b2cWebsite"] = b2c_url
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
