from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
import uuid
from datetime import date
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl

APP_VERSION = "0.2.0"
USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "DataMineProBot/0.1 (+contact: admin@datamine-pro.example)",
)
MAX_PAGES_PER_SOURCE = 6
MAX_DIRECTORY_PAGES = 10
DIRECTORY_PAGE_SIZE = 25
REQUEST_TIMEOUT = 20.0
HOST_DELAY_SECONDS = 1.0
DIRECTORY_API = "https://recherche-entreprises.api.gouv.fr/search"
DIRECTORY_HOST = "annuaire-entreprises.data.gouv.fr"
jobs: dict[str, dict[str, Any]] = {}
cancelled_jobs: set[str] = set()
_host_locks: dict[str, asyncio.Lock] = {}

app = FastAPI(title="DataMine Pro Extraction API", version=APP_VERSION)

allowed_origins = [
    item.strip()
    for item in os.getenv(
        "FRONTEND_ORIGINS",
        "https://datamine-pro.vercel.app,http://localhost:3000",
    ).split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class RangeFilter(BaseModel):
    min: int | None = None
    max: int | None = None


class ExtractionRequest(BaseModel):
    projectName: str = Field(default="Company extraction", max_length=120)
    sourceUrls: list[HttpUrl] = Field(min_length=1, max_length=10)
    country: str = Field(default="Other", max_length=40)
    employeeRange: RangeFilter = Field(default_factory=RangeFilter)
    turnoverRange: RangeFilter = Field(default_factory=RangeFilter)
    fields: list[str] = Field(default_factory=list)
    complianceConfirmed: bool


class ExtractionJob(BaseModel):
    id: str
    state: str
    progress: int
    message: str
    recordsFound: int


def _public_http_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) websites are supported.")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("Local and private network addresses are not allowed.")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("The website host could not be resolved.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Private, local, or reserved network addresses are not allowed.")
    return raw_url


def _is_annuaire_directory(raw_url: str) -> bool:
    parsed = urlparse(raw_url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return host == DIRECTORY_HOST and parsed.path.rstrip("/") in {"/rechercher", "/recherche"}


async def _get_page(client: httpx.AsyncClient, url: str) -> str | None:
    safe_url = _public_http_url(url)
    host = urlparse(safe_url).hostname or ""
    lock = _host_locks.setdefault(host, asyncio.Lock())
    async with lock:
        await asyncio.sleep(HOST_DELAY_SECONDS)
        try:
            response = await client.get(safe_url, headers={"User-Agent": USER_AGENT})
            if response.status_code != 200:
                return None
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return None
            return response.text[:2_000_000]
        except (httpx.HTTPError, ValueError):
            return None


async def _robots_allows(client: httpx.AsyncClient, url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        _public_http_url(robots_url)
        host = parsed.hostname or ""
        lock = _host_locks.setdefault(host, asyncio.Lock())
        async with lock:
            await asyncio.sleep(HOST_DELAY_SECONDS)
            response = await client.get(
                robots_url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=False,
            )
        if response.status_code == 404:
            return True
        if response.status_code != 200:
            return False
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        return False


def _storefront_from_html(html: str, url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    terms = re.compile(
        r"\b(shop|store|boutique|webshop|e-shop|ecommerce|online shop|"
        r"buy online|shop online|winkel|webwinkel|magasin|acheter|commander|"
        r"boutique en ligne|tienda|comprar|loja|comprar online)\b",
        re.I,
    )
    path_terms = re.compile(r"/(shop|store|boutique|webshop|e-shop|online-shop|shop-online)(/|$|[?#-])", re.I)
    excluded = {
        "facebook.com", "instagram.com", "linkedin.com", "pinterest.com",
        "youtube.com", "tiktok.com", "x.com", "twitter.com",
    }
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(url, anchor["href"].strip())
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        host = parsed.hostname.lower().removeprefix("www.")
        if host in excluded or any(host.endswith("." + item) for item in excluded):
            continue
        label = " ".join((
            anchor.get_text(" ", strip=True),
            str(anchor.get("aria-label", "")),
            str(anchor.get("title", "")),
        ))
        score = (3 if terms.search(label) else 0) + (2 if path_terms.search(parsed.path) else 0)
        if re.search(r"(?i)(shopify|myshopify|woocommerce)", href):
            score += 1
        if score >= 3:
            candidates.append((score, href))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _extract_record(html: str, url: str, country: str, index: int) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    og = soup.find("meta", attrs={"property": "og:site_name"})
    name_meta = soup.find("meta", attrs={"name": re.compile(r"^application-name$", re.I)})
    h1 = soup.find("h1")
    name = (
        (og.get("content") if og else None)
        or (name_meta.get("content") if name_meta else None)
        or (h1.get_text(" ", strip=True) if h1 else None)
        or title
        or urlparse(url).hostname
        or "Unknown company"
    )
    text = soup.get_text(" ", strip=True)
    emails = sorted(set(re.findall(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", html)))
    phones = []
    for link in soup.select('a[href^="tel:"]'):
        value = link.get("href", "").replace("tel:", "").strip()
        if value and value not in phones:
            phones.append(value)
    if not phones:
        for value in re.findall(r"(?<!\w)(?:\+\d{1,3}[ .()-]?)?(?:\d[ .()-]?){7,14}\d", text):
            cleaned = re.sub(r"\s+", " ", value).strip()
            if cleaned and cleaned not in phones:
                phones.append(cleaned)
            if len(phones) >= 3:
                break
    address_node = soup.find("address")
    address = address_node.get_text(" ", strip=True) if address_node else ""
    if not address:
        for tag in soup.select('[itemprop="address"], [class*="address"], [id*="address"]'):
            candidate = tag.get_text(" ", strip=True)
            if 8 <= len(candidate) <= 240:
                address = candidate
                break
    b2c = _storefront_from_html(html, url)
    employee_match = re.search(r"(?i)(?:employees|team size|staff)\D{0,30}(\d[\d, .]*)", text)
    turnover_match = re.search(r"(?i)(?:annual turnover|revenue|chiffre d'affaires)\D{0,30}([€$£]?\s?\d[\d,. ]*\s?(?:million|m|billion|bn|k)?)", text)
    employees = int(re.sub(r"\D", "", employee_match.group(1))) if employee_match else 0
    turnover = 0
    if turnover_match:
        raw = turnover_match.group(1).lower().replace(" ", "").replace(",", "")
        number = re.search(r"\d+(?:\.\d+)?", raw)
        if number:
            multiplier = 1_000_000_000 if any(x in raw for x in ("billion", "bn")) else 1_000_000 if "million" in raw or re.search(r"\d(?:\.\d+)?m$", raw) else 1_000 if re.search(r"\d(?:\.\d+)?k$", raw) else 1
            try:
                turnover = int(float(number.group()) * multiplier)
            except ValueError:
                turnover = 0
    return {
        "id": f"extracted-{uuid.uuid4().hex[:12]}",
        "name": name[:180],
        "director": "",
        "email": emails[0] if emails else "",
        "phone": phones[0] if phones else "",
        "employees": employees,
        "turnover": turnover,
        "country": country,
        "address": address[:240],
        "website": url,
        "b2cWebsite": b2c,
        "emailVerified": False,
        "phoneVerified": False,
        "verification": "Unverified",
        "origin": "extracted",
        "extractedAt": date.today().isoformat(),
    }


# Official directory API workforce bands: INSEE/Recherche d'entreprises codes.
EMPLOYEE_BANDS = [
    ("00", 0, 0), ("01", 1, 2), ("02", 3, 5), ("03", 6, 9),
    ("11", 10, 19), ("12", 20, 49), ("21", 50, 99), ("22", 100, 199),
    ("31", 200, 249), ("32", 250, 499), ("41", 500, 999),
    ("42", 1000, 1999), ("51", 2000, 4999), ("52", 5000, 9999),
    ("53", 10000, 10**9),
]


def _employee_codes(employee_range: RangeFilter) -> list[str]:
    lower = employee_range.min if employee_range.min is not None else 0
    upper = employee_range.max if employee_range.max is not None else 10**9
    return [
        code for code, band_min, band_max in EMPLOYEE_BANDS
        if band_max >= lower and band_min <= upper and code != "00"
    ]


def _latest_turnover(finances: Any) -> int:
    if not isinstance(finances, dict):
        return 0
    candidates: list[tuple[int, int]] = []
    for key, value in finances.items():
        if not isinstance(value, dict):
            continue
        amount = value.get("ca")
        if isinstance(amount, (int, float)) and amount > 0:
            year_match = re.search(r"(20\d{2})", str(key))
            year = int(year_match.group(1)) if year_match else 0
            candidates.append((year, int(amount)))
    return max(candidates, default=(0, 0))[1]


def _directory_record(item: dict[str, Any], country: str) -> dict[str, Any]:
    name = item.get("nom_complet") or item.get("nom_raison_sociale") or ""
    seat = item.get("siege") if isinstance(item.get("siege"), dict) else {}
    address_parts = [
        seat.get("numero_voie"), seat.get("type_voie"), seat.get("libelle_voie"),
        seat.get("complement_adresse"), seat.get("code_postal"), seat.get("libelle_commune"),
    ]
    address = " ".join(str(part).strip() for part in address_parts if part)
    leaders = item.get("dirigeants") if isinstance(item.get("dirigeants"), list) else []
    director_names = []
    for leader in leaders:
        if not isinstance(leader, dict):
            continue
        full_name = " ".join(str(leader.get(key, "")).strip() for key in ("prenoms", "nom")).strip()
        if full_name:
            director_names.append(full_name)
    website = ""
    for container in (item, item.get("complements", {})):
        if not isinstance(container, dict):
            continue
        candidate = container.get("site_web") or container.get("website")
        if isinstance(candidate, str) and candidate.strip():
            website = candidate.strip()
            if not website.startswith(("http://", "https://")):
                website = "https://" + website
            break
    return {
        "id": f"extracted-{uuid.uuid4().hex[:12]}",
        "name": str(name)[:180],
        "director": ", ".join(director_names[:3]),
        "email": "",
        "phone": "",
        # The official API publishes employee bands, not an exact headcount.
        # Keep the numeric field at zero rather than inventing a precise number.
        "employees": 0,
        "turnover": _latest_turnover(item.get("finances")),
        "country": country,
        "address": address[:240],
        "website": website,
        "b2cWebsite": None,
        "emailVerified": False,
        "phoneVerified": False,
        "verification": "Unverified",
        "origin": "extracted",
        "extractedAt": date.today().isoformat(),
    }


async def _run_annuaire_directory(
    client: httpx.AsyncClient,
    job_id: str,
    request: ExtractionRequest,
    source_url: str,
) -> list[dict[str, Any]]:
    if request.country != "France":
        raise RuntimeError("The Annuaire des Entreprises connector currently supports France only. Select France and try again.")
    params: dict[str, Any] = {
        "page": 1,
        "per_page": DIRECTORY_PAGE_SIZE,
        "etat_administratif": "A",
        "minimal": "true",
        "include": "siege,dirigeants,finances,complements",
    }
    codes = _employee_codes(request.employeeRange)
    if codes:
        params["tranche_effectif_salarie"] = ",".join(codes)
    if request.turnoverRange.min is not None:
        params["ca_min"] = request.turnoverRange.min
    if request.turnoverRange.max is not None:
        params["ca_max"] = request.turnoverRange.max

    collected: list[dict[str, Any]] = []
    total_pages = 1
    for page in range(1, MAX_DIRECTORY_PAGES + 1):
        if job_id in cancelled_jobs:
            return collected
        params["page"] = page
        try:
            response = await client.get(
                DIRECTORY_API,
                params=params,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Could not reach the official French company search API: {type(exc).__name__}.") from exc
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "a short time")
            raise RuntimeError(f"The official directory API rate limit was reached. Retry after {retry_after}.")
        if response.status_code != 200:
            raise RuntimeError(f"The official directory API returned HTTP {response.status_code}. Check its availability and try again.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("The official directory API returned an unreadable response.") from exc
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(results, list):
            raise RuntimeError("The official directory API response did not contain a results list.")
        total_pages = int(payload.get("total_pages", 1) or 1)
        for item in results:
            if not isinstance(item, dict):
                continue
            record = _directory_record(item, request.country)
            if not record["name"]:
                continue
            # Enrich only when the official API itself supplies a company website.
            # Respect that website's robots.txt and keep B2C blank unless an explicit
            # storefront link is visible on that company website.
            website = record["website"]
            if website:
                try:
                    if await _robots_allows(client, website):
                        html = await _get_page(client, website)
                        if html:
                            storefront = _storefront_from_html(html, website)
                            record["b2cWebsite"] = storefront
                            page_record = _extract_record(html, website, request.country, len(collected))
                            record["email"] = page_record["email"]
                            record["phone"] = page_record["phone"]
                            if not record["address"]:
                                record["address"] = page_record["address"]
                except (ValueError, httpx.HTTPError):
                    pass
            collected.append(record)
        job.update(
            progress=min(88, 12 + int(76 * page / max(1, min(total_pages, MAX_DIRECTORY_PAGES)))),
            recordsFound=len(collected),
            message=f"Searching official French company directory: page {page} of {min(total_pages, MAX_DIRECTORY_PAGES)}",
        )
        if not results or page >= total_pages or page >= MAX_DIRECTORY_PAGES:
            break
        # Stay comfortably below the API's published per-IP request ceiling.
        await asyncio.sleep(0.3)

    requested = set(request.fields)
    field_map = {
        "Director Name": "director", "Email Address": "email", "Phone Number": "phone",
        "Number of Employees": "employees", "Annual Turnover": "turnover",
        "Company Address": "address", "Company Website": "website",
    }
    for record in collected:
        for label, key in field_map.items():
            if label not in requested and key != "director":
                record[key] = 0 if key in {"employees", "turnover"} else ""
        # B2C Website is always retained because it is a required deliverable.
    return collected


async def _run_job(job_id: str, request: ExtractionRequest) -> None:
    job = jobs[job_id]
    companies: list[dict[str, Any]] = []
    try:
        job.update(state="running", progress=5, message="Checking source permissions")
        timeout = httpx.Timeout(REQUEST_TIMEOUT)
        limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
        async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=False) as client:
            for source_index, source in enumerate(request.sourceUrls):
                if job_id in cancelled_jobs:
                    job.update(state="cancelled", message="Extraction cancelled")
                    return
                source_url = str(source)
                if _is_annuaire_directory(source_url):
                    directory_records = await _run_annuaire_directory(client, job_id, request, source_url)
                    companies.extend(directory_records)
                    continue
                try:
                    source_url = _public_http_url(source_url)
                    if not await _robots_allows(client, source_url):
                        continue
                    html = await _get_page(client, source_url)
                    if not html:
                        continue
                    record = _extract_record(html, source_url, request.country, source_index)
                    employee_count = record["employees"]
                    if employee_count > 0:
                        if request.employeeRange.min is not None and employee_count < request.employeeRange.min:
                            continue
                        if request.employeeRange.max is not None and employee_count > request.employeeRange.max:
                            continue
                    turnover_value = record["turnover"]
                    if turnover_value > 0:
                        if request.turnoverRange.min is not None and turnover_value < request.turnoverRange.min:
                            continue
                        if request.turnoverRange.max is not None and turnover_value > request.turnoverRange.max:
                            continue
                    requested = set(request.fields)
                    field_map = {
                        "Director Name": "director", "Email Address": "email", "Phone Number": "phone",
                        "Number of Employees": "employees", "Annual Turnover": "turnover",
                        "Company Address": "address", "Company Website": "website",
                    }
                    for label, key in field_map.items():
                        if label not in requested and key != "director":
                            record[key] = 0 if key in {"employees", "turnover"} else ""
                    companies.append(record)
                    job.update(
                        progress=min(90, 10 + int(80 * (source_index + 1) / len(request.sourceUrls))),
                        recordsFound=len(companies),
                        message=f"Processed {source_index + 1} of {len(request.sourceUrls)} source websites",
                    )
                except ValueError:
                    continue
        job["companies"] = companies
        job.update(
            state="completed",
            progress=100,
            recordsFound=len(companies),
            message=(
                "Directory extraction finished. Records come from the official French public API. "
                "Websites and B2C matches are included only when explicitly available; missing values remain blank."
                if any(_is_annuaire_directory(str(url)) for url in request.sourceUrls)
                else "Extraction finished. Missing values are left blank; no details were invented."
            ),
        )
    except Exception as exc:
        job.update(state="failed", message=f"Extraction failed: {str(exc)[:240]}")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}


@app.post("/jobs", response_model=ExtractionJob, status_code=202)
async def create_job(payload: ExtractionRequest, background_tasks: BackgroundTasks) -> ExtractionJob:
    if not payload.complianceConfirmed:
        raise HTTPException(status_code=400, detail="Please confirm you are allowed to collect from these sources.")
    if payload.employeeRange.min is not None and payload.employeeRange.max is not None and payload.employeeRange.min > payload.employeeRange.max:
        raise HTTPException(status_code=400, detail="Employee minimum cannot exceed maximum.")
    if payload.turnoverRange.min is not None and payload.turnoverRange.max is not None and payload.turnoverRange.min > payload.turnoverRange.max:
        raise HTTPException(status_code=400, detail="Turnover minimum cannot exceed maximum.")
    job_id = uuid.uuid4().hex
    jobs[job_id] = {
        "id": job_id, "state": "queued", "progress": 0,
        "message": "Job queued", "recordsFound": 0, "companies": [],
    }
    background_tasks.add_task(_run_job, job_id, payload)
    return ExtractionJob(**{key: jobs[job_id][key] for key in ("id", "state", "progress", "message", "recordsFound")})


@app.get("/jobs/{job_id}", response_model=ExtractionJob)
async def get_job(job_id: str) -> ExtractionJob:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found. Jobs are stored in memory on this starter service.")
    return ExtractionJob(**{key: job[key] for key in ("id", "state", "progress", "message", "recordsFound")})


@app.post("/jobs/{job_id}/cancel", response_model=ExtractionJob)
async def cancel_job(job_id: str) -> ExtractionJob:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    cancelled_jobs.add(job_id)
    if job["state"] in {"queued", "running"}:
        job.update(state="cancelled", message="Cancellation requested")
    return ExtractionJob(**{key: job[key] for key in ("id", "state", "progress", "message", "recordsFound")})


@app.get("/jobs/{job_id}/results")
async def get_results(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    summary = ExtractionJob(**{key: job[key] for key in ("id", "state", "progress", "message", "recordsFound")})
    return {"job": summary.model_dump(by_alias=True), "companies": job.get("companies", [])}
