"""Self-host configuration panel API.

GET  /api/config         - effective values + metadata, grouped by pipeline stage
PUT  /api/config         - partial update {key: value}; validates, persists, applies hot
POST /api/config/reset   - {"keys": [...]} drops those overrides ({} drops all)
POST /api/config/restart - re-exec the server so restart-required settings take effect

Every endpoint 404s when config_panel_enabled is off (the hosted service).
"""
import asyncio
import os
import sys

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from config import settings
from services import runtime_config

router = APIRouter()

_GROUPS = (
    ("archive", "Archive.org politeness"),
    ("selection", "Snapshot selection"),
    ("queue", "Scans & queue"),
    ("advanced", "Advanced"),
)


def _guard() -> None:
    if not settings.config_panel_enabled:
        raise HTTPException(status_code=404)


def _describe(key: str, spec: runtime_config.Tunable) -> dict:
    return {
        "key": key,
        "type": spec.type,
        "value": getattr(settings, key),
        "default": runtime_config.boot_value(key),
        "recommended": spec.recommended,
        "min": spec.min,
        "max": spec.max,
        "step": spec.step,
        "unit": spec.unit,
        "restart": spec.restart,
        "risk": spec.risk,
        "infinite_at": spec.infinite_at,
        "choices": list(spec.choices) or None,
        "overridden": key in runtime_config.overrides(),
        "desc": spec.desc,
    }


@router.get("/api/config")
async def get_config():
    _guard()
    groups = []
    for gkey, gtitle in _GROUPS:
        items = [_describe(k, s) for k, s in runtime_config.TUNABLES.items()
                 if s.group == gkey]
        groups.append({"key": gkey, "title": gtitle, "settings": items})
    return {"enabled": True, "groups": groups}


@router.put("/api/config")
async def put_config(request: Request):
    _guard()
    body = await request.json()
    if not isinstance(body, dict) or not body:
        raise HTTPException(status_code=400, detail="expected {key: value}")
    validated: dict[str, object] = {}
    for key, value in body.items():
        try:
            validated[key] = runtime_config.coerce(key, value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    restart = runtime_config.apply(validated)
    await runtime_config.save_overrides(validated)
    return {"applied": sorted(validated), "restart_required": restart}


@router.post("/api/config/reset")
async def reset_config(request: Request):
    _guard()
    body = await request.json()
    keys = body.get("keys") if isinstance(body, dict) else None
    if keys is not None and not isinstance(keys, list):
        raise HTTPException(status_code=400, detail="keys must be a list")
    await runtime_config.reset_keys(keys)
    return {"ok": True}


async def _reexec_soon() -> None:
    # Let the HTTP response flush, then replace this process with a fresh copy
    # of the exact command that started it. os.execv works the same whether the
    # server runs bare (uvicorn), under Docker, or behind a process manager, so
    # the restart is portable and does not depend on the deployment.
    await asyncio.sleep(0.4)
    logger.info("Restarting: re-exec {} {}", sys.executable, sys.argv)
    os.execv(sys.executable, [sys.executable] + sys.argv)


@router.post("/api/config/restart")
async def restart_server():
    """Restart the server so restart-required settings take effect. Self-host
    only (the panel is disabled on the hosted build)."""
    _guard()
    asyncio.get_event_loop().create_task(_reexec_soon())
    return {"restarting": True}
