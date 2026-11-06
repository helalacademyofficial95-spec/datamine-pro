# Durable enrichment queue

The enrichment queue is additive and stored in Neon/PostgreSQL. It does not delete
or replace extraction records or existing company_enrichment rows.

The backend initializes the queue table at startup. Protected operational endpoints:

- GET /enrichment/status
- POST /enrichment/queue/enqueue
- POST /enrichment/queue/run

The POST endpoints require the server-side ENRICHMENT_ADMIN_TOKEN in the
X-Admin-Token request header. Never expose this token in frontend public settings.

The worker claims at most 50 records per batch, saves enrichment results separately,
and retries transient failures up to three attempts. It respects the existing public
source fetcher, bounded concurrency and per-company timeout.
