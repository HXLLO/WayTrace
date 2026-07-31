"""Self-host configuration panel: registry, API, persistence, hot apply.

The panel exposes live Settings fields with technical bounds, recommended
values and risk zones. Overrides persist in app_state (one JSON blob under
``cfg_overrides``), survive a restart via load_overrides(), and apply hot via
setattr on the settings singleton (plus re-init hooks for the two boot-frozen
archive.org knobs). The hosted service ships with the panel disabled.
"""
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import db as dbmod
from config import settings
from services import archive_rate, runtime_config


@pytest_asyncio.fixture(autouse=True)
async def _reset(tmp_path):
    await dbmod.init_db(str(tmp_path / "t.db"))
    saved = {k: getattr(settings, k) for k in runtime_config.TUNABLES}
    saved_panel = settings.config_panel_enabled
    settings.config_panel_enabled = True
    runtime_config.reset_state_for_tests()
    yield
    for k, v in saved.items():
        setattr(settings, k, v)
    settings.config_panel_enabled = saved_panel
    runtime_config.reset_state_for_tests()
    archive_rate.reset()


@pytest_asyncio.fixture()
async def client():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def test_registry_matches_settings_fields():
    for key, spec in runtime_config.TUNABLES.items():
        assert hasattr(settings, key), f"unknown settings field: {key}"
        assert spec.group in {"archive", "selection", "queue", "advanced"}
        if spec.type in {"int", "float"}:
            assert spec.min is not None and spec.max is not None
            assert spec.min <= spec.recommended <= spec.max


@pytest.mark.asyncio
async def test_get_config_lists_effective_values(client):
    r = await client.get("/api/config")
    assert r.status_code == 200
    d = r.json()
    assert d["enabled"] is True
    flat = {s["key"]: s for g in d["groups"] for s in g["settings"]}
    assert flat["max_concurrent_scrapes"]["value"] == settings.max_concurrent_scrapes
    assert flat["max_concurrent_scrapes"]["overridden"] is False
    assert flat["archive_rate_max"]["risk"]["red"] == 105
    assert flat["log_level"]["restart"] is True
    assert flat["log_level"]["choices"] == ["DEBUG", "INFO", "WARNING", "ERROR"]


@pytest.mark.asyncio
async def test_put_applies_hot_and_marks_overridden(client):
    r = await client.put("/api/config", json={"scrape_delay_min": 0.8})
    assert r.status_code == 200
    assert settings.scrape_delay_min == 0.8
    d = (await client.get("/api/config")).json()
    flat = {s["key"]: s for g in d["groups"] for s in g["settings"]}
    assert flat["scrape_delay_min"]["value"] == 0.8
    assert flat["scrape_delay_min"]["overridden"] is True


@pytest.mark.asyncio
async def test_put_persists_and_reloads_after_restart(client):
    await client.put("/api/config", json={"max_concurrent_scrapes": 9})
    raw = await dbmod.get_app_state("cfg_overrides")
    assert json.loads(raw)["max_concurrent_scrapes"] == 9
    # Simulate a restart: settings back to boot value, then reload overrides.
    settings.max_concurrent_scrapes = 4
    runtime_config.reset_state_for_tests()
    await runtime_config.load_overrides()
    assert settings.max_concurrent_scrapes == 9


@pytest.mark.asyncio
async def test_put_rejects_bad_type_and_out_of_bounds(client):
    r = await client.put("/api/config", json={"max_concurrent_scrapes": "abc"})
    assert r.status_code == 400
    r = await client.put("/api/config", json={"archive_request_timeout": 1})
    assert r.status_code == 400
    assert settings.archive_request_timeout != 1
    r = await client.put("/api/config", json={"log_level": "VERBOSE"})
    assert r.status_code == 400
    r = await client.put("/api/config", json={"nope_unknown": 1})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_put_reports_restart_required(client):
    r = await client.put("/api/config", json={"log_level": "DEBUG", "scrape_max_retries": 5})
    assert r.status_code == 200
    d = r.json()
    assert "log_level" in d["restart_required"]
    assert "scrape_max_retries" not in d["restart_required"]


@pytest.mark.asyncio
async def test_reset_single_key_restores_boot_value(client):
    boot = settings.scan_retention_days
    await client.put("/api/config", json={"scan_retention_days": 3})
    assert settings.scan_retention_days == 3
    r = await client.post("/api/config/reset", json={"keys": ["scan_retention_days"]})
    assert r.status_code == 200
    assert settings.scan_retention_days == boot
    raw = await dbmod.get_app_state("cfg_overrides")
    assert "scan_retention_days" not in json.loads(raw or "{}")


@pytest.mark.asyncio
async def test_reset_all_restores_everything(client):
    boot_delay = settings.scrape_delay_max
    boot_queue = settings.max_queue_total
    await client.put("/api/config", json={"scrape_delay_max": 4.0, "max_queue_total": 7})
    r = await client.post("/api/config/reset", json={})
    assert r.status_code == 200
    assert settings.scrape_delay_max == boot_delay
    assert settings.max_queue_total == boot_queue
    assert json.loads(await dbmod.get_app_state("cfg_overrides") or "{}") == {}


@pytest.mark.asyncio
async def test_service_status_advertises_panel(client):
    d = (await client.get("/api/service-status")).json()
    assert d["service"]["config_panel"] is True
    settings.config_panel_enabled = False
    d = (await client.get("/api/service-status")).json()
    assert d["service"]["config_panel"] is False


@pytest.mark.asyncio
async def test_panel_disabled_returns_404(client):
    settings.config_panel_enabled = False
    assert (await client.get("/api/config")).status_code == 404
    assert (await client.put("/api/config", json={"max_queue_total": 5})).status_code == 404
    assert (await client.post("/api/config/reset", json={})).status_code == 404


@pytest.mark.asyncio
async def test_rate_governor_hook_applies_new_start_rate(client):
    r = await client.put("/api/config", json={"archive_rate_per_minute": 42,
                                              "archive_rate_min": 30})
    assert r.status_code == 200
    assert archive_rate.current_rate_per_minute() == 42.0


def test_snapshot_cap_multiplier_scales_adaptive_cap():
    from models import ScanConfig
    from services.filters import DEPTH_PRESETS, _apply_depth_to_cap
    cfg = ScanConfig(depth="standard")
    settings.snapshot_cap_multiplier = 1.0
    base = _apply_depth_to_cap(1000, cfg)
    settings.snapshot_cap_multiplier = 2.0
    assert _apply_depth_to_cap(1000, cfg) == base * 2
    # Preset clamps still win over the multiplier.
    settings.snapshot_cap_multiplier = 1000.0
    full = ScanConfig(depth="full")
    assert _apply_depth_to_cap(1000, full) == DEPTH_PRESETS["full"]["max_cap"]
