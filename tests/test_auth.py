import json

import pytest

from src.app.auth import (
    _load_tokens,
    _save_tokens,
    _server_name_to_env_key,
    get_auth_status,
    get_token,
)
from src.app.models import McpServerConfig


def test_server_name_to_env_key():
    assert _server_name_to_env_key("dataverse-mcp") == "MCP_DATAVERSE_MCP_TOKEN"
    assert _server_name_to_env_key("my-server") == "MCP_MY_SERVER_TOKEN"


def test_load_save_tokens(tmp_path, monkeypatch):
    tokens_path = tmp_path / "tokens.json"
    monkeypatch.setattr("src.app.auth.TOKENS_PATH", tokens_path)

    assert _load_tokens() == {}

    _save_tokens({"server1": {"access_token": "abc"}})
    loaded = _load_tokens()
    assert loaded["server1"]["access_token"] == "abc"


def test_get_auth_status_no_auth():
    config = McpServerConfig(url="https://example.com", auth=False)
    status = get_auth_status("test", config)
    assert status["authenticated"] is True


def test_get_auth_status_sso_missing(monkeypatch):
    monkeypatch.delenv("MCP_TEST_SERVER_TOKEN", raising=False)
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="sso")
    status = get_auth_status("test-server", config)
    assert status["authenticated"] is False


def test_get_auth_status_sso_present(monkeypatch):
    monkeypatch.setenv("MCP_TEST_SERVER_TOKEN", "jwt123")
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="sso")
    status = get_auth_status("test-server", config)
    assert status["authenticated"] is True


@pytest.mark.asyncio
async def test_get_token_sso(monkeypatch):
    monkeypatch.setenv("MCP_MY_MCP_TOKEN", "sso-token-value")
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="sso")
    token = await get_token("my-mcp", config)
    assert token == "sso-token-value"


@pytest.mark.asyncio
async def test_get_token_sso_missing(monkeypatch):
    monkeypatch.delenv("MCP_MISSING_TOKEN", raising=False)
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="sso")
    with pytest.raises(ValueError, match="SSO token not found"):
        await get_token("missing", config)


@pytest.mark.asyncio
async def test_get_token_no_auth():
    config = McpServerConfig(url="https://example.com", auth=False)
    token = await get_token("test", config)
    assert token is None
