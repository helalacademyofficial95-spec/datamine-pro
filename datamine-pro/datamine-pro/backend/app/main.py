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

APP_VERSION = "0.1.0"
USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "DataMineProBot/0.1 (+contact: admin@datamine-pro.example)",
)
MAX_PAGES_PER_SOURCE = 6
REQUEST_TIMEOUT = 12.0
HOST_DELAY_SECONDS = 1.0
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
            # A confirmed missing robots.txt means there are no published crawl rules.
            return True
        if response.status_code != 200:
            return False
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        return False


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

    # Match a B2C storefront only when the source explicitly identifies a shop.
    # Consider visible/accessibility labels and shop-like URL paths; never invent domains.
    b2c_candidates: list[tuple[int, str]] = []
    shop_terms = re.compile(
        r"\b(shop|store|boutique|webshop|e-shop|ecommerce|online shop|"
        r"buy online|shop online|winkel|webwinkel|magasin|acheter|commander|"
        r"boutique en ligne|tienda|comprar|loja|comprar online)\b",
        re.I,
    )
    shop_path_terms = re.compile(
        r"/(shop|store|boutique|webshop|e-shop|online-shop|shop-online)(/|$|[?#-])",
        re.I,
    )
    excluded_hosts = {
        "facebook.com", "instagram.com", "linkedin.com", "pinterest.com",
        "youtube.com", "tiktok.com", "x.com", "twitter.com",
    }
    for anchor in soup.find_all("a", href=True):
        href = urljoin(url, anchor["href"].strip())
        parsed_href = urlparse(href)
        if parsed_href.scheme not in {"http", "https"} or not parsed_href.hostname:
            continue
        host = parsed_href.hostname.lower().removeprefix("www.")
        if host in excluded_hosts or any(host.endswith("." + item) for item in excluded_hosts):
            continue
        label = " ".join([
            anchor.get_text(" ", strip=True),
            str(anchor.get("aria-label", "")),
            str(anchor.get("title", "")),
        ]).strip()
        score = 0
        if shop_terms.search(label):
            score += 3
        if shop_path_terms.search(parsed_href.path):
            score += 2
        if re.search(r"(?i)(shopify|myshopify|woocommerce)", href):
            score += 1
        if score >= 3:
            b2c_candidates.append((score, href))

    # Prefer the clearest explicit storefront link; preserve the source's exact URL.
    b2c = max(b2c_candidates, key=lambda item: item[0])[1] if b2c_candidates else None

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
                try:
                    source_url = _public_http_url(source_url)
                    if not await _robots_allows(client, source_url):
                        continue
                    html = await _get_page(client, source_url)
                    if not html:
                        continue
                    record = _extract_record(html, source_url, request.country, source_index)

                    # Apply numeric filters only when a source actually exposes a value.
                    # Zero represents unknown in the current frontend data model.
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

                    # Keep the Company Name as the required record identifier. Other
                    # optional fields are blanked when the user did not request them.
                    requested = set(request.fields)
                    field_map = {
                        "Director Name": "director",
                        "Email Address": "email",
                        "Phone Number": "phone",
                        "Number of Employees": "employees",
                        "Annual Turnover": "turnover",
                        "Company Address": "address",
                        "Company Website": "website",
                        "B2C Website": "b2cWebsite",
                    }
                    for label, key in field_map.items():
                        # B2C Website is a required client deliverable, so retain it even if other optional fields are unchecked.
                        if label not in requested and key != "b2cWebsite":
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
            message="Extraction finished. Missing values are left blank; no details were invented.",
        )
    except Exception as exc:
        job.update(state="failed", message=f"Extraction failed: {type(exc).__name__}")


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
