"""Glue between the API layer and the enrichment pipeline. Pure and offline-testable.

- token_ok: constant-time admin-token check for the endpoint that starts crawling.
- apply_enrichment: overlay stored enrichment results onto extraction records. Storage
  problems never break the records endpoint: the plain records are returned instead.
"""
from __future__ import annotations

import hmac
from typing import Any, Callable

from .merge import Key, overlay_enrichment, record_key


def token_ok(provided: str | None, expected: str) -> bool:
    """True only when a token is configured AND the caller supplied exactly that token."""
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def apply_enrichment(
    records: list[dict[str, Any]],
    load_map: Callable[[], dict[Key, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Records with enrichment overlaid. Stored extraction records are never modified."""
    try:
        enriched = load_map()
    except Exception:  # enrichment is optional; the 644 real records must still be served
        return records
    out: list[dict[str, Any]] = []
    for record in records:
        key = record_key(record)
        out.append(overlay_enrichment(record, enriched.get(key) if key else None))
    return out
