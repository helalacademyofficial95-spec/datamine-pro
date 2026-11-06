"""Resumable batch enrichment for Render Free.

Free hosting sleeps and restarts, so work is done in small batches. Each company's result is
saved the moment it finishes; the next batch simply continues with the records that have no
result yet. Only one batch runs at a time.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from . import ENRICHMENT_VERSION, store
from .fetcher import HttpFetcher, make_wikidata_lookup
from .merge import record_key, select_pending
from .pipeline import enrich_company

MAX_BATCH = 50
PER_COMPANY_TIMEOUT = 90.0
CONCURRENCY = 3

state: dict[str, Any] = {
    "running": False,
    "startedAt": None,
    "finishedAt": None,
    "target": 0,
    "processed": 0,
    "failed": 0,
    "officialWebsitesFound": 0,
    "b2cMatches": 0,
    "lastError": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def run_batch(
    *,
    database_url: str,
    user_agent: str,
    load_records: Callable[[], list[dict[str, Any]]],
    limit: int,
    force: bool = False,
) -> None:
    if state["running"]:
        return
    state.update(
        running=True, startedAt=_now(), finishedAt=None, target=0, processed=0, failed=0,
        officialWebsitesFound=0, b2cMatches=0, lastError=None,
    )
    try:
        records = await asyncio.to_thread(load_records)
        enriched = await asyncio.to_thread(store.load_map, database_url)
        targets = select_pending(records, set(enriched), min(max(limit, 1), MAX_BATCH), force)
        state["target"] = len(targets)

        timeout = httpx.Timeout(20.0)
        limits = httpx.Limits(max_connections=6, max_keepalive_connections=2)
        async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
            fetcher = HttpFetcher(client, user_agent)
            wikidata = make_wikidata_lookup(client, user_agent)
            gate = asyncio.Semaphore(CONCURRENCY)

            async def work(record: dict[str, Any]) -> None:
                key = record_key(record)
                if key is None:
                    return
                async with gate:
                    try:
                        data = await asyncio.wait_for(enrich_company(record, fetcher, wikidata), PER_COMPANY_TIMEOUT)
                        data["enrichmentVersion"] = ENRICHMENT_VERSION
                        await asyncio.to_thread(store.save_one, database_url, key, data)
                    except Exception as exc:  # one company must never stop the batch
                        state["failed"] += 1
                        state["lastError"] = f"{type(exc).__name__}: {str(exc)[:160]}"
                        return
                    state["processed"] += 1
                    if data.get("officialWebsite"):
                        state["officialWebsitesFound"] += 1
                    if data.get("b2cWebsite"):
                        state["b2cMatches"] += 1

            await asyncio.gather(*(work(r) for r in targets))
    except Exception as exc:
        state["lastError"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        state.update(running=False, finishedAt=_now())


async def run_queue(*, database_url: str, user_agent: str, max_batches: int = 100) -> None:
    """Drain ready durable queue work in bounded batches; safe to resume after restarts."""
    from . import queue as durable_queue
    if state["running"]:
        return
    state.update(running=True, startedAt=_now(), finishedAt=None, target=0,
                 processed=0, failed=0, officialWebsitesFound=0, b2cMatches=0, lastError=None)
    try:
        timeout = httpx.Timeout(20.0)
        limits = httpx.Limits(max_connections=6, max_keepalive_connections=2)
        async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
            fetcher = HttpFetcher(client, user_agent)
            wikidata = make_wikidata_lookup(client, user_agent)
            gate = asyncio.Semaphore(CONCURRENCY)

            async def work(record: dict[str, Any]) -> None:
                key = record_key(record)
                if key is None:
                    return
                async with gate:
                    try:
                        data = await asyncio.wait_for(enrich_company(record, fetcher, wikidata), PER_COMPANY_TIMEOUT)
                        data["enrichmentVersion"] = ENRICHMENT_VERSION
                        await asyncio.to_thread(store.save_one, database_url, key, data)
                        await asyncio.to_thread(durable_queue.mark_done, database_url, record)
                    except Exception as exc:
                        state["failed"] += 1
                        state["lastError"] = f"{type(exc).__name__}: {str(exc)[:160]}"
                        await asyncio.to_thread(durable_queue.mark_failed, database_url, record,
                                                f"{type(exc).__name__}: {str(exc)[:400]}")
                        return
                    state["processed"] += 1
                    if data.get("officialWebsite"):
                        state["officialWebsitesFound"] += 1
                    if data.get("b2cWebsite"):
                        state["b2cMatches"] += 1

            for _ in range(max(1, min(max_batches, 100))):
                batch = await asyncio.to_thread(durable_queue.claim_batch, database_url, MAX_BATCH)
                if not batch:
                    break
                state["target"] += len(batch)
                await asyncio.gather(*(work(record) for record in batch))
    except Exception as exc:
        state["lastError"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        state.update(running=False, finishedAt=_now())
