import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "active_jobs" in data
    assert "uptime_seconds" in data


@pytest.mark.anyio
async def test_stats(client):
    resp = await client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_scans_run" in data
    assert "active_jobs" in data


@pytest.mark.anyio
async def test_scan_valid_domain(client):
    resp = await client.post("/api/scan", json={"domain": "example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data


@pytest.mark.anyio
async def test_scan_invalid_domain(client):
    resp = await client.post("/api/scan", json={"domain": "not_a_domain"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_scan_rejects_url(client):
    resp = await client.post(
        "/api/scan", json={"domain": "https://example.com"}
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_scan_rejects_ip(client):
    resp = await client.post("/api/scan", json={"domain": "192.168.1.1"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_job_not_found(client):
    resp = await client.get("/api/jobs/nonexistent-uuid")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_scan_returns_existing_job(client):
    resp1 = await client.post("/api/scan", json={"domain": "dedup-test.com"})
    resp2 = await client.post("/api/scan", json={"domain": "dedup-test.com"})
    assert resp1.json()["job_id"] == resp2.json()["job_id"]


@pytest.mark.anyio
async def test_scan_invalid_categories(client):
    resp = await client.post("/api/scan", json={
        "domain": "example.com",
        "config": {"categories": ["emails", "not_a_category"]},
    })
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_scan_valid_categories(client):
    resp = await client.post("/api/scan", json={
        "domain": "cat-test.com",
        "config": {"categories": ["emails", "phones"]},
    })
    assert resp.status_code == 200
    assert "job_id" in resp.json()


@pytest.mark.anyio
async def test_scan_with_selected_snapshots(client):
    resp = await client.post("/api/scan", json={
        "domain": "snap-test.com",
        "selected_snapshots": [
            {"timestamp": "20220601120000", "url": "https://snap-test.com/"},
        ],
    })
    assert resp.status_code == 200
    assert "job_id" in resp.json()


@pytest.mark.anyio
async def test_scan_smart_dedup_flag(client):
    resp = await client.post("/api/scan", json={
        "domain": "dedup-flag-test.com",
        "config": {"smart_dedup": False},
    })
    assert resp.status_code == 200
    assert "job_id" in resp.json()


@pytest.mark.anyio
async def test_scan_smart_dedup_default(client):
    resp = await client.post("/api/scan", json={
        "domain": "dedup-default-test.com",
        "config": {},
    })
    assert resp.status_code == 200
    assert "job_id" in resp.json()


def test_preflight_response_structure():
    """PreflightResponse has expected fields."""
    from models import DateRange, PreflightResponse, ScanConfig

    resp = PreflightResponse(
        domain="example.com",
        total_snapshots=100,
        html_snapshots=80,
        unique_paths=10,
        unique_content=70,
        date_range=DateRange(first="2020-01", last="2024-12"),
        suggested_config=ScanConfig(cap=200),
    )
    assert resp.domain == "example.com"
    assert resp.total_snapshots == 100
    assert resp.html_snapshots == 80
    assert resp.path_groups == []
