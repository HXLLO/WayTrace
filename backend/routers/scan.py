from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from config import settings
from models import (
    DateRange,
    JobCreate,
    JobResponse,
    JobStatus,
    PathGroup,
    PreflightResponse,
    ScanConfig,
    SnapshotDetail,
)
from services.cdx import fetch_cdx_snapshots
from services.extractor import ALL_CATEGORIES, extract_all, compute_highlights
from services.filters import filter_snapshots, _compute_cap, _normalize_path, _score_path
from services.scraper import scrape_snapshots
from store import store

router = APIRouter(prefix="/api", tags=["scan"])


# ---------------------------------------------------------------------------
# Scan pipeline (sequential: CDX → filter → scrape → extract)
# ---------------------------------------------------------------------------

async def run_scan(
    job_id: str,
    config: ScanConfig | None = None,
    selected_snapshots: list[dict] | None = None,
) -> None:
    """Main scan pipeline with timeout protection."""
    await store.update_job(job_id, status="running", step="Starting scan...")
    logger.info("Scan started for job {}", job_id)

    job = await store.get_job(job_id)
    if job is None:
        return

    domain = job["domain"]
    start = time.time()

    try:
        await asyncio.wait_for(
            _scan_pipeline(job_id, domain, start, config, selected_snapshots),
            timeout=settings.scan_timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning("Job {} timed out after {}s", job_id, settings.scan_timeout_seconds)
        await store.update_job(
            job_id,
            status="failed",
            step=f"Timed out after {settings.scan_timeout_seconds // 60}min",
        )
    except Exception as exc:
        logger.error("Scan failed for job {}: {}", job_id, exc)
        await store.update_job(
            job_id,
            status="failed",
            step=f"Error: {exc}",
        )


async def _scan_pipeline(
    job_id: str, domain: str, start: float,
    config: ScanConfig | None = None,
    selected_snapshots: list[dict] | None = None,
) -> None:
    empty_results = {cat: [] for cat in ALL_CATEGORIES}
    categories = config.categories if config else None

    try:
        pages_deduped = 0
        if selected_snapshots:
            # Advanced mode: user-selected snapshots — skip CDX + filter
            await store.update_job(
                job_id, step="Using selected snapshots...", progress=10
            )
            snap_list = [{"timestamp": s["timestamp"], "url": s["url"]} for s in selected_snapshots]
            total_found = len(snap_list)
            selected = snap_list
            date_first = f"{snap_list[0]['timestamp'][:4]}-{snap_list[0]['timestamp'][4:6]}" if snap_list else None
            date_last = f"{snap_list[-1]['timestamp'][:4]}-{snap_list[-1]['timestamp'][4:6]}" if snap_list else None
        else:
            # Phase 1: CDX fetch
            await store.update_job(
                job_id, step="Fetching snapshots from CDX API...", progress=5
            )
            cdx_result = await fetch_cdx_snapshots(domain)

            # Phase 2: Filtering
            await store.update_job(
                job_id, step="Selecting diverse snapshots...", progress=10
            )
            filtered = filter_snapshots(cdx_result["snapshots"], config)

            if not filtered["selected"]:
                await store.update_job(
                    job_id,
                    status="completed",
                    progress=100,
                    step="No HTML snapshots found",
                    meta={
                        "domain": domain,
                        "total_snapshots_found": cdx_result["total_found"],
                        "snapshots_analyzed": 0,
                        "pages_scraped": 0,
                        "pages_failed": 0,
                        "pages_deduped": 0,
                        "date_first_seen": None,
                        "date_last_seen": None,
                        "scan_duration_seconds": round(time.time() - start, 1),
                    },
                    results=empty_results,
                )
                return

            total_found = cdx_result["total_found"]
            selected = filtered["selected"]
            date_first = filtered["date_first_seen"]
            date_last = filtered["date_last_seen"]
            pages_deduped = filtered.get("pages_deduped", 0)

        # Phase 3: Scraping
        await store.update_job(
            job_id,
            step=f"Scraping {len(selected)} archived pages...",
            progress=15,
        )
        pages = await scrape_snapshots(selected, job_id)

        pages_scraped = sum(1 for p in pages if p["html"] is not None)
        pages_failed = len(pages) - pages_scraped

        # Phase 4: Extraction
        await store.update_job(
            job_id, step="Extracting OSINT data...", progress=75
        )

        results = extract_all(pages, domain, categories=categories)
        results["highlights"] = compute_highlights(results, domain)

        duration = round(time.time() - start, 1)
        meta = {
            "domain": domain,
            "total_snapshots_found": total_found,
            "snapshots_analyzed": len(selected),
            "pages_scraped": pages_scraped,
            "pages_failed": pages_failed,
            "pages_deduped": pages_deduped,
            "date_first_seen": date_first,
            "date_last_seen": date_last,
            "scan_duration_seconds": duration,
        }

        await store.update_job(
            job_id,
            status="completed",
            progress=100,
            step="Scan complete",
            meta=meta,
            results=results,
        )
        logger.info("Scan completed for job {} in {}s", job_id, duration)

    except Exception as exc:
        logger.error("Scan pipeline error for job {}: {}", job_id, exc)
        raise


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

@router.post("/scan/preflight", response_model=PreflightResponse)
async def scan_preflight(body: JobCreate):
    """Lightweight CDX fetch to return domain stats and suggested config."""
    try:
        cdx_result = await fetch_cdx_snapshots(body.domain)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Archive.org unavailable: {exc}")

    snapshots = cdx_result["snapshots"]

    html_snaps = [s for s in snapshots if s.get("mimetype") == "text/html"]
    html_snaps.sort(key=lambda s: s["timestamp"])

    unique_paths: set[str] = set()
    unique_content: set[tuple[str, str]] = set()
    by_path: dict[str, list[dict]] = {}
    for snap in html_snaps:
        path = _normalize_path(snap["url"])
        unique_paths.add(path)
        digest = snap.get("digest")
        if digest:
            unique_content.add((path, digest))
        by_path.setdefault(path, []).append(snap)

    if html_snaps:
        first_ts = html_snaps[0]["timestamp"]
        last_ts = html_snaps[-1]["timestamp"]
        date_first = f"{first_ts[:4]}-{first_ts[4:6]}"
        date_last = f"{last_ts[:4]}-{last_ts[4:6]}"
    else:
        date_first = None
        date_last = None

    suggested_cap = _compute_cap(len(unique_paths), len(html_snaps))

    # Build path groups for Advanced mode
    path_groups: list[PathGroup] = []
    for path, snaps in by_path.items():
        snaps.sort(key=lambda s: s["timestamp"])
        path_groups.append(PathGroup(
            path=path,
            score=_score_path(path),
            count=len(snaps),
            first=snaps[0]["timestamp"],
            last=snaps[-1]["timestamp"],
            snapshots=[
                SnapshotDetail(
                    timestamp=s["timestamp"],
                    url=s["url"],
                    digest=s.get("digest"),
                )
                for s in snaps
            ],
        ))
    path_groups.sort(key=lambda g: (-g.score, g.path))

    return PreflightResponse(
        domain=body.domain,
        total_snapshots=len(snapshots),
        html_snapshots=len(html_snaps),
        unique_paths=len(unique_paths),
        unique_content=len(unique_content) if unique_content else len(html_snaps),
        date_range=DateRange(first=date_first, last=date_last),
        suggested_config=ScanConfig(cap=suggested_cap),
        path_groups=path_groups,
    )


# ---------------------------------------------------------------------------
# Scan CRUD
# ---------------------------------------------------------------------------

@router.post("/scan", response_model=JobResponse)
async def create_scan(body: JobCreate):
    # Validate categories if provided
    if body.config and body.config.categories is not None:
        invalid = [c for c in body.config.categories if c not in ALL_CATEGORIES]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid categories: {', '.join(invalid)}",
            )

    try:
        job_id = await store.create_job(body.domain)
    except RuntimeError:
        raise HTTPException(
            status_code=429,
            detail="Too many active jobs. Please wait and try again.",
        )

    # Convert selected_snapshots to plain dicts for the pipeline
    sel_snaps = None
    if body.selected_snapshots:
        sel_snaps = [{"timestamp": s.timestamp, "url": s.url} for s in body.selected_snapshots]

    job = await store.get_job(job_id)
    if job and job["status"] == "queued":
        asyncio.create_task(run_scan(job_id, body.config, selected_snapshots=sel_snaps))

    return JobResponse(job_id=job_id)


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    job = await store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return JobStatus(**job)


# ---------------------------------------------------------------------------
# SSE streaming
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}/stream")
async def stream_job_status(job_id: str, request: Request):
    """SSE endpoint for real-time job progress updates."""
    job = await store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    last_event_id = int(request.headers.get("last-event-id", "0"))

    async def event_generator():
        event_id = last_event_id
        last_progress = -1
        last_step = ""
        heartbeat_interval = 15
        last_heartbeat = time.time()

        while True:
            if await request.is_disconnected():
                return

            job = await store.get_job(job_id)
            if job is None:
                event_id += 1
                yield f"id: {event_id}\nevent: expired\ndata: {json.dumps({'status': 'expired'})}\n\n"
                return

            progress = job.get("progress", 0)
            step = job.get("step", "")
            status = job.get("status", "queued")

            if progress != last_progress or step != last_step:
                event_id += 1
                event_data = {
                    "status": status,
                    "progress": progress,
                    "step": step,
                }
                event_type = "progress"
                if status == "completed":
                    event_type = "complete"
                    event_data["meta"] = job.get("meta")
                    event_data["results"] = job.get("results")
                elif status == "failed":
                    event_type = "error"

                yield f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(event_data)}\n\n"
                last_progress = progress
                last_step = step
                last_heartbeat = time.time()

            if status in ("completed", "failed"):
                return

            now = time.time()
            if now - last_heartbeat >= heartbeat_interval:
                yield ": heartbeat\n\n"
                last_heartbeat = now

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
