"""The public feed and the publish-to-feed feature were removed (nobody used
the feed: most scans were kept private). Viewing and sharing a scan by its
url_id capability token still works; only the feed/publish surface is gone.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import db as dbmod


@pytest_asyncio.fixture(autouse=True)
async def _reset(tmp_path):
    await dbmod.init_db(str(tmp_path / "t.db"))
    yield


@pytest_asyncio.fixture()
async def client():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_feed_endpoint_gone(client):
    assert (await client.get("/api/feed")).status_code == 404


@pytest.mark.asyncio
async def test_publish_endpoint_gone(client):
    now = datetime.now(timezone.utc)
    await dbmod.save_job(
        url_id="viewme", domain="x.com", client_ip="1.1.1.1",
        created_at=now, expires_at=now + timedelta(days=7),
        status="completed", meta={}, results={},
    )
    # Publishing is gone...
    assert (await client.post("/api/s/viewme/publish", json={"published": True})).status_code == 404
    # ...but the scan is still viewable by its url_id (local history / share link).
    assert (await client.get("/api/s/viewme")).status_code == 200


def test_scan_request_has_no_publish_field():
    from models import JobCreate
    assert "publish_on_complete" not in JobCreate.model_fields
