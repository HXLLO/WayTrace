"""Self-host configuration panel: tunable registry + runtime overlay.

Overrides live in app_state under one JSON blob (``cfg_overrides``), are
re-applied at boot (load_overrides, called from the lifespan), and take effect
hot via setattr on the settings singleton. Two archive.org knobs are frozen at
boot into live objects and get a re-init hook instead (rate governor reset,
global semaphore rebuild); the handful of settings truly frozen at boot
(logging, CORS, middleware, docs) are flagged ``restart``.

Risk zones are advisory only: green below ``orange``, orange below ``red``,
red beyond (direction ``below`` flips the comparison). Red means a real chance
archive.org hard-blocks the host IP; nothing is clamped beyond technical
validity, a self-hosted install answers for its own politeness.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from loguru import logger

from config import settings

_STATE_KEY = "cfg_overrides"


@dataclass(frozen=True)
class Tunable:
    group: str                      # archive | selection | queue | advanced
    type: str                       # int | float | bool | str | choice
    desc: str                       # short English description (frontend i18n)
    recommended: object = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str | None = None         # s, req/min, days, bytes...
    restart: bool = False           # frozen at boot, needs a restart
    hook: str | None = None         # rate_reset | sem_reset
    risk: dict | None = None        # {"direction": "above"|"below", "orange": x, "red": y}
    choices: tuple = field(default_factory=tuple)


TUNABLES: dict[str, Tunable] = {
    # --- archive.org politeness -------------------------------------------
    "archive_rate_per_minute": Tunable(
        "archive", "int", "Starting request rate of the adaptive governor.",
        recommended=75, min=1, max=600, unit="req/min", hook="rate_reset",
        risk={"direction": "above", "orange": 80, "red": 105}),
    "archive_rate_min": Tunable(
        "archive", "int", "Floor the adaptive rate never drops below.",
        recommended=60, min=1, max=600, unit="req/min",
        risk={"direction": "above", "orange": 80, "red": 105}),
    "archive_rate_max": Tunable(
        "archive", "int", "Ceiling the adaptive rate may probe up to.",
        recommended=80, min=1, max=600, unit="req/min",
        risk={"direction": "above", "orange": 80, "red": 105}),
    "archive_rate_step": Tunable(
        "archive", "int", "Additive rate increase after a clean interval.",
        recommended=15, min=1, max=120, unit="req/min"),
    "archive_rate_increase_interval": Tunable(
        "archive", "float", "Seconds of clean responses before a rate bump.",
        recommended=90.0, min=5, max=3600, unit="s",
        risk={"direction": "below", "orange": 30, "red": 10}),
    "archive_rate_decrease_factor": Tunable(
        "archive", "float", "Multiplier applied to the rate on a refusal.",
        recommended=0.5, min=0.05, max=0.95, step=0.05),
    "archive_rate_burst": Tunable(
        "archive", "int", "Token-bucket burst allowance.",
        recommended=6, min=1, max=50, hook="rate_reset",
        risk={"direction": "above", "orange": 12, "red": 25}),
    "archive_global_concurrency": Tunable(
        "archive", "int", "Simultaneous archive.org connections, all scans combined.",
        recommended=3, min=1, max=50, hook="sem_reset",
        risk={"direction": "above", "orange": 6, "red": 12}),
    "max_concurrent_scrapes": Tunable(
        "archive", "int", "Parallel downloads within a single scan.",
        recommended=4, min=1, max=50,
        risk={"direction": "above", "orange": 8, "red": 16}),
    "scrape_delay_min": Tunable(
        "archive", "float", "Low bound of the per-request jitter delay.",
        recommended=0.5, min=0.0, max=10.0, step=0.05, unit="s",
        risk={"direction": "below", "orange": 0.25, "red": 0.1}),
    "scrape_delay_max": Tunable(
        "archive", "float", "High bound of the per-request jitter delay.",
        recommended=1.2, min=0.0, max=15.0, step=0.05, unit="s",
        risk={"direction": "below", "orange": 0.5, "red": 0.2}),
    "archive_request_timeout": Tunable(
        "archive", "int", "Timeout of a single archive.org request.",
        recommended=60, min=5, max=120, unit="s"),
    "archive_retry_count": Tunable(
        "archive", "int", "Retries on a failed CDX index request.",
        recommended=3, min=0, max=10),
    "scrape_max_retries": Tunable(
        "archive", "int", "Retries on a failed page download.",
        recommended=3, min=0, max=10),
    "archive_hard_cooldown_base": Tunable(
        "archive", "int", "First pause after archive.org refuses connections.",
        recommended=120, min=10, max=3600, unit="s",
        risk={"direction": "below", "orange": 60, "red": 30}),
    "archive_hard_cooldown_max": Tunable(
        "archive", "int", "Ceiling of the escalating refusal pause.",
        recommended=1800, min=60, max=7200, unit="s"),
    "archive_hard_streak_reset": Tunable(
        "archive", "int", "Quiet gap that resets the refusal escalation.",
        recommended=900, min=60, max=7200, unit="s"),
    # --- snapshot selection ------------------------------------------------
    "hosted_snapshot_ceiling": Tunable(
        "selection", "int", "Hard cap on snapshots per scan. 0 removes the cap and scans the domain in full.",
        recommended=0, min=0, max=100000),
    "snapshot_cap_multiplier": Tunable(
        "selection", "float", "Scales the adaptive snapshot cap before depth presets. Above 1.0 scans fetch more pages and take longer.",
        recommended=1.0, min=0.1, max=50.0, step=0.1,
        risk={"direction": "above", "orange": 3, "red": 10}),
    # --- scans & queue -----------------------------------------------------
    "max_active_total": Tunable(
        "queue", "int", "Scans running at the same time; the rest wait in queue.",
        recommended=1, min=1, max=10,
        risk={"direction": "above", "orange": 2, "red": 4}),
    "max_queue_total": Tunable(
        "queue", "int", "Hard cap on running plus waiting scans.",
        recommended=100, min=1, max=1000),
    "max_active_per_ip": Tunable(
        "queue", "int", "In-flight scans allowed per client IP.",
        recommended=2, min=1, max=100),
    "scan_timeout_seconds": Tunable(
        "queue", "int", "Hard wall-clock limit of a single scan.",
        recommended=3600, min=60, max=86400, unit="s"),
    "scrape_budget_seconds": Tunable(
        "queue", "int", "Download-phase budget; past it the scan analyzes what it already has. 0 disables the budget.",
        recommended=0, min=0, max=86400, unit="s"),
    "scan_retention_days": Tunable(
        "queue", "int", "How long finished scans are kept and reused.",
        recommended=14, min=1, max=365, unit="days"),
    "cleanup_interval_seconds": Tunable(
        "queue", "int", "Pause between expired-scan cleanup passes.",
        recommended=3600, min=60, max=86400, unit="s"),
    # --- advanced ----------------------------------------------------------
    "example_scan_domain": Tunable(
        "advanced", "str", "Domain whose scan is kept forever as the homepage example. Empty disables it."),
    "trust_cloudflare": Tunable(
        "advanced", "bool", "Trust Cloudflare headers for the client IP. Only behind Cloudflare.",
        recommended=False),
    "expose_api_docs": Tunable(
        "advanced", "bool", "Serve the interactive Swagger docs at /docs.",
        recommended=False, restart=True),
    "log_level": Tunable(
        "advanced", "choice", "Verbosity of the server logs.",
        recommended="INFO", restart=True,
        choices=("DEBUG", "INFO", "WARNING", "ERROR")),
    "cors_origins": Tunable(
        "advanced", "str", "Comma-separated origins allowed to call the API.",
        restart=True),
    "max_request_body_bytes": Tunable(
        "advanced", "int", "Largest accepted request body.",
        recommended=2_000_000, min=100_000, max=50_000_000, unit="bytes",
        restart=True),
}

# Boot values, captured before any override lands: what "reset" returns to.
_boot_values: dict[str, object] = {}
_overrides: dict[str, object] = {}


def _ensure_boot_snapshot() -> None:
    if not _boot_values:
        for key in TUNABLES:
            _boot_values[key] = getattr(settings, key)


def boot_value(key: str):
    _ensure_boot_snapshot()
    return _boot_values[key]


def overrides() -> dict[str, object]:
    return dict(_overrides)


def coerce(key: str, value) -> object:
    """Validate `value` for `key` against the registry. Raises ValueError."""
    spec = TUNABLES.get(key)
    if spec is None:
        raise ValueError(f"unknown setting: {key}")
    if spec.type == "bool":
        if isinstance(value, bool):
            return value
        raise ValueError(f"{key}: expected a boolean")
    if spec.type in ("int", "float"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key}: expected a number")
        out = int(value) if spec.type == "int" else float(value)
        if spec.type == "int" and float(value) != out:
            raise ValueError(f"{key}: expected an integer")
        if spec.min is not None and out < spec.min:
            raise ValueError(f"{key}: below technical minimum {spec.min}")
        if spec.max is not None and out > spec.max:
            raise ValueError(f"{key}: above technical maximum {spec.max}")
        return out
    if spec.type == "choice":
        if not isinstance(value, str) or value not in spec.choices:
            raise ValueError(f"{key}: must be one of {', '.join(spec.choices)}")
        return value
    if spec.type == "str":
        if not isinstance(value, str):
            raise ValueError(f"{key}: expected a string")
        return value.strip()
    raise ValueError(f"{key}: unsupported type")


def _run_hooks(hooks: set[str]) -> None:
    if "rate_reset" in hooks:
        from services import archive_rate
        archive_rate.reset()
    if "sem_reset" in hooks:
        from services import scraper
        scraper.reset_global_semaphore()


def apply(values: dict[str, object]) -> list[str]:
    """setattr validated values onto settings, run re-init hooks.

    Returns the keys that still need a restart to take effect.
    """
    _ensure_boot_snapshot()
    hooks: set[str] = set()
    restart: list[str] = []
    for key, value in values.items():
        setattr(settings, key, value)
        spec = TUNABLES[key]
        if spec.hook:
            hooks.add(spec.hook)
        if spec.restart:
            restart.append(key)
    _run_hooks(hooks)
    return restart


async def save_overrides(values: dict[str, object]) -> None:
    from db import set_app_state
    _overrides.update(values)
    await set_app_state(_STATE_KEY, json.dumps(_overrides))


async def reset_keys(keys: list[str] | None) -> None:
    """Drop overrides (all when keys is falsy) and restore boot values."""
    from db import set_app_state
    _ensure_boot_snapshot()
    targets = list(_overrides) if not keys else [k for k in keys if k in TUNABLES]
    restore = {}
    for key in targets:
        _overrides.pop(key, None)
        restore[key] = _boot_values[key]
    if restore:
        apply(restore)
    await set_app_state(_STATE_KEY, json.dumps(_overrides))


async def load_overrides() -> None:
    """Boot: snapshot defaults, then re-apply persisted overrides."""
    from db import get_app_state
    _ensure_boot_snapshot()
    raw = await get_app_state(_STATE_KEY)
    if not raw:
        return
    try:
        stored = json.loads(raw)
    except ValueError:
        logger.warning("cfg_overrides: unreadable JSON, ignoring")
        return
    valid: dict[str, object] = {}
    for key, value in stored.items():
        try:
            valid[key] = coerce(key, value)
        except ValueError as exc:
            logger.warning(f"cfg_overrides: dropping {key}: {exc}")
    _overrides.clear()
    _overrides.update(valid)
    if valid:
        apply(valid)
        logger.info(f"config overrides applied: {', '.join(sorted(valid))}")


def reset_state_for_tests() -> None:
    _overrides.clear()
    _boot_values.clear()
