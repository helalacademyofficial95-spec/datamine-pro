"""Durable, retryable enrichment work queue in Neon/PostgreSQL.

The queue is separate from extraction_jobs and company_enrichment. It never deletes or
rewrites source records. Workers claim rows with SKIP LOCKED so multiple instances cannot
process the same company concurrently.
"""
from __future__ import annotations

import json
from typing import Any

from .merge import record_key

MAX_ATTEMPTS = 3
STALE_MINUTES = 10


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


def claim_batch(database_url: str, limit: int) -> list[dict[str, Any]]:
    """Atomically claim a bounded batch and recover stale processing leases."""
    with _connect(database_url) as connection:
        rows = connection.execute("""
            WITH candidates AS (
                SELECT country, registration_number
                FROM enrichment_queue
                WHERE attempts < %s
                  AND (
                    (status IN ('pending','failed') AND available_at <= NOW())
                    OR (status = 'processing' AND locked_at < NOW() - (%s * INTERVAL '1 minute'))
                  )
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
        """, (MAX_ATTEMPTS, STALE_MINUTES, max(1, min(int(limit), 50)))).fetchall()
    return [row[2] for row in rows if isinstance(row[2], dict)]


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
    with _connect(database_url) as connection:
        connection.execute("""
            UPDATE enrichment_queue
            SET status = CASE WHEN attempts >= %s THEN 'failed' ELSE 'pending' END,
                available_at = NOW() + (LEAST(300, 30 * GREATEST(attempts,1)) * INTERVAL '1 second'),
                locked_at=NULL, last_error=%s, updated_at=NOW()
            WHERE country=%s AND registration_number=%s
        """, (MAX_ATTEMPTS, error[:500], key[0], key[1]))


def queue_status(database_url: str) -> dict[str, int]:
    with _connect(database_url) as connection:
        rows = connection.execute("""
            SELECT status, COUNT(*) FROM enrichment_queue GROUP BY status
        """).fetchall()
    result = {"pending": 0, "processing": 0, "done": 0, "failed": 0, "total": 0}
    for status, count in rows:
        result[status] = int(count)
        result["total"] += int(count)
    return result
