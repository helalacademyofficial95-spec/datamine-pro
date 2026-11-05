# Backend (future) — not built yet

This folder is intentionally empty of code. The frontend in the parent folder runs completely on its own,
using sample data. When you are ready, build a **separate** Python service here and connect it.

## Planned stack (all free / open source)

- Python 3.11+
- FastAPI (HTTP API) + Uvicorn
- Scrapy and/or Playwright (fetching pages), BeautifulSoup (parsing)
- Pandas (cleaning / de-duplication), OpenPyXL (Excel files on the server if needed)

Suggested layout:

```
backend/
  app/
    main.py            # FastAPI app and routes
    jobs.py            # job queue / status
    spiders/           # Scrapy spiders, one per source type
    enrich/            # B2C website matching, e-mail / phone verification
    models.py          # Pydantic models matching frontend/lib/types.ts
  requirements.txt
  README.md
```

## API the frontend already expects

The typed client lives in `lib/api/client.ts` and the request/response shapes in `lib/api/types.ts`.
Set `NEXT_PUBLIC_API_URL` (see `.env.example`) to the backend address, e.g. `http://localhost:8000`.

| Method | Path                  | Purpose                                      |
| ------ | --------------------- | -------------------------------------------- |
| GET    | `/health`             | `{ "status": "ok" }`                         |
| POST   | `/jobs`               | Create an extraction job (`ExtractionRequest`) → `ExtractionJob` |
| GET    | `/jobs/{id}`          | Job state and progress                        |
| POST   | `/jobs/{id}/cancel`   | Cancel a running job                          |
| GET    | `/jobs/{id}/results`  | `JobResults` with `companies[]`, each `origin: "extracted"` |

Remember to enable CORS for your frontend address in FastAPI.

## Rules the backend must follow

- Read and obey each site's `robots.txt` and terms of use.
- Rate-limit requests and identify your crawler honestly (User-Agent with contact info).
- Never bypass CAPTCHAs, logins, paywalls or any access restriction.
- Treat names, e-mails and phone numbers of people as personal data (GDPR): collect only what you need,
  have a lawful basis, and delete data you no longer need.
- Real records must be returned with `origin: "extracted"` so the UI never confuses them with sample data.
