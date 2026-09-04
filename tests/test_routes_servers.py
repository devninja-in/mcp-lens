import json

import pytest
from fastapi.testclient import TestClient

from src.app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps({
        "mcpServers": {
            "test-server": {
                "url": "https://example.com/mcp",
                "enabled": True,
                "auth": False,
            }
        }
    }))
    monkeypatch.setattr("src.app.config.CONFIG_PATH", config_path)
    return TestClient(app)


def test_list_servers(client):
    resp = client.get("/api/servers")
    assert resp.status_code == 200
    assert "test-server" in resp.json()["servers"]


def test_get_server(client):
    resp = client.get("/api/servers/test-server")
    assert resp.status_code == 200
    assert resp.json()["name"] == "test-server"


def test_get_server_not_found(client):
    resp = client.get("/api/servers/nonexistent")
    assert resp.status_code == 404


def test_create_server(client):
    resp = client.post(
        "/api/servers?name=new-server",
        json={"url": "https://new.com/mcp", "enabled": True},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_create_duplicate(client):
    resp = client.post(
        "/api/servers?name=test-server",
        json={"url": "https://dup.com/mcp"},
    )
    assert resp.status_code == 409


def test_update_server(client):
    resp = client.put(
        "/api/servers/test-server",
        json={"url": "https://updated.com/mcp", "enabled": False},
    )
    assert resp.status_code == 200


def test_delete_server(client):
    resp = client.delete("/api/servers/test-server")
    assert resp.status_code == 200
