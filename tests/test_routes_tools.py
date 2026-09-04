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
    monkeypatch.setattr("src.app.tools_store.TOOLS_DIR", tmp_path / "tools")
    return TestClient(app)


def test_get_tools_not_fetched(client):
    resp = client.get("/api/servers/test-server/tools")
    assert resp.status_code == 404


def test_get_tools_missing_server(client):
    resp = client.get("/api/servers/nonexistent/tools")
    assert resp.status_code == 404
