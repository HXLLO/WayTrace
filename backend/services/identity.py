"""Per-instance identity for honest archive.org attribution.

Every self-hosted instance gets its own stable, random short id (persisted in
app_state, generated once on first access) folded into the User-Agent, so
archive.org sees distinct polite clients rather than one aggregate "WayTrace"
identity for the whole project. This is attribution, NOT evasion: the UA still
says it is WayTrace, the id never rotates, and an optional operator contact lets
archive.org reach the person running the instance. The real anti-block mechanism
stays the adaptive politeness governor (services/archive_rate.py).
"""
from __future__ import annotations

import asyncio
import re
import secrets

from config import APP_VERSION, settings

_STATE_KEY = "instance_id"
_PROJECT_URL = "https://github.com/thomashousset/WayTrace"
# Anything not printable-ASCII (CR/LF, control chars) is dropped from the
# operator contact before it enters the User-Agent, so a stray newline can
# never break the header (aiohttp would reject it) or the UA string.
_UA_UNSAFE = re.compile(r"[^\x20-\x7e]")

_instance_id: str | None = None
_ua_cache: str | None = None
_id_lock = asyncio.Lock()


async def get_instance_id() -> str:
    """Stable per-instance token (6 hex chars). Generated once, then persisted
    in app_state and cached in memory; never rotates. A DB failure degrades to
    an ephemeral in-memory id rather than failing the caller's request (the UA
    is on the archive.org hot path and must never raise)."""
    global _instance_id
    if _instance_id is not None:
        return _instance_id
    async with _id_lock:
        if _instance_id is not None:   # another coroutine won the race
            return _instance_id
        try:
            from db import get_app_state, set_app_state
            stored = await get_app_state(_STATE_KEY)
            if stored:
                _instance_id = stored.strip()
            else:
                _instance_id = secrets.token_hex(3)
                await set_app_state(_STATE_KEY, _instance_id)
        except Exception:
            # Persist failed: use a process-lifetime id so requests still go out.
            if _instance_id is None:
                _instance_id = secrets.token_hex(3)
    return _instance_id


def build_user_agent(version: str, contact: str, instance_id: str) -> str:
    """Assemble the honest per-instance UA. `contact` empty falls back to the
    project URL so archive.org always has a way to attribute and reach us."""
    clean = _UA_UNSAFE.sub("", contact.strip()) if contact else ""
    attribution = f"+{clean}" if clean else f"+{_PROJECT_URL}"
    return f"WayTrace/{version} ({attribution}; id:{instance_id})"


async def current_user_agent() -> str:
    """The UA header value for the next archive.org request. Cached; the cache
    is dropped when operator_contact changes (runtime_config ua_reset hook)."""
    global _ua_cache
    if _ua_cache is not None:
        return _ua_cache
    _ua_cache = build_user_agent(
        APP_VERSION, getattr(settings, "operator_contact", ""), await get_instance_id()
    )
    return _ua_cache


def reset_ua_cache() -> None:
    """Drop the assembled-UA cache so the next request rebuilds it (called when
    operator_contact is changed at runtime)."""
    global _ua_cache
    _ua_cache = None


def reset_state_for_tests() -> None:
    global _instance_id, _ua_cache
    _instance_id = None
    _ua_cache = None
