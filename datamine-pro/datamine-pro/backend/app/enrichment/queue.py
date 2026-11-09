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
# Failed rows whose error is transient get a fresh set of attempts after a cooldown, at most
# MAX_CYCLES times in total. Errors starting with "permanent:" are never retried automatically.
MAX_CYCLES = 3
RETRY_COOLDOWN_MINUTES = 30
PERMANENT_PREFIX = "permanent:"
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
        # Additive migration: number of automatic retry cycles already given to a failed row.
        connection.execute("ALTER TABLE enrichment_queue ADD COLUMN IF NOT EXISTS cycles INTEGER NOT NULL DEFAULT 0")
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
        retried = connection.execute("""
            UPDATE enrichment_queue
            SET status='pending', attempts=0, cycles=cycles+1, available_at=NOW(),
                locked_at=NULL, updated_at=NOW()
            WHERE status='failed' AND cycles < %s
              AND COALESCE(last_error, '') NOT LIKE %s
              AND updated_at < NOW() - (%s * INTERVAL '1 minute')
        """, (MAX_CYCLES, PERMANENT_PREFIX + "%", RETRY_COOLDOWN_MINUTES)).rowcount
    if failed or requeued or retried:
        log.warning("queue recovery: requeued=%s failed=%s transient_retried=%s", requeued, failed, retried)
    return {"requeued": max(requeued, 0), "failed": max(failed, 0), "retried": max(retried, 0)}


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


def requeue_outdated(database_url: str, minimum_version: int) -> int:
    """Requeue records created by older enrichment pipelines without deleting stored data."""
    version = max(1, int(minimum_version))
    with _connect(database_url) as connection:
        rows = connection.execute("""
            SELECT q.country, q.registration_number
            FROM enrichment_queue AS q
            LEFT JOIN company_enrichment AS e
              ON e.country = q.country
             AND e.registration_number = q.registration_number
            WHERE q.status <> 'processing'
              AND (
                COALESCE(
                    CASE
                        WHEN COALESCE(e.data->>'enrichmentVersion', '') ~ '^[0-9]+
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
               OR (status='failed' AND cycles < %s AND COALESCE(last_error, '') NOT LIKE %s
                   AND updated_at < NOW() - (%s * INTERVAL '1 minute'))
            LIMIT 1
        """, (MAX_ATTEMPTS, STALE_MINUTES, MAX_CYCLES, PERMANENT_PREFIX + "%", RETRY_COOLDOWN_MINUTES)).fetchone()
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


def mark_failed(database_url: str, record: dict[str, Any], error: str, permanent: bool = False) -> None:
    """Record a failure. Transient: retry with exponential backoff (30s, 60s, 120s... max 15 min)
    until MAX_ATTEMPTS. Permanent: fail immediately with a "permanent:" reason that is never retried."""
    key = record_key(record)
    if not key:
        return
    log.warning("enrichment failed for %s (%s): %s", key, "permanent" if permanent else "transient", error[:200])
    message = (PERMANENT_PREFIX + " " + error if permanent else error)[:500]
    with _connect(database_url) as connection:
        connection.execute("""
            UPDATE enrichment_queue
            SET status = CASE WHEN %s OR attempts >= %s THEN 'failed' ELSE 'pending' END,
                available_at = NOW() + (LEAST(900, 30 * POWER(2, GREATEST(attempts,1) - 1)) * INTERVAL '1 second'),
                locked_at=NULL, last_error=%s, updated_at=NOW()
            WHERE country=%s AND registration_number=%s
        """, (permanent, MAX_ATTEMPTS, message, key[0], key[1]))


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
        causes = connection.execute("""
            SELECT LEFT(COALESCE(last_error, 'no error recorded'), 70) AS cause, COUNT(*)
            FROM enrichment_queue WHERE status='failed'
            GROUP BY 1 ORDER BY 2 DESC LIMIT 8
        """).fetchall()
    result: dict[str, Any] = {"pending": 0, "processing": 0, "done": 0, "failed": 0, "total": 0}
    for status, count in rows:
        result[status] = int(count)
        result["total"] += int(count)
    result["stale"] = int(stale)
    result["failedByCause"] = [{"cause": c[0], "count": int(c[1])} for c in causes]
    result["recentErrors"] = [
        {"country": e[1], "registrationNumber": e[0], "status": e[2], "attempts": e[3], "error": e[4]}
        for e in errors
    ]
    return result

                        THEN (e.data->>'enrichmentVersion')::integer
                        ELSE NULL
                    END,
                    0
                ) < %s
                OR NOT COALESCE(e.data ? 'discoveryComplete', FALSE)
              )
        """, (version,)).fetchall()
        count = 0
        for country, number in rows:
            count += max(connection.execute("""
                UPDATE enrichment_queue
                SET status='pending', attempts=0, cycles=0, last_error=NULL,
                    available_at=NOW(), locked_at=NULL, updated_at=NOW()
                WHERE country=%s AND registration_number=%s AND status <> 'processing'
            """, (country, number)).rowcount, 0)
    if count:
        log.warning("requeued %s outdated enrichment records for pipeline version %s", count, version)
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
               OR (status='failed' AND cycles < %s AND COALESCE(last_error, '') NOT LIKE %s
                   AND updated_at < NOW() - (%s * INTERVAL '1 minute'))
            LIMIT 1
        """, (MAX_ATTEMPTS, STALE_MINUTES, MAX_CYCLES, PERMANENT_PREFIX + "%", RETRY_COOLDOWN_MINUTES)).fetchone()
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


def mark_failed(database_url: str, record: dict[str, Any], error: str, permanent: bool = False) -> None:
    """Record a failure. Transient: retry with exponential backoff (30s, 60s, 120s... max 15 min)
    until MAX_ATTEMPTS. Permanent: fail immediately with a "permanent:" reason that is never retried."""
    key = record_key(record)
    if not key:
        return
    log.warning("enrichment failed for %s (%s): %s", key, "permanent" if permanent else "transient", error[:200])
    message = (PERMANENT_PREFIX + " " + error if permanent else error)[:500]
    with _connect(database_url) as connection:
        connection.execute("""
            UPDATE enrichment_queue
            SET status = CASE WHEN %s OR attempts >= %s THEN 'failed' ELSE 'pending' END,
                available_at = NOW() + (LEAST(900, 30 * POWER(2, GREATEST(attempts,1) - 1)) * INTERVAL '1 second'),
                locked_at=NULL, last_error=%s, updated_at=NOW()
            WHERE country=%s AND registration_number=%s
        """, (permanent, MAX_ATTEMPTS, message, key[0], key[1]))


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
        causes = connection.execute("""
            SELECT LEFT(COALESCE(last_error, 'no error recorded'), 70) AS cause, COUNT(*)
            FROM enrichment_queue WHERE status='failed'
            GROUP BY 1 ORDER BY 2 DESC LIMIT 8
        """).fetchall()
    result: dict[str, Any] = {"pending": 0, "processing": 0, "done": 0, "failed": 0, "total": 0}
    for status, count in rows:
        result[status] = int(count)
        result["total"] += int(count)
    result["stale"] = int(stale)
    result["failedByCause"] = [{"cause": c[0], "count": int(c[1])} for c in causes]
    result["recentErrors"] = [
        {"country": e[1], "registrationNumber": e[0], "status": e[2], "attempts": e[3], "error": e[4]}
        for e in errors
    ]
    return result
