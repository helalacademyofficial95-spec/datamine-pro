"""HTTP behaviour of /enrichment/* (runs where FastAPI is installed, e.g. CI)."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.enrichment import runner  # noqa: E402
from app.enrichment_routes import build_router  # noqa: E402


@pytest.fixture
def calls(monkeypatch):
    recorded: list[dict] = []

    async def fake_run_batch(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(runner, "run_batch", fake_run_batch)
    monkeypatch.setattr(runner, "state", {**runner.state, "running": False})
    return recorded


def client(token="s3cret", database_url="postgres://x"):
    app = FastAPI()
    app.include_router(build_router(
        database_url=database_url, user_agent="TestBot/1.0", load_records=lambda: [], admin_token=token,
    ))
    return TestClient(app)


def test_run_disabled_without_configured_token(calls):
    r = client(token="").post("/enrichment/run", headers={"X-Admin-Token": "anything"})
    assert r.status_code == 503 and calls == []


def test_run_rejects_missing_or_wrong_token(calls):
    c = client()
    assert c.post("/enrichment/run").status_code == 401
    assert c.post("/enrichment/run", headers={"X-Admin-Token": "nope"}).status_code == 401
    assert calls == []


def test_run_starts_a_batch_with_bounded_limit(calls):
    c = client()
    r = c.post("/enrichment/run?limit=10", headers={"X-Admin-Token": "s3cret"})
    assert r.status_code == 202 and r.json() == {"started": True, "limit": 10, "force": False}
    assert len(calls) == 1
    assert calls[0]["limit"] == 10 and calls[0]["database_url"] == "postgres://x" and calls[0]["user_agent"] == "TestBot/1.0"
    assert c.post("/enrichment/run?limit=500", headers={"X-Admin-Token": "s3cret"}).status_code == 422
    assert c.post("/enrichment/run?limit=0", headers={"X-Admin-Token": "s3cret"}).status_code == 422


def test_run_conflicts_while_a_batch_is_running(calls, monkeypatch):
    monkeypatch.setitem(runner.state, "running", True)
    r = client().post("/enrichment/run", headers={"X-Admin-Token": "s3cret"})
    assert r.status_code == 409 and calls == []


def test_run_requires_storage(calls):
    r = client(database_url="").post("/enrichment/run", headers={"X-Admin-Token": "s3cret"})
    assert r.status_code == 503 and calls == []


def test_status_is_public_and_reports_whether_run_is_enabled(calls):
    r = client(database_url="").get("/enrichment/status")
    body = r.json()
    assert r.status_code == 200
    assert body["runEnabled"] is True and body["enrichedCount"] is None
    assert {"running", "processed", "officialWebsitesFound", "b2cMatches"} <= set(body["batch"])
    assert client(token="").get("/enrichment/status").json()["runEnabled"] is False



def test_reprocess_outdated_requires_admin_token_and_requeues_safely(calls, monkeypatch):
    requeued = []
    resumed = []
    enqueued = []

    def fake_enqueue(database_url, records):
        enqueued.append((database_url, records))
        return len(records)

    def fake_requeue(database_url, version):
        requeued.append((database_url, version))
        return 12

    async def fake_resume_if_needed(**kwargs):
        resumed.append(kwargs)
        return True

    monkeypatch.setattr("app.enrichment_routes.durable_queue.enqueue_records", fake_enqueue)
    monkeypatch.setattr("app.enrichment_routes.durable_queue.requeue_outdated", fake_requeue)
    monkeypatch.setattr(runner, "resume_if_needed", fake_resume_if_needed)

    c = client()
    assert c.post("/enrichment/queue/reprocess-outdated").status_code == 401
    response = c.post("/enrichment/queue/reprocess-outdated", headers={"X-Admin-Token": "s3cret"})
    assert response.status_code == 202
    assert response.json() == {"requeued": 12, "newlyQueued": 0, "outdatedRecordsFound": 0, "recordsScanned": 0, "pipelineVersion": runner.ENRICHMENT_VERSION, "workerResumed": True}
    assert enqueued == [("postgres://x", [])]
    assert requeued == [("postgres://x", runner.ENRICHMENT_VERSION)]
    assert len(resumed) == 1
