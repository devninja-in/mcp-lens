import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

import src.app.database as db_module
from src.app.database import set_server_config
from src.app.main import app


async def _noop():
    pass


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(db_module, "_migrate_tokens_json", _noop)
    monkeypatch.setattr(db_module, "_migrate_mcp_json", _noop)
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()
    await set_server_config(
        "test-server",
        {
            "url": "https://example.com/mcp",
            "enabled": True,
            "auth": False,
        },
    )
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    await db_module.dispose_db()


@pytest.mark.asyncio
async def test_list_servers(client):
    resp = client.get("/api/servers")
    assert resp.status_code == 200
    assert "test-server" in resp.json()["servers"]


@pytest.mark.asyncio
async def test_get_server(client):
    resp = client.get("/api/servers/test-server")
    assert resp.status_code == 200
    assert resp.json()["name"] == "test-server"


@pytest.mark.asyncio
async def test_get_server_not_found(client):
    resp = client.get("/api/servers/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_server(client):
    resp = client.post(
        "/api/servers?name=new-server",
        json={"url": "https://new.com/mcp", "enabled": True},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_create_duplicate(client):
    resp = client.post(
        "/api/servers?name=test-server",
        json={"url": "https://dup.com/mcp"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_server(client):
    resp = client.put(
        "/api/servers/test-server",
        json={"url": "https://updated.com/mcp", "enabled": False},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_server(client):
    resp = client.delete("/api/servers/test-server")
    assert resp.status_code == 200
