"""Shared helper functions for the extractor."""
from __future__ import annotations

import re

from .patterns import EMAIL_EXCLUDE, IMAGE_EXTENSIONS, WAYBACK_TOOLBAR_RE, WAYBACK_SCRIPT_RE, WAYBACK_DIV_RE


def ts_to_month(timestamp: str) -> str:
    return f"{timestamp[:4]}-{timestamp[4:6]}"


def update_entity(
    store: dict, key: str, month: str, extra: dict | None = None
) -> None:
    if key in store:
        entry = store[key]
        entry["occurrences"] += 1
        if month < entry["first_seen"]:
            entry["first_seen"] = month
        if month > entry["last_seen"]:
            entry["last_seen"] = month
    else:
        entry = {
            "first_seen": month,
            "last_seen": month,
            "occurrences": 1,
        }
        if extra:
            entry.update(extra)
        store[key] = entry


def is_email_excluded(email: str) -> bool:
    local = email.split("@")[0].lower()
    if any(exc in local for exc in EMAIL_EXCLUDE):
        return True
    if email.lower() == "example@example.com":
        return True
    for ext in IMAGE_EXTENSIONS:
        if email.endswith(ext):
            return True
    return False


def normalize_phone(raw: str) -> str:
    return re.sub(r"[^\d+]", "", raw)


def strip_wayback_artifacts(html: str) -> str:
    """Remove Wayback Machine injected toolbar, scripts, and divs."""
    html = WAYBACK_TOOLBAR_RE.sub("", html)
    html = WAYBACK_SCRIPT_RE.sub("", html)
    html = WAYBACK_DIV_RE.sub("", html)
    return html


def is_wayback_comment(text: str) -> bool:
    """Check if an HTML comment is a Wayback Machine artifact."""
    lower = text.lower().strip()
    return any(kw in lower for kw in (
        "wayback", "toolbar", "wm-ipp", "begin wayback", "end wayback",
        "_static/", "archive.org",
    ))
