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
    with _connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO company_enrichment (country, registration_number, data, enriched_at)
            VALUES (%s, %s, %s::jsonb, NOW())
            ON CONFLICT (country, registration_number) DO UPDATE SET
                data = EXCLUDED.data, enriched_at = NOW()
            """,
            (key[0], key[1], json.dumps(data, ensure_ascii=False)),
        )
