"""Country/source capability registry.

Availability here means that a source has been identified, not that a full
connector or commercial reuse permission has been established. Keep these
states explicit so the UI and API never imply unsupported coverage.
"""
from __future__ import annotations

from typing import Any


_COUNTRIES: dict[str, dict[str, Any]] = {
    "FR": {
        "country_code": "FR",
        "country_name": "France",
        "status": "partial",
        "registry_sources": [
            {
                "source_id": "fr-recherche-entreprises",
                "name": "Recherche d'entreprises / Annuaire des Entreprises",
                "source_type": "government_api",
                "public_url": "https://recherche-entreprises.api.gouv.fr/",
                "access_model": "public_api",
                "reuse_review": "review_required",
                "connector": "implemented",
                "notes": "Current connector searches a limited set of terms and pages; not a complete national export.",
            },
            {
                "source_id": "fr-sirene",
                "name": "INSEE SIRENE",
                "source_type": "government_open_data",
                "public_url": "https://www.insee.fr/",
                "access_model": "account_or_open_data_download",
                "reuse_review": "review_required",
                "connector": "planned",
                "notes": "Check current access quotas, diffusion status, and dataset licence before use.",
            },
        ],
    },
    "BE": {
        "country_code": "BE",
        "country_name": "Belgium",
        "status": "planned",
        "registry_sources": [
            {
                "source_id": "be-cbe-kbo",
                "name": "Crossroads Bank for Enterprises (CBE/KBO)",
                "source_type": "government_registry",
                "public_url": "https://economie.fgov.be/",
                "access_model": "public_search_and_open_data",
                "reuse_review": "required_before_implementation",
                "connector": "planned",
                "notes": "Verify the applicable dataset terms, personal-data limits, and commercial reuse conditions before collecting or exporting records.",
            },
        ],
    },
    "LU": {
        "country_code": "LU",
        "country_name": "Luxembourg",
        "status": "planned",
        "registry_sources": [
            {
                "source_id": "lu-lbr",
                "name": "Luxembourg Business Registers",
                "source_type": "government_registry",
                "public_url": "https://www.lbr.lu/",
                "access_model": "public_search",
                "reuse_review": "required_before_implementation",
                "connector": "planned",
                "notes": "Confirm access, extraction restrictions, and reuse/licensing conditions before automation.",
            },
        ],
    },
}


def list_country_capabilities() -> list[dict[str, Any]]:
    """Return a safe, serializable summary of supported country capabilities."""
    return [
        {
            "country_code": item["country_code"],
            "country_name": item["country_name"],
            "status": item["status"],
            "registry_sources": item["registry_sources"],
        }
        for item in _COUNTRIES.values()
    ]


def get_country_capabilities(country: str) -> dict[str, Any] | None:
    """Look up a country by ISO-2 code or its English display name."""
    normalized = country.strip().lower()
    aliases = {
        "france": "FR",
        "belgium": "BE",
        "luxembourg": "LU",
    }
    code = aliases.get(normalized, normalized.upper())
    item = _COUNTRIES.get(code)
    if item is None:
        return None
    return {
        "country_code": item["country_code"],
        "country_name": item["country_name"],
        "status": item["status"],
        "registry_sources": item["registry_sources"],
    }
