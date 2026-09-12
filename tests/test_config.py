import pytest

from src.app.config import load_config, save_config
from src.app.database import set_server_config
from src.app.models import McpConfig, McpServerConfig


@pytest.mark.asyncio
async def test_load_empty_config(db):
    config = await load_config()
    assert config.mcpServers == {}


@pytest.mark.asyncio
async def test_load_config_with_server(db):
    await set_server_config("test-server", {
        "url": "https://example.com/mcp",
        "enabled": True,
        "auth": False,
    })
    config = await load_config()
    assert "test-server" in config.mcpServers
    assert config.mcpServers["test-server"].url == "https://example.com/mcp"


@pytest.mark.asyncio
async def test_save_config(db):
    config = McpConfig(mcpServers={
        "my-server": McpServerConfig(url="https://example.com/mcp")
    })
    await save_config(config)
    loaded = await load_config()
    assert "my-server" in loaded.mcpServers
    assert loaded.mcpServers["my-server"].url == "https://example.com/mcp"


def test_get_env_var(monkeypatch):
    monkeypatch.setenv("MCP_TEST_TOKEN", "abc123")
    from src.app.config import get_env_var
    assert get_env_var("MCP_TEST_TOKEN") == "abc123"
    assert get_env_var("NONEXISTENT") is None
