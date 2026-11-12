"""Neon/PostgreSQL persistence for enrichment results (separate table; extraction jobs untouched)."""
from __future__ import annotations

import json
from typing import Any

from .merge import Key


def _connect(database_url: str):
    import psycopg  # imported lazily so the pure modules stay dependency-free

    return psycopg.connect(database_url, connect_timeout=10)


def init_table(database_url: str) -> None:
    with _connect(database_url) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS company_enrichment (
                country TEXT NOT NULL,
                registration_number TEXT NOT NULL,
                data JSONB NOT NULL,
                enriched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (country, registration_number)
            )
        """)


def load_map(database_url: str) -> dict[Key, dict[str, Any]]:
    with _connect(database_url) as connection:
        rows = connection.execute("SELECT country, registration_number, data FROM company_enrichment").fetchall()
    return {(row[0], row[1]): row[2] for row in rows if isinstance(row[2], dict)}


def save_one(database_url: str, key: Key, data: dict[str, Any]) -> None:
    from .merge import preserve_better

    with _connect(database_url) as connection:
        row = connection.execute(
            "SELECT data FROM company_enrichment WHERE country=%s AND registration_number=%s", key
        ).fetchone()
        data = preserve_better(row[0] if row and isinstance(row[0], dict) else None, data)
        connection.execute(
            """
            INSERT INTO company_enrichment (country, registration_number, data, enriched_at)
            VALUES (%s, %s, %s::jsonb, NOW())
            ON CONFLICT (country, registration_number) DO UPDATE SET
                data = EXCLUDED.data, enriched_at = NOW()
            """,
            (key[0], key[1], json.dumps(data, ensure_ascii=False)),
        )


def coverage(database_url: str) -> dict[str, int]:
    """Real counts computed in the database (nothing cached or simulated)."""
    with _connect(database_url) as connection:
        row = connection.execute("""
            SELECT
              COUNT(*),
              COUNT(*) FILTER (WHERE data->>'officialWebsite' IS NOT NULL
                               AND data->>'officialWebsiteStatus' IN ('Verified','Partially Verified')),
              COUNT(*) FILTER (WHERE data->>'b2cWebsite' IS NOT NULL
                               AND data->>'b2cStatus' IN ('Verified','Partially Verified')),
              COUNT(*) FILTER (WHERE COALESCE(data->>'contactEmail','') <> ''),
              COUNT(*) FILTER (WHERE COALESCE(data->>'contactPhone','') <> ''),
              COUNT(*) FILTER (WHERE data->>'officialWebsite' IS NOT NULL
                               AND data->>'officialWebsiteStatus' = 'Verified')
            FROM company_enrichment
        """).fetchone()
    keys = ("enriched", "officialWebsites", "b2cWebsites", "emails", "phones", "officialWebsitesVerified")
    return {k: int(v) for k, v in zip(keys, row)}
