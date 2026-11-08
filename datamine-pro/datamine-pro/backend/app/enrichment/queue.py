"""Durable, retryable enrichment work queue in Neon/PostgreSQL.

The queue is separate from extraction_jobs and company_enrichment. It never deletes or
rewrites source records. Workers claim rows with SKIP LOCKED so multiple instances cannot
process the same company concurrently.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from .merge import record_key

log = logging.getLogger("datamine.queue")

MAX_ATTEMPTS = 3
# A lease is renewed by the worker heartbeat every minute, so a row untouched for this long
# belongs to a worker that died (restart, redeploy, Render sleep). Default 15 minutes.
STALE_MINUTES = max(5, int(os.environ.get("QUEUE_STALE_MINUTES", "15") or 15))


def _connect(database_url: str):
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def init_table(database_url: str) -> None:
    with _connect(database_url) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS enrichment_queue (
                country TEXT NOT NULL,
                registration_number TEXT NOT NULL,
                record JSONB NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','processing','done','failed')),
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                locked_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (country, registration_number)
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS enrichment_queue_ready_idx
            ON enrichment_queue (status, available_at, created_at)
        """)


def enqueue_records(database_url: str, records: list[dict[str, Any]]) -> int:
    """Add eligible records without resetting completed or currently-running work."""
    inserted = 0
    with _connect(database_url) as connection:
        for record in records:
            key = record_key(record)
            if not key:
                continue
            result = connection.execute("""
                INSERT INTO enrichment_queue
                    (country, registration_number, record, status)
                VALUES (%s, %s, %s::jsonb, 'pending')
                ON CONFLICT (country, registration_number) DO UPDATE SET
                    record = EXCLUDED.record,
                    updated_at = NOW()
                WHERE enrichment_queue.status NOT IN ('done','processing')
            """, (key[0], key[1], json.dumps(record, ensure_ascii=False)))
            inserted += max(result.rowcount, 0)
    return inserted


def recover_stale(database_url: str, stale_minutes: int | None = None) -> dict[str, int]:
    """Release leases whose worker stopped heartbeating. Never touches a fresh lease.

    Rows with attempts left go back to pending (to be retried); rows that already used their
    last attempt become failed with an explanatory error. Nothing is deleted.
    """
    minutes = max(5, int(stale_minutes or STALE_MINUTES))
    with _connect(database_url) as connection:
        failed = connection.execute("""
            UPDATE enrichment_queue
            SET status='failed', locked_at=NULL,
                last_error=COALESCE(last_error, 'Worker lease expired after maximum attempts'),
                updated_at=NOW()
            WHERE status='processing' AND attempts >= %s
              AND locked_at < NOW() - (%s * INTERVAL '1 minute')
        """, (MAX_ATTEMPTS, minutes)).rowcount
        requeued = connection.execute("""
            UPDATE enrichment_queue
            SET status='pending', locked_at=NULL, available_at=NOW(),
                last_error=COALESCE(last_error, 'Worker lease expired; requeued for retry'),
                updated_at=NOW()
            WHERE status='processing' AND attempts < %s
              AND locked_at < NOW() - (%s * INTERVAL '1 minute')
        """, (MAX_ATTEMPTS, minutes)).rowcount
    if failed or requeued:
        log.warning("stale queue recovery: requeued=%s failed=%s", requeued, failed)
    return {"requeued": max(requeued, 0), "failed": max(failed, 0)}


def claim_batch(database_url: str, limit: int) -> list[dict[str, Any]]:
    """Atomically claim a bounded batch (stale leases are recovered first)."""
    recover_stale(database_url)
    with _connect(database_url) as connection:
        rows = connection.execute("""
            WITH candidates AS (
                SELECT country, registration_number
                FROM enrichment_queue
                WHERE attempts < %s
                  AND status IN ('pending','failed') AND available_at <= NOW()
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT %s
            )
            UPDATE enrichment_queue AS q
            SET status = 'processing',
                attempts = q.attempts + 1,
                locked_at = NOW(),
                updated_at = NOW()
            FROM candidates AS c
            WHERE q.country = c.country
              AND q.registration_number = c.registration_number
            RETURNING q.country, q.registration_number, q.record, q.attempts
        """, (MAX_ATTEMPTS, max(1, min(int(limit), 50)))).fetchall()
    return [row[2] for row in rows if isinstance(row[2], dict)]


def touch(database_url: str, records: list[dict[str, Any]]) -> int:
    """Heartbeat: renew the lease of rows this worker is still processing."""
    keys = [k for k in (record_key(r) for r in records) if k]
    if not keys:
        return 0
    with _connect(database_url) as connection:
        count = 0
        for country, number in keys:
            count += max(connection.execute("""
                UPDATE enrichment_queue SET locked_at=NOW()
                WHERE country=%s AND registration_number=%s AND status='processing'
            """, (country, number)).rowcount, 0)
    return count


def requeue_failed(database_url: str) -> int:
    """Explicit operator action: give failed rows a fresh set of bounded attempts."""
    with _connect(database_url) as connection:
        n = connection.execute("""
            UPDATE enrichment_queue
            SET status='pending', attempts=0, available_at=NOW(), locked_at=NULL, updated_at=NOW()
            WHERE status='failed'
        """).rowcount
    return max(n, 0)


def has_ready_work(database_url: str) -> bool:
    with _connect(database_url) as connection:
        row = connection.execute("""
            SELECT 1 FROM enrichment_queue
            WHERE (status IN ('pending','failed') AND attempts < %s)
               OR (status='processing' AND locked_at < NOW() - (%s * INTERVAL '1 minute'))
            LIMIT 1
        """, (MAX_ATTEMPTS, STALE_MINUTES)).fetchone()
    return row is not None


def mark_done(database_url: str, record: dict[str, Any]) -> None:
    key = record_key(record)
    if not key:
        return
    with _connect(database_url) as connection:
        connection.execute("""
            UPDATE enrichment_queue
            SET status='done', locked_at=NULL, last_error=NULL, updated_at=NOW()
            WHERE country=%s AND registration_number=%s
        """, key)


def mark_failed(database_url: str, record: dict[str, Any], error: str) -> None:
    key = record_key(record)
    if not key:
        return
    log.warning("enrichment failed for %s: %s", key, error[:200])
    with _connect(database_url) as connection:
        connection.execute("""
            UPDATE enrichment_queue
            SET status = CASE WHEN attempts >= %s THEN 'failed' ELSE 'pending' END,
                available_at = NOW() + (LEAST(300, 30 * GREATEST(attempts,1)) * INTERVAL '1 second'),
                locked_at=NULL, last_error=%s, updated_at=NOW()
            WHERE country=%s AND registration_number=%s
        """, (MAX_ATTEMPTS, error[:500], key[0], key[1]))


def queue_status(database_url: str) -> dict[str, Any]:
    with _connect(database_url) as connection:
        rows = connection.execute("""
            SELECT status, COUNT(*) FROM enrichment_queue GROUP BY status
        """).fetchall()
        stale = connection.execute("""
            SELECT COUNT(*) FROM enrichment_queue
            WHERE status='processing' AND locked_at < NOW() - (%s * INTERVAL '1 minute')
        """, (STALE_MINUTES,)).fetchone()[0]
        errors = connection.execute("""
            SELECT registration_number, country, status, attempts, LEFT(last_error, 200)
            FROM enrichment_queue WHERE last_error IS NOT NULL
            ORDER BY updated_at DESC LIMIT 5
        """).fetchall()
    result: dict[str, Any] = {"pending": 0, "processing": 0, "done": 0, "failed": 0, "total": 0}
    for status, count in rows:
        result[status] = int(count)
        result["total"] += int(count)
    result["stale"] = int(stale)
    result["recentErrors"] = [
        {"country": e[1], "registrationNumber": e[0], "status": e[2], "attempts": e[3], "error": e[4]}
        for e in errors
    ]
    return result
