from __future__ import annotations

import asyncio
import random

import aiohttp
from loguru import logger

from config import settings
from store import store

WAYBACK_URL = "https://web.archive.org/web/{timestamp}id_/{url}"


async def scrape_snapshots(
    snapshots: list[dict], job_id: str
) -> list[dict]:
    semaphore = asyncio.Semaphore(settings.max_concurrent_scrapes)
    timeout = aiohttp.ClientTimeout(total=settings.archive_request_timeout)
    connector = aiohttp.TCPConnector(
        limit=settings.max_concurrent_scrapes + 10,
        limit_per_host=settings.max_concurrent_scrapes,
        keepalive_timeout=60,
    )
    total = len(snapshots)
    completed = 0
    update_every = max(1, total // 50)  # ~50 progress updates for big scans

    # Adaptive delay: starts low, increases on 429s, decreases on success streaks
    _delay_state = {"min": settings.scrape_delay_min, "max": settings.scrape_delay_max}
    _rate_limit_hits = {"count": 0}

    async def fetch_one(
        session: aiohttp.ClientSession, snap: dict
    ) -> dict:
        nonlocal completed
        url = WAYBACK_URL.format(
            timestamp=snap["timestamp"], url=snap["url"]
        )
        result = None

        async with semaphore:
            for attempt in range(1 + settings.scrape_max_retries):
                try:
                    async with session.get(url) as resp:
                        if resp.status == 429:
                            _rate_limit_hits["count"] += 1
                            # Adaptive backoff: scale with how many 429s we've seen
                            base_wait = min(5 * (attempt + 1), 30)
                            extra = min(_rate_limit_hits["count"] * 2, 60)
                            wait = base_wait + extra
                            logger.warning(
                                "Rate-limited (429) on {}, waiting {}s (attempt {}/{}, total 429s: {})",
                                snap["url"], wait, attempt + 1,
                                1 + settings.scrape_max_retries,
                                _rate_limit_hits["count"],
                            )
                            # Temporarily increase delays for all tasks
                            _delay_state["min"] = min(_delay_state["min"] * 2, 1.0)
                            _delay_state["max"] = min(_delay_state["max"] * 2, 2.0)
                            await asyncio.sleep(wait)
                            continue
                        if resp.status in (404, 410):
                            result = {"timestamp": snap["timestamp"], "url": snap["url"], "html": None}
                            break
                        if resp.status >= 500:
                            if attempt < settings.scrape_max_retries:
                                await asyncio.sleep(3 * (attempt + 1))
                                continue
                            result = {"timestamp": snap["timestamp"], "url": snap["url"], "html": None}
                            break
                        if resp.status >= 400:
                            result = {"timestamp": snap["timestamp"], "url": snap["url"], "html": None}
                            break
                        html = await resp.text(errors="replace")
                        result = {"timestamp": snap["timestamp"], "url": snap["url"], "html": html}
                        # Gradually recover delays on success
                        if _delay_state["min"] > settings.scrape_delay_min:
                            _delay_state["min"] = max(
                                settings.scrape_delay_min,
                                _delay_state["min"] * 0.95,
                            )
                            _delay_state["max"] = max(
                                settings.scrape_delay_max,
                                _delay_state["max"] * 0.95,
                            )
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    logger.debug(
                        "Scrape failed for {} (attempt {}/{}): {}",
                        url, attempt + 1, 1 + settings.scrape_max_retries, exc,
                    )
                    if attempt < settings.scrape_max_retries:
                        await asyncio.sleep(3 * (attempt + 1))
                        continue
                    result = {"timestamp": snap["timestamp"], "url": snap["url"], "html": None}

            if result is None:
                result = {"timestamp": snap["timestamp"], "url": snap["url"], "html": None}

        # Progress + delay OUTSIDE semaphore — slot freed for next task
        completed += 1
        if completed % update_every == 0 or completed == total:
            progress = 15 + int((completed / total) * 60)
            await store.update_job(
                job_id, progress=progress, step=f"Scraping page {completed}/{total}"
            )

        await asyncio.sleep(
            random.uniform(_delay_state["min"], _delay_state["max"])
        )

        return result

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tasks = [fetch_one(session, snap) for snap in snapshots]
        results = await asyncio.gather(*tasks)

    success = sum(1 for r in results if r["html"] is not None)
    logger.info(
        "Scraped {}/{} pages successfully (429 hits: {})",
        success, total, _rate_limit_hits["count"],
    )
    return list(results)
