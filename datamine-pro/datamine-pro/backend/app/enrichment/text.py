"""Text normalisation and company-name helpers (standard library only)."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

# Legal-form words that are not part of a brand name.
LEGAL_TOKENS = {
    "sarl", "sas", "sasu", "eurl", "sa", "snc", "sci", "scp", "sca", "scop", "selarl",
    "selas", "sel", "ei", "eirl", "earl", "gaec", "gie", "sc", "scm", "sccv", "se",
    "societe", "anonyme", "responsabilite", "limitee", "unipersonnelle", "simplifiee",
    "par", "actions", "association", "entreprise", "individuelle", "et", "cie", "compagnie",
}
STOP_TOKENS = {"de", "du", "des", "la", "le", "les", "l", "d", "the", "and", "au", "aux", "en", "a"}


def normalize(text: str) -> str:
    """Lowercase, strip accents, collapse everything non-alphanumeric to single spaces."""
    text = (text or "").replace("œ", "oe").replace("Œ", "oe").replace("æ", "ae").replace("Æ", "ae")
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def name_variants(raw_name: str) -> list[str]:
    """Registry names look like 'LEGAL NAME (TRADE NAME)'. Return each distinct part."""
    raw_name = (raw_name or "").strip()
    parts = [re.sub(r"\(.*?\)", " ", raw_name)]
    parts += re.findall(r"\(([^)]+)\)", raw_name)
    seen: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def core_tokens(name: str) -> list[str]:
    """Distinctive words of a name: no legal forms, no articles."""
    tokens = [t for t in normalize(name).split() if t not in LEGAL_TOKENS and t not in STOP_TOKENS]
    return tokens


def host_of(url: str) -> str:
    """Lowercase host without a leading 'www.'."""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def base_domain(host: str) -> str:
    """Last two labels (adequate for .fr/.be/.lu/.com; not a full public-suffix lookup)."""
    labels = [p for p in host.split(".") if p]
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def same_site(url_a: str, url_b: str) -> bool:
    """True when both URLs belong to the same registrable site (shop.x.fr and x.fr match)."""
    a, b = host_of(url_a), host_of(url_b)
    return bool(a) and bool(b) and base_domain(a) == base_domain(b)


def host_matches(host: str, domains: set[str]) -> bool:
    """True when host equals or is a subdomain of any listed domain."""
    host = host.lower()
    host = host[4:] if host.startswith("www.") else host
    return any(host == d or host.endswith("." + d) for d in domains)
