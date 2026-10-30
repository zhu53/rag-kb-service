"""我的第一个异步测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from kb_service.core.security import create_access_token
from kb_service.main import create_app


@pytest.fixture
async def async_client():
    """async fixture：yield 前后各有一段异步生命周期。"""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "Authorization": f"Bearer {create_access_token('11111111-1111-4111-8111-111111111111')}"
        },
    ) as client:
        yield client


async def test_health_async(async_client):
    resp = await async_client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
