# DataMine Pro Python API (starter)

This is the first real backend implementation. It fetches only the exact public source URLs supplied by the user, checks each source's `robots.txt`, identifies itself with a User-Agent, spaces requests, and does not bypass logins, CAPTCHAs, paywalls, or other restrictions.

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

- `FRONTEND_ORIGINS`: comma-separated allowed frontend origins. Defaults to the production DataMine Pro URL and localhost.
- `CRAWLER_USER_AGENT`: identify the crawler and provide a monitored contact address before production use. The default uses a reserved example address and MUST be replaced.

## API contract

- `GET /health`
- `POST /jobs` — accepts the frontend `ExtractionRequest`, returns a queued job.
- `GET /jobs/{id}` — job state and progress.
- `POST /jobs/{id}/cancel` — request cancellation.
- `GET /jobs/{id}/results` — returns `{ job, companies }`.

## Important limitations in this first version

- This starter treats each submitted source URL as one possible company page. It extracts visible metadata, email addresses, phone links, and address markup from that page. It does not yet discover multiple company profiles from directory listing pages.
- B2C Website is populated only when the source page itself contains an explicit shop/store/boutique link. It never guesses a storefront domain. Each match needs review.
- Employee counts and turnover are returned as zero when not found because the current frontend contract requires numeric fields. Zero means **unknown/not found**, not a confirmed zero.
- Email and phone values are not independently verified. Verification flags remain false.
- Director names are not collected in this starter version.
- Jobs and results are held in process memory. They disappear when the service restarts and are unsuitable for multi-instance production deployment without persistent storage and a durable queue.
- Each job accepts at most 10 URLs. The service refuses local/private network targets and does not follow redirects.
- Robots rules are treated conservatively: if `robots.txt` cannot be retrieved, the source is skipped. Check website terms and applicable privacy law as well.

Do not use this backend to collect restricted or unnecessary personal data. Only collect business information you are authorized to process.
