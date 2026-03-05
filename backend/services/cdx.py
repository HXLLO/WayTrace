from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path

import aiohttp
from loguru import logger

from config import settings

CDX_URL = "https://web.archive.org/cdx/search/cdx"

_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cdx"


def _cache_path(domain: str) -> Path:
    safe = domain.replace("/", "_").replace(":", "_")
    return _CACHE_DIR / f"{safe}.json.gz"


def _load_cache(domain: str) -> dict | None:
    p = _cache_path(domain)
    if not p.exists():
        return None
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("CDX cache hit for {} ({} snapshots)", domain, data.get("total_found", 0))
        return data
    except Exception:
        return None


def _save_cache(domain: str, result: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with gzip.open(_cache_path(domain), "wt", encoding="utf-8") as f:
            json.dump(result, f)
        logger.info("CDX cached for {} ({} snapshots)", domain, result.get("total_found", 0))
    except Exception as exc:
        logger.warning("CDX cache write failed: {}", exc)


def _parse_cdx_rows(data: list) -> list[dict]:
    """Parse CDX JSON rows into snapshot dicts."""
    if not data or len(data) < 2:
        return []
    headers = data[0]
    return [
        {
            "timestamp": row[headers.index("timestamp")],
            "url": row[headers.index("original")],
            "status": row[headers.index("statuscode")],
            "mimetype": row[headers.index("mimetype")],
            "digest": row[headers.index("digest")] if "digest" in headers else None,
        }
        for row in data[1:]
    ]


async def fetch_cdx_snapshots(domain: str) -> dict:
    cached = _load_cache(domain)
    if cached is not None:
        return cached

    params = {
        "url": f"{domain}/*",
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype,digest",
        "filter": ["statuscode:200", "mimetype:text/html"],
        "showResumeKey": "true",
    }

    timeout = aiohttp.ClientTimeout(total=120)
    last_error: Exception | None = None
    all_snapshots: list[dict] = []

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(1 + settings.archive_retry_count):
            try:
                async with session.get(CDX_URL, params=params) as resp:
                    if resp.status == 429:
                        wait = 30 * (2 ** attempt)
                        logger.warning(
                            "CDX rate-limited (429), waiting {}s (attempt {}/{})",
                            wait, attempt + 1, 1 + settings.archive_retry_count,
                        )
                        await asyncio.sleep(wait)
                        continue

                    resp.raise_for_status()
                    data = await resp.json(content_type=None)

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                delay = 5 * (2 ** attempt)
                logger.warning(
                    "CDX request failed: {} — retrying in {}s (attempt {}/{})",
                    exc, delay, attempt + 1, 1 + settings.archive_retry_count,
                )
                await asyncio.sleep(delay)
                continue

            if not data or len(data) < 2:
                logger.info("No archived snapshots found for {}", domain)
                return {"snapshots": [], "total_found": 0}

            all_snapshots = _parse_cdx_rows(data)

            # Check for resumeKey for very large domains
            resume_key = None
            if data and isinstance(data[-1], list) and len(data[-1]) == 1:
                possible_key = data[-1][0]
                if isinstance(possible_key, str) and len(possible_key) > 20:
                    resume_key = possible_key
                    all_snapshots = all_snapshots[:-1]

            if resume_key:
                logger.info(
                    "CDX returned {} snapshots with resumeKey, fetching more...",
                    len(all_snapshots),
                )
                extra = await _fetch_cdx_resume(session, domain, resume_key)
                all_snapshots.extend(extra)

            logger.info(
                "CDX returned {} snapshots for {}", len(all_snapshots), domain
            )
            result = {"snapshots": all_snapshots, "total_found": len(all_snapshots)}
            _save_cache(domain, result)
            return result

    reason = str(last_error) if last_error else "rate-limited (429)"
    raise RuntimeError(
        f"CDX API unreachable after {1 + settings.archive_retry_count} attempts: {reason}"
    )


async def _fetch_cdx_resume(
    session: aiohttp.ClientSession, domain: str, resume_key: str,
) -> list[dict]:
    """Fetch all remaining CDX pages by chaining resumeKeys."""
    all_extra: list[dict] = []
    current_key = resume_key
    max_pages = 50

    for page in range(max_pages):
        params = {
            "url": f"{domain}/*",
            "output": "json",
            "fl": "timestamp,original,statuscode,mimetype,digest",
            "filter": ["statuscode:200", "mimetype:text/html"],
            "showResumeKey": "true",
            "resumeKey": current_key,
        }

        try:
            async with session.get(CDX_URL, params=params) as resp:
                if resp.status == 429:
                    wait = 30 * (2 ** min(page, 3))
                    logger.warning("CDX resume rate-limited, waiting {}s", wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status != 200:
                    logger.warning("CDX resume page {} returned {}", page + 1, resp.status)
                    break
                data = await resp.json(content_type=None)
        except Exception as exc:
            logger.warning("CDX resume fetch failed on page {}: {}", page + 1, exc)
            break

        snapshots = _parse_cdx_rows(data)
        if not snapshots:
            break

        # Check if last row is a resumeKey
        next_key = None
        if data and isinstance(data[-1], list) and len(data[-1]) == 1:
            possible_key = data[-1][0]
            if isinstance(possible_key, str) and len(possible_key) > 20:
                next_key = possible_key
                snapshots = snapshots[:-1]

        all_extra.extend(snapshots)
        logger.info(
            "CDX resume page {} returned {} snapshots (total extra: {})",
            page + 1, len(snapshots), len(all_extra),
        )

        if next_key is None:
            break
        current_key = next_key

    return all_extra
