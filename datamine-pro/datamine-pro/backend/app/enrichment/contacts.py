"""Publicly published business contact details, read only from pages of a verified company site.

Nothing is guessed or generated: an email or phone number is returned only when it appears on a
page we already fetched (a mailto:/tel: link, or an address written in the page text), together
with the URL of that page as evidence.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from .pagefacts import PageFacts
from .text import base_domain, host_of

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
IGNORED_DOMAINS = {"example.com", "example.org", "domain.com", "sentry.io", "wixpress.com", "email.com"}
IGNORED_LOCALS = {"name", "email", "nom", "prenom", "votreadresse", "you", "user", "mail"}
FILE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")


def _valid_email(value: str) -> str | None:
    value = value.strip().strip(".,;:<>()[]\"'").lower()
    if not EMAIL.fullmatch(value) or value.endswith(FILE_SUFFIXES):
        return None
    local, _, domain = value.partition("@")
    if domain in IGNORED_DOMAINS or local in IGNORED_LOCALS:
        return None
    return value


def _valid_phone(value: str) -> str | None:
    value = unquote(value).strip()
    digits = re.sub(r"\D", "", value)
    if not 8 <= len(digits) <= 15:
        return None
    return re.sub(r"[^\d+]", "", value) if value.startswith("+") else " ".join(value.split())


def find_contacts(pages: list[PageFacts]) -> dict[str, str | None]:
    """Best published email and phone across the given pages, each with its source page URL."""
    site_domain = base_domain(host_of(pages[0].url)) if pages else ""
    emails: list[tuple[int, str, str]] = []  # (rank, email, page url)
    phones: list[tuple[str, str]] = []
    for page in pages:
        for url, _label in page.links:
            lowered = url.lower()
            if lowered.startswith("mailto:"):
                email = _valid_email(unquote(urlparse(url).path))
                if email:
                    emails.append((0, email, page.url))
            elif lowered.startswith("tel:"):
                phone = _valid_phone(url[4:])
                if phone:
                    phones.append((phone, page.url))
        for found in EMAIL.findall(page.text):
            email = _valid_email(found)
            if email:
                emails.append((1, email, page.url))

    def rank(item: tuple[int, str, str]) -> tuple[int, int]:
        same_domain = base_domain(item[1].split("@", 1)[1]) == site_domain
        return (0 if same_domain else 1, item[0])

    best_email = min(emails, key=rank) if emails else None
    best_phone = phones[0] if phones else None
    return {
        "contactEmail": best_email[1] if best_email else None,
        "contactEmailSource": best_email[2] if best_email else None,
        "contactPhone": best_phone[0] if best_phone else None,
        "contactPhoneSource": best_phone[1] if best_phone else None,
    }
