from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """固定使用 asyncio，避免测试尝试其他异步后端。"""
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """创建直接调用 FastAPI ASGI 应用的异步测试客户端。"""
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as async_client:
        yield async_client


@pytest.mark.anyio
async def test_root_endpoint(client: AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "AI Customer Service API is running",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


@pytest.mark.anyio
async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "AI Customer Service API",
        "version": "0.1.0",
        "environment": "development",
    }


@pytest.mark.anyio
async def test_openapi_document_is_available(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    assert document["info"]["title"] == "AI Customer Service API"
    assert "/api/v1/health" in document["paths"]
