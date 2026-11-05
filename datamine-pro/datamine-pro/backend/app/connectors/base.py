"""Shared contracts for reusable country data connectors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SourceMetadata:
    source_id: str
    country_code: str
    name: str
    source_type: str
    public_url: str
    access_model: str
    reuse_review: str
    notes: str


class CountryConnector(Protocol):
    """Contract implemented by a country-specific registry connector."""

    country_code: str
    country_name: str

    def supports_source(self, source_url: str) -> bool:
        """Return True only for URLs owned by this connector."""

    async def search(
        self,
        client: Any,
        *,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return normalized company records with source provenance."""
