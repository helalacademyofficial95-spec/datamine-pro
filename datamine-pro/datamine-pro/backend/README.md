# DataMine Pro Python API

This FastAPI service supports public, permitted company-page extraction and a dedicated connector for the French Annuaire des Entreprises search page.

## Deployment

The Render web service is connected to the `feature/python-extraction-backend` branch with automatic deploys enabled. Changes pushed to this branch should trigger a backend deployment.

## Run locally

From this `backend` directory:

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Check `http://localhost:8000/health` and API docs at `http://localhost:8000/docs`.

## Environment

- `FRONTEND_ORIGINS`: comma-separated allowed frontend origins.
- `CRAWLER_USER_AGENT`: descriptive crawler identity. Replace the example contact before wider use.

## API contract

- `GET /health`
- `POST /jobs` — accepts the frontend extraction request.
- `GET /jobs/{id}` — job state and progress.
- `POST /jobs/{id}/cancel` — request cancellation.
- `GET /jobs/{id}/results` — returns `{ job, companies }`.

## French Annuaire des Entreprises connector

When the submitted source is `https://annuaire-entreprises.data.gouv.fr/rechercher`, the service uses the official open Recherche d'Entreprises API that powers the directory search, rather than attempting to scrape the search page's HTML.

- API: `https://recherche-entreprises.api.gouv.fr/search`
- Supports France only.
- Uses the selected employee band and annual turnover minimum/maximum filters.
- Requests active legal units and includes public registered-office, director, finance, and company-complement fields.
- Fetches up to 10 pages × 25 records (maximum 250 records per run) to keep free-service jobs bounded.
- Observes the API's published rate limit with a delay between page requests and handles HTTP 429 without retry storms.
- When an official company website is supplied in the API result, the service checks its robots.txt before fetching it. Public email/phone details and a B2C storefront link are added only when visibly present on that permitted website.
- B2C website is never guessed. If no explicit storefront link is found, the field remains blank.

The official API does not expose every field shown on the directory website. Employee headcount is provided in bands, not as an exact count; this connector leaves the exact numeric employee field at zero (unknown) rather than fabricating a number. Turnover can also be absent. Director names are only included when supplied by the public API. Email and phone are not independently verified.

Official API documentation: https://recherche-entreprises.api.gouv.fr/docs/

## Website discovery and B2C matching (`/enrichment`)

The registry publishes no websites, so a separate, resumable step looks for them after extraction. Results are stored in their own Neon table (`company_enrichment`, keyed by country + registration number); extraction records are never modified and are overlaid with the results only when `GET /companies` is served.

- `POST /enrichment/run?limit=25` starts one batch (max 50 companies). Send the header `X-Admin-Token: <ENRICHMENT_ADMIN_TOKEN>`. The endpoint is disabled while that environment variable is unset. Call it again to continue with the next unprocessed companies.
- `GET /enrichment/status` shows batch progress (public, read-only).
- Candidate sites come from the registry, Wikidata (by SIREN) and domains derived from the company name. Search-engine pages and commercial directories are not scraped.
- A site is reported only after it was fetched and inspected. "Verified" requires the company's SIREN/SIRET on the site's own legal notice plus a name or postal-code match; weaker evidence is "Partially Verified" or "Unverified" (kept as an audit trail, never shown as the company's website).
- B2C status is separate from ownership and never stronger than either: marketplaces, social pages and directories are never accepted, and B2B-only sites are marked "Not Applicable".
- Every request honours robots.txt, is rate-limited per host, refuses private network addresses, and caps page size. Set `CRAWLER_USER_AGENT` to a real contact address.
- Emails and phone numbers are not collected by this step yet.

Environment: `ENRICHMENT_ADMIN_TOKEN` (long random secret), `CRAWLER_USER_AGENT`.

## Supported sources (what a submitted URL may be)

- French Annuaire des Entreprises search URL: official API (tested against fixtures and, earlier, a real run of 644 records).
- A page that publishes several companies as schema.org JSON-LD: one record per company (tested on fixtures only, not on real directories).
- A single company website: one record from its visible metadata and contacts.
- Anything else (JavaScript-only directories, pages without structured data) fails with a clear message instead of being stored as one company.
- Belgian (KBO) and Luxembourg (LBR) registry pages are rejected with a message: no connector exists yet.

## Other public website URLs

Other submitted URLs are still treated as individual company pages, not as directory discovery sources. The service extracts visible metadata, email addresses, phone links, address markup, and explicit shop/store links from each permitted page.

## Important limitations and safeguards

- The French connector is currently the only supported directory adapter.
- Jobs and results are held in process memory and disappear if the Render service restarts.
- Each job accepts at most 10 source URLs.
- The service refuses local/private network targets and does not bypass logins, CAPTCHAs, paywalls, or access restrictions.
- Website enrichment is skipped if robots.txt cannot be checked or disallows the crawler.
- The French public API excludes non-diffusible businesses and may not expose all information available on the directory website.
- Review extracted records before use. Missing values remain blank/unknown; email and phone are not verified.
- Use only information you are authorized to process and follow the source's terms and applicable privacy requirements.
