"""
Shared test fixtures.
Uses fakeredis so tests run without a real Redis instance.
"""

import sys
from pathlib import Path

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# make src importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
# make sentinel_sdk importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


@pytest.fixture(autouse=True)
async def fake_redis(monkeypatch):
    """Replace Redis with an in-process fakeredis for every test."""
    import store as store_module

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store_module.store._redis = fake

    import graph as graph_module
    graph_module.graph.rebuild([], [])

    yield fake

    await fake.aclose()


@pytest.fixture
async def client():
    from main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
