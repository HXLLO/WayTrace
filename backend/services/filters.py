from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from loguru import logger

if TYPE_CHECKING:
    from models import ScanConfig

# Paths with high OSINT value — diverse content likely
HIGH_PRIORITY_KEYWORDS = {
    "contact", "about", "team", "staff", "people", "privacy", "terms",
    "careers", "legal", "imprint", "impressum", "login", "admin", "blog",
    "jobs", "press", "partners", "investors", "security",
}

# Depth preset multipliers
DEPTH_PRESETS = {
    "quick": {"cap_mult": 0.15, "min_cap": 200},
    "standard": {"cap_mult": 1.0, "min_cap": 1},
    "full": {"cap_mult": 2.0, "max_cap": 30000},
}


def _compute_cap(unique_paths: int, html_count: int = 0) -> int:
    """Adaptive cap based on unique paths and available HTML snapshots.

    The goal is to scrape as many snapshots as possible for maximum
    temporal coverage and OSINT data extraction.
    """
    if unique_paths <= 30:
        # Small site — scan everything available
        base = html_count
    elif unique_paths <= 200:
        # Medium site — ~15 snapshots per path
        base = min(unique_paths * 15, 10000)
    elif unique_paths <= 1000:
        # Large site — generous coverage
        base = min(unique_paths * 8, 15000)
    else:
        # Very large — cap at 15000
        base = 15000

    # Never go below a reasonable minimum
    return max(base, min(html_count, 100))


def _normalize_path(url: str) -> str:
    """Extract and normalize the URL path."""
    try:
        parsed = urlparse(url)
        path = (parsed.path or "/").rstrip("/").lower() or "/"
        return path
    except Exception:
        return "/"


def _score_path(path: str) -> int:
    """Score a path by OSINT value. Higher = more interesting."""
    path_lower = path.lower()
    for kw in HIGH_PRIORITY_KEYWORDS:
        if kw in path_lower:
            return 3  # high
    if path == "/":
        return 2  # medium (homepage)
    return 1  # low


def _apply_date_filter(snapshots: list[dict], config: ScanConfig | None) -> list[dict]:
    """Filter snapshots by date_from/date_to from config."""
    if config is None:
        return snapshots
    filtered = snapshots
    if config.date_from:
        # date_from is "YYYY-MM", timestamp is "YYYYMMDDhhmmss"
        from_ts = config.date_from.replace("-", "") + "01000000"
        filtered = [s for s in filtered if s["timestamp"] >= from_ts]
    if config.date_to:
        # date_to is "YYYY-MM", include the full month
        to_ts = config.date_to.replace("-", "") + "31235959"
        filtered = [s for s in filtered if s["timestamp"] <= to_ts]
    return filtered


def _apply_depth_to_cap(cap: int, config: ScanConfig | None) -> int:
    """Apply depth preset multiplier to cap."""
    if config is None:
        return cap
    preset = DEPTH_PRESETS.get(config.depth, DEPTH_PRESETS["standard"])
    adjusted = int(cap * preset["cap_mult"])
    if "min_cap" in preset:
        adjusted = max(adjusted, preset["min_cap"])
    if "max_cap" in preset:
        adjusted = min(adjusted, preset["max_cap"])
    return adjusted


def filter_snapshots(snapshots: list[dict], config: ScanConfig | None = None) -> dict:
    html_only = [s for s in snapshots if s.get("mimetype") == "text/html"]

    # Apply date filtering before anything else
    html_only = _apply_date_filter(html_only, config)

    if not html_only:
        return {
            "selected": [],
            "total_snapshots_found": len(snapshots),
            "snapshots_selected": 0,
            "pages_deduped": 0,
            "date_first_seen": None,
            "date_last_seen": None,
        }

    html_only.sort(key=lambda s: s["timestamp"])

    first = html_only[0]
    last = html_only[-1]

    selected = list(html_only)
    dedup_saved = 0

    smart_dedup = (config is None) or config.smart_dedup
    if smart_dedup:
        seen_content: dict[tuple, None] = {}
        deduped: list[dict] = []
        for snap in selected:
            digest = snap.get("digest")
            if digest:
                path = _normalize_path(snap["url"])
                key = (path, digest)
                if key in seen_content:
                    continue
                seen_content[key] = None
            deduped.append(snap)
        dedup_saved = len(selected) - len(deduped)
        selected = deduped

    cap = None
    if config and config.cap is not None:
        cap = config.cap
    elif config and config.depth == "quick":
        cap = 500

    if cap is not None and len(selected) > cap:
        selected = selected[:cap]

    if dedup_saved > 0:
        logger.info(
            "Content dedup removed {} duplicate snapshots ({} → {})",
            dedup_saved,
            dedup_saved + len(selected),
            len(selected),
        )

    date_first = f"{first['timestamp'][:4]}-{first['timestamp'][4:6]}"
    date_last = f"{last['timestamp'][:4]}-{last['timestamp'][4:6]}"

    unique_paths = len({_normalize_path(s["url"]) for s in html_only})
    logger.info(
        "Filtered {} HTML snapshots down to {} across {} unique paths (range: {} to {})",
        len(html_only),
        len(selected),
        unique_paths,
        date_first,
        date_last,
    )

    return {
        "selected": selected,
        "total_snapshots_found": len(snapshots),
        "snapshots_selected": len(selected),
        "pages_deduped": dedup_saved,
        "date_first_seen": date_first,
        "date_last_seen": date_last,
    }
