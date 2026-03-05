from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from config import settings


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self.total_scans_run: int = 0
        self._cleanup_task: asyncio.Task | None = None

    async def start_cleanup_loop(self) -> None:
        self._cleanup_task = asyncio.create_task(self._cleanup_expired())

    async def stop_cleanup_loop(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_expired(self) -> None:
        while True:
            await asyncio.sleep(600)
            now = datetime.now(timezone.utc)
            async with self._lock:
                expired = [
                    jid
                    for jid, job in self._jobs.items()
                    if (now - job["updated_at"]).total_seconds()
                    > settings.job_ttl_seconds
                ]
                for jid in expired:
                    del self._jobs[jid]

    async def create_job(self, domain: str) -> str:
        async with self._lock:
            for job in self._jobs.values():
                if job["domain"] == domain and job["status"] in (
                    "queued",
                    "running",
                ):
                    return job["id"]

            active = sum(
                1
                for j in self._jobs.values()
                if j["status"] in ("queued", "running")
            )
            if active >= settings.max_active_jobs:
                raise RuntimeError("Too many active jobs")

            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            self._jobs[job_id] = {
                "id": job_id,
                "domain": domain,
                "status": "queued",
                "progress": 0,
                "step": "Queued...",
                "created_at": now,
                "updated_at": now,
                "meta": None,
                "results": None,
            }
            self.total_scans_run += 1
            return job_id

    async def get_job(self, job_id: str) -> dict | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update_job(self, job_id: str, **fields) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                if key in job:
                    job[key] = value
            job["updated_at"] = datetime.now(timezone.utc)

    async def active_count(self) -> int:
        async with self._lock:
            return sum(
                1
                for j in self._jobs.values()
                if j["status"] in ("queued", "running")
            )


store = JobStore()
