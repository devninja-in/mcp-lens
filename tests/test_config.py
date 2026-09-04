import json
from pathlib import Path

from src.app.config import load_config, save_config
from src.app.models import McpConfig, McpServerConfig


def test_load_empty_config(tmp_path, monkeypatch):
    monkeypatch.setattr("src.app.config.CONFIG_PATH", tmp_path / "mcp.json")
    config = load_config()
    assert config.mcpServers == {}


def test_load_config_with_server(tmp_path, monkeypatch):
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
    config = load_config()
    assert "test-server" in config.mcpServers
    assert config.mcpServers["test-server"].url == "https://example.com/mcp"


def test_save_config(tmp_path, monkeypatch):
    config_path = tmp_path / "mcp.json"
    monkeypatch.setattr("src.app.config.CONFIG_PATH", config_path)
    config = McpConfig(mcpServers={
        "my-server": McpServerConfig(url="https://example.com/mcp")
    })
    save_config(config)
    loaded = json.loads(config_path.read_text())
    assert loaded["mcpServers"]["my-server"]["url"] == "https://example.com/mcp"


def test_get_env_var(monkeypatch):
    monkeypatch.setenv("MCP_TEST_TOKEN", "abc123")
    from src.app.config import get_env_var
    assert get_env_var("MCP_TEST_TOKEN") == "abc123"
    assert get_env_var("NONEXISTENT") is None
