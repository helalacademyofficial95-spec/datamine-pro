"""HTTP endpoints for website discovery / B2C enrichment.

GET  /enrichment/status  public, read-only progress of the current/last batch.
POST /enrichment/run     starts one resumable batch. Requires the X-Admin-Token header to match
                         the ENRICHMENT_ADMIN_TOKEN environment variable (the endpoint is disabled
                         while that variable is unset), because it makes outbound requests.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query

from .enrichment import runner, store, queue as durable_queue
from .enrichment.service import token_ok


def build_router(
    *,
    database_url: str,
    user_agent: str,
    load_records: Callable[[], list[dict[str, Any]]],
    admin_token: str,
) -> APIRouter:
    router = APIRouter(prefix="/enrichment", tags=["enrichment"])
    record_counts: dict[str, float] = {"at": -1e9}

    @router.get("/status")
    async def enrichment_status() -> dict[str, Any]:
        enriched: int | None = None
        coverage: dict[str, int] | None = None
        if database_url:
            try:
                coverage = await asyncio.to_thread(store.coverage, database_url)
                enriched = coverage["enriched"]
            except Exception:
                enriched = None
        # Director/contact names live on the extraction records, not on the enrichment rows.
        if coverage is not None:
            now = time.monotonic()
            if now - record_counts["at"] > 60:  # status is polled often; reading every record is not free
                try:
                    records = await asyncio.to_thread(load_records)
                    record_counts.update(at=now, companies=len(records),
                                         directors=sum(1 for r in records if str(r.get("director") or "").strip()))
                except Exception:
                    pass
            if "companies" in record_counts:
                coverage["companies"] = record_counts["companies"]
                coverage["directors"] = record_counts["directors"]
        queue = None
        if database_url:
            try:
                queue = await asyncio.to_thread(durable_queue.queue_status, database_url)
            except Exception:
                queue = None
        # Polling status doubles as a free keep-alive/resume trigger: a worker killed by a Render
        # sleep or redeploy is restarted here without any token (it only drains existing queue rows).
        resumed = False
        if database_url and queue and not runner.state["running"]:
            resumed = await runner.resume_if_needed(database_url=database_url, user_agent=user_agent)
        return {"batch": dict(runner.state), "enrichedCount": enriched, "coverage": coverage, "queue": queue,
                "runEnabled": bool(admin_token), "workerResumed": resumed}

    @router.post("/run", status_code=202)
    async def enrichment_run(
        background_tasks: BackgroundTasks,
        limit: int = Query(default=25, ge=1, le=runner.MAX_BATCH),
        force: bool = False,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not admin_token:
            raise HTTPException(status_code=503, detail="Enrichment is disabled: ENRICHMENT_ADMIN_TOKEN is not configured on the server.")
        if not token_ok(x_admin_token, admin_token):
            raise HTTPException(status_code=401, detail="Missing or invalid admin token.")
        if not database_url:
            raise HTTPException(status_code=503, detail="Persistent storage is not configured.")
        if runner.state["running"]:
            raise HTTPException(status_code=409, detail="An enrichment batch is already running.")
        background_tasks.add_task(
            runner.run_batch,
            database_url=database_url,
            user_agent=user_agent,
            load_records=load_records,
            limit=limit,
            force=force,
        )
        return {"started": True, "limit": limit, "force": force}


    @router.post("/queue/enqueue", status_code=202)
    async def enqueue_all(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
        if not admin_token:
            raise HTTPException(status_code=503, detail="Enrichment is disabled: server admin token is not configured.")
        if not token_ok(x_admin_token, admin_token):
            raise HTTPException(status_code=401, detail="Missing or invalid admin token.")
        if not database_url:
            raise HTTPException(status_code=503, detail="Persistent storage is not configured.")
        records = await asyncio.to_thread(load_records)
        enriched = await asyncio.to_thread(store.load_map, database_url)
        pending = [record for record in records if (key := runner.record_key(record)) is not None and key not in enriched]
        added = await asyncio.to_thread(durable_queue.enqueue_records, database_url, pending)
        return {"queued": added, "recordsChecked": len(records), "alreadyEnriched": len(records) - len(pending)}

    @router.post("/queue/run", status_code=202)
    async def run_queue(background_tasks: BackgroundTasks,
                        x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
        if not admin_token:
            raise HTTPException(status_code=503, detail="Enrichment is disabled: server admin token is not configured.")
        if not token_ok(x_admin_token, admin_token):
            raise HTTPException(status_code=401, detail="Missing or invalid admin token.")
        if not database_url:
            raise HTTPException(status_code=503, detail="Persistent storage is not configured.")
        if runner.state["running"]:
            raise HTTPException(status_code=409, detail="An enrichment worker is already running.")
        background_tasks.add_task(runner.run_queue, database_url=database_url, user_agent=user_agent)
        return {"started": True, "batchSize": runner.QUEUE_BATCH}


    @router.post("/queue/reprocess-outdated", status_code=202)
    async def reprocess_outdated(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
        """Re-run records produced by an older enrichment pipeline without deleting their data."""
        if not admin_token:
            raise HTTPException(status_code=503, detail="Enrichment is disabled: server admin token is not configured.")
        if not token_ok(x_admin_token, admin_token):
            raise HTTPException(status_code=401, detail="Missing or invalid admin token.")
        if not database_url:
            raise HTTPException(status_code=503, detail="Persistent storage is not configured.")
        # Some older enrichment rows predate the durable queue. Rebuild queue entries for
        # those rows from the preserved extraction_jobs source records before requeueing.
        # This is idempotent: the queue primary key prevents duplicates, and enqueue_records
        # never resets completed/processing rows. requeue_outdated below resets only old results.
        records = await asyncio.to_thread(load_records)
        enriched = await asyncio.to_thread(store.load_map, database_url)
        outdated_records = []
        for record in records:
            key = runner.record_key(record)
            data = enriched.get(key) if key else None
            if data and (
                str(data.get("enrichmentVersion", "0")) != str(runner.ENRICHMENT_VERSION)
                or not data.get("discoveryComplete", False)
            ):
                outdated_records.append(record)

        newly_queued = await asyncio.to_thread(
            durable_queue.enqueue_records, database_url, outdated_records
        )
        count = await asyncio.to_thread(
            durable_queue.requeue_outdated, database_url, runner.ENRICHMENT_VERSION
        )
        resumed = False
        if (count or newly_queued) and not runner.state["running"]:
            resumed = await runner.resume_if_needed(database_url=database_url, user_agent=user_agent)
        return {
            "requeued": count,
            "newlyQueued": newly_queued,
            "outdatedRecordsFound": len(outdated_records),
            "recordsScanned": len(records),
            "pipelineVersion": runner.ENRICHMENT_VERSION,
            "workerResumed": resumed,
        }


    @router.post("/queue/requeue-failed", status_code=202)
    async def requeue_failed(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
        if not admin_token:
            raise HTTPException(status_code=503, detail="Enrichment is disabled: server admin token is not configured.")
        if not token_ok(x_admin_token, admin_token):
            raise HTTPException(status_code=401, detail="Missing or invalid admin token.")
        if not database_url:
            raise HTTPException(status_code=503, detail="Persistent storage is not configured.")
        count = await asyncio.to_thread(durable_queue.requeue_failed, database_url)
        return {"requeued": count}

    return router
