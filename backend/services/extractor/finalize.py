"""Accumulator finalization and high-level extract_all entry point."""
from __future__ import annotations

from loguru import logger

from .extract import extract_page
from .highlights import compute_highlights

ALL_CATEGORIES = [
    "emails", "subdomains", "api_keys", "cloud_buckets",
    "analytics_trackers", "endpoints", "social_profiles",
    "technologies", "persons", "phones",
]


def extract_page_safe(
    html: str, url: str, timestamp: str, domain: str, accum: dict,
    categories: set[str] | None = None,
) -> bool:
    """Extract data from a single page, returning True on success."""
    try:
        extract_page(html, url, timestamp, domain, accum, categories=categories)
        return True
    except Exception as exc:
        logger.warning("Extraction error on {}: {}", url, exc)
        return False


def finalize_accum(accum: dict, categories: list[str] | None = None) -> dict:
    """Convert accumulator dicts to sorted result lists.

    If *categories* is provided, only included categories are populated;
    excluded categories return empty lists.
    """

    def _sort_list(items: list[dict]) -> list[dict]:
        return sorted(items, key=lambda x: x["occurrences"], reverse=True)

    def _cat(key: str, items: list[dict]) -> list[dict]:
        if categories is not None and key not in categories:
            return []
        return _sort_list(items)

    return {
        "emails": _cat("emails",
            [{"value": e.pop("value", k), **e} for k, e in accum["emails"].items()]
        ),
        "subdomains": _cat("subdomains",
            [{"value": e.pop("value", k), **e} for k, e in accum["subdomains"].items()]
        ),
        "api_keys": _cat("api_keys",
            [
                {"type": e.pop("type", ""), "value": e.pop("value", k), **e}
                for k, e in accum["api_keys"].items()
            ]
        ),
        "cloud_buckets": _cat("cloud_buckets",
            [{"value": e.pop("value", k), **e} for k, e in accum["cloud_buckets"].items()]
        ),
        "analytics_trackers": _cat("analytics_trackers",
            [
                {"type": e.pop("type", ""), "id": e.pop("id", k), **e}
                for k, e in accum["analytics_trackers"].items()
            ]
        ),
        "endpoints": _cat("endpoints",
            [{"path": e.pop("path", k), **e} for k, e in accum["endpoints"].items()]
        ),
        "social_profiles": _cat("social_profiles",
            [
                {
                    "platform": e.pop("platform", ""),
                    "handle": e.pop("handle", ""),
                    "url": e.pop("url", ""),
                    **e,
                }
                for k, e in accum["social_profiles"].items()
            ]
        ),
        "technologies": _cat("technologies",
            [
                {
                    "technology": e.pop("technology", k),
                    "version": e.pop("version", None),
                    **e,
                }
                for k, e in accum["technologies"].items()
            ]
        ),
        "persons": _cat("persons",
            [
                {"name": e.pop("name", k), "context": e.pop("context", ""), **e}
                for k, e in accum["persons"].items()
            ]
        ),
        "phones": _cat("phones",
            [
                {"raw": e.pop("raw", ""), "normalized": e.pop("normalized", k), **e}
                for k, e in accum["phones"].items()
            ]
        ),
    }


def extract_all(pages: list[dict], domain: str, categories: list[str] | None = None) -> dict:
    accum = {cat: {} for cat in ALL_CATEGORIES}
    cat_set = set(categories) if categories else None

    processed = 0
    for page in pages:
        if page["html"] is None:
            continue
        if extract_page_safe(
            page["html"], page["url"], page["timestamp"], domain, accum,
            categories=cat_set,
        ):
            processed += 1

    logger.info("Extracted data from {} pages for {}", processed, domain)
    return finalize_accum(accum, categories=categories)
