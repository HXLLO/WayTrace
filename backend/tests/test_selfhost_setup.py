"""First-run setup state + complete-setup endpoint (self-host only)."""
import re

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import db as dbmod
from config import settings
from services import identity, runtime_config


@pytest_asyncio.fixture(autouse=True)
async def _reset(tmp_path):
    await dbmod.init_db(str(tmp_path / "t.db"))
    saved_panel = settings.config_panel_enabled
    settings.config_panel_enabled = True
    identity.reset_state_for_tests()
    runtime_config.reset_state_for_tests()
    yield
    settings.config_panel_enabled = saved_panel
    identity.reset_state_for_tests()
    runtime_config.reset_state_for_tests()


@pytest_asyncio.fixture()
async def client():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_get_config_exposes_setup_and_instance_id(client):
    d = (await client.get("/api/config")).json()
    assert d["setup_completed"] is False
    assert re.fullmatch(r"[0-9a-f]{6}", d["instance_id"])
    assert any(g["key"] == "instance" for g in d["groups"])
    inst = next(g for g in d["groups"] if g["key"] == "instance")
    keys = {s["key"] for s in inst["settings"]}
    assert {"instance_name", "operator_contact", "default_theme", "default_categories"} <= keys


@pytest.mark.asyncio
async def test_complete_setup_flips_and_persists(client):
    assert (await client.get("/api/config")).json()["setup_completed"] is False
    r = await client.post("/api/config/complete-setup")
    assert r.status_code == 200 and r.json()["setup_completed"] is True
    assert (await client.get("/api/config")).json()["setup_completed"] is True


@pytest.mark.asyncio
async def test_setup_endpoints_404_when_panel_disabled(client):
    settings.config_panel_enabled = False
    assert (await client.get("/api/config")).status_code == 404
    assert (await client.post("/api/config/complete-setup")).status_code == 404


@pytest.mark.asyncio
async def test_service_status_exposes_setup_completed(client):
    d = (await client.get("/api/service-status")).json()["service"]
    assert d["setup_completed"] is False   # panel on, not yet completed
    await client.post("/api/config/complete-setup")
    d2 = (await client.get("/api/service-status")).json()["service"]
    assert d2["setup_completed"] is True


@pytest.mark.asyncio
async def test_service_status_setup_true_when_panel_off(client):
    settings.config_panel_enabled = False
    d = (await client.get("/api/service-status")).json()["service"]
    assert d["setup_completed"] is True   # hosted never routes to the wizard


def test_resolve_categories():
    from routers.scan import resolve_categories
    from models import ScanConfig

    # explicit per-scan list wins
    assert resolve_categories(ScanConfig(categories=["endpoints"])) == ["endpoints"]
    # no config / no default -> None (all categories)
    settings.default_categories = []
    assert resolve_categories(None) is None
    assert resolve_categories(ScanConfig()) is None
    # explicit empty list is normalised to None (all), never extract-nothing
    assert resolve_categories(ScanConfig(categories=[])) is None
    # instance default applies when no explicit choice
    settings.default_categories = ["emails", "endpoints"]
    assert resolve_categories(None) == ["emails", "endpoints"]
    assert resolve_categories(ScanConfig()) == ["emails", "endpoints"]
    settings.default_categories = []
