"""Regression test: browser preflight must allow the protected enrichment header."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def test_enrichment_admin_header_is_allowed_by_cors_preflight():
    response = TestClient(app).options(
        "/enrichment/run",
        headers={
            "Origin": "https://datamine-pro.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-admin-token",
        },
    )
    assert response.status_code == 200
    allowed = response.headers.get("access-control-allow-headers", "").lower()
    assert "x-admin-token" in allowed
