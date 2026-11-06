"""HTTP endpoints for website discovery / B2C enrichment.

GET  /enrichment/status  public, read-only progress of the current/last batch.
POST /enrichment/run     starts one resumable batch. Requires the X-Admin-Token header to match
                         the ENRICHMENT_ADMIN_TOKEN environment variable (the endpoint is disabled
                         while that variable is unset), because it makes outbound requests.
"""
from __future__ import annotations

import asyncio
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

    @router.get("/status")
    async def enrichment_status() -> dict[str, Any]:
        enriched: int | None = None
        if database_url:
            try:
                enriched = len(await asyncio.to_thread(store.load_map, database_url))
            except Exception:
                enriched = None
        queue = None
        if database_url:
            try:
                queue = await asyncio.to_thread(durable_queue.queue_status, database_url)
            except Exception:
                queue = None
        return {"batch": dict(runner.state), "enrichedCount": enriched, "queue": queue, "runEnabled": bool(admin_token)}

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
        return {"started": True, "batchSize": runner.MAX_BATCH}

    return router
