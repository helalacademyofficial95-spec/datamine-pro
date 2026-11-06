"""Decide whether a candidate website belongs to a given company, and keep the evidence.

Evidence types:
- registration_number : the company's SIREN/SIRET appears on the site's own pages (French law
                        requires the RCS number in a site's legal notice). Strongest evidence.
- name_match          : the distinctive words of the legal/trade name appear in title/text.
- postal_code_match   : the registered postal code appears together with the town.
- registry_published  : the official registry itself lists this website (accepted as-is).

Status rule (never stronger than the evidence):
- Verified            : registration number AND (name OR postal code); or registry-published.
- Partially Verified  : registration number alone, OR name AND postal code without the number.
- Unverified          : anything weaker. The URL is kept only as an audit trail, never reported
                        as the company's website.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from . import NOT_FOUND, PARTIAL, UNVERIFIED, VERIFIED
from .pagefacts import PageFacts
from .text import core_tokens, name_variants, normalize

SEP = r"[ .  ]?"


def _number_pattern(digits: str, allow_suffix: bool) -> re.Pattern[str]:
    body = SEP.join(re.escape(d) for d in digits)
    suffix = rf"(?:{SEP}\d(?:{SEP}\d){{4}})?" if allow_suffix else ""
    return re.compile(rf"(?<![\d]){body}{suffix}(?!\d)")


def registration_ids(company: dict[str, Any]) -> dict[str, str]:
    """{'siret': '...', 'siren': '...'} for the identifiers we hold (digits only)."""
    ids: dict[str, str] = {}
    siret = re.sub(r"\D", "", str(company.get("siret") or ""))
    siren = re.sub(r"\D", "", str(company.get("siren") or ""))
    if len(siret) == 14:
        ids["siret"] = siret
    if len(siren) == 9:
        ids["siren"] = siren
    elif "siret" in ids:
        ids["siren"] = ids["siret"][:9]
    return ids


def find_registration_number(company: dict[str, Any], text: str) -> str | None:
    """Return 'siret' or 'siren' when that identifier appears in the text, else None."""
    ids = registration_ids(company)
    if "siret" in ids and _number_pattern(ids["siret"], False).search(text):
        return "siret"
    if "siren" in ids and _number_pattern(ids["siren"], True).search(text):
        return "siren"
    return None


def _postal_and_city(address: str) -> tuple[str, str]:
    matches = list(re.finditer(r"\b(\d{5})\b\s*([^\d,]*)", address or ""))
    if not matches:
        return "", ""
    last = matches[-1]
    return last.group(1), normalize(last.group(2))


def _name_matches(company_name: str, haystack_normalized: str) -> bool:
    padded = f" {haystack_normalized} "
    for variant in name_variants(company_name):
        tokens = [t for t in core_tokens(variant) if len(t) >= 3]
        if not tokens:
            continue
        found = sum(1 for t in tokens if f" {t} " in padded)
        needed = len(tokens) if len(tokens) <= 2 else max(2, int(len(tokens) * 0.75 + 0.999))
        if found >= needed:
            return True
    return False


@dataclass
class Verification:
    status: str = UNVERIFIED
    evidence: list[dict[str, str]] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.status in (VERIFIED, PARTIAL)


def verify_candidate(company: dict[str, Any], pages: list[PageFacts]) -> Verification:
    """Judge a candidate from the pages we fetched on that same site."""
    result = Verification()
    if not pages:
        return result
    number_hit: tuple[str, str] | None = None
    for page in pages:
        kind = find_registration_number(company, f"{page.title} {page.text}")
        if kind:
            number_hit = (kind, page.url)
            break

    combined = normalize(" ".join(f"{p.title} {p.meta.get('og:site_name', '')} {p.text[:20000]}" for p in pages))
    name_hit = _name_matches(str(company.get("name") or ""), combined)
    postal, city = _postal_and_city(str(company.get("address") or ""))
    full_text = " ".join(p.text for p in pages)
    postal_hit = (
        bool(postal)
        and re.search(rf"(?<!\d){postal}(?!\d)", full_text) is not None
        and (not city or city in normalize(full_text))
    )

    if number_hit:
        result.evidence.append({
            "type": "registration_number",
            "detail": f"{number_hit[0].upper()} of the company found on the site's own page",
            "url": number_hit[1],
        })
    if name_hit:
        result.evidence.append({"type": "name_match", "detail": "Distinctive words of the company name appear on the site", "url": pages[0].url})
    if postal_hit:
        result.evidence.append({"type": "postal_code_match", "detail": f"Registered postal code {postal} and town appear on the site", "url": pages[0].url})

    if number_hit and (name_hit or postal_hit):
        result.status = VERIFIED
    elif number_hit or (name_hit and postal_hit):
        result.status = PARTIAL
    else:
        result.status = UNVERIFIED
    return result


def registry_published(url: str) -> Verification:
    """A website listed by the official registry itself."""
    return Verification(
        status=VERIFIED,
        evidence=[{"type": "registry_published", "detail": "Website published by the official registry", "url": url}],
    )


def not_found_result() -> Verification:
    return Verification(status=NOT_FOUND, evidence=[])
