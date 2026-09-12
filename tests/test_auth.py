from unittest.mock import AsyncMock, MagicMock

import pytest

from src.app.auth import (
    _derive_base_urls,
    _server_name_to_env_key,
    discover_oauth_metadata,
    get_auth_status,
    get_token,
    set_bearer_token,
)
from src.app.models import McpServerConfig


def test_server_name_to_env_key():
    assert _server_name_to_env_key("dataverse-mcp") == "MCP_DATAVERSE_MCP_TOKEN"
    assert _server_name_to_env_key("my-server") == "MCP_MY_SERVER_TOKEN"


@pytest.mark.asyncio
async def test_get_auth_status_no_auth(db):
    config = McpServerConfig(url="https://example.com", auth=False)
    status = await get_auth_status("test", config)
    assert status["authenticated"] is True


@pytest.mark.asyncio
async def test_get_auth_status_bearer_token_missing(db, monkeypatch):
    monkeypatch.delenv("MCP_TEST_SERVER_TOKEN", raising=False)
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="bearer_token")
    status = await get_auth_status("test-server", config)
    assert status["authenticated"] is False


@pytest.mark.asyncio
async def test_get_auth_status_bearer_token_present(db, monkeypatch):
    monkeypatch.setenv("MCP_TEST_SERVER_TOKEN", "jwt123")
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="bearer_token")
    status = await get_auth_status("test-server", config)
    assert status["authenticated"] is True


@pytest.mark.asyncio
async def test_get_auth_status_bearer_from_db(db):
    await set_bearer_token("db-server", "stored-token")
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="bearer_token")
    status = await get_auth_status("db-server", config)
    assert status["authenticated"] is True


@pytest.mark.asyncio
async def test_get_token_bearer(db, monkeypatch):
    monkeypatch.setenv("MCP_MY_MCP_TOKEN", "bearer-token-value")
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="bearer_token")
    token = await get_token("my-mcp", config)
    assert token == "bearer-token-value"  # noqa: S105


@pytest.mark.asyncio
async def test_get_token_bearer_missing(db, monkeypatch):
    monkeypatch.delenv("MCP_MISSING_TOKEN", raising=False)
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="bearer_token")
    with pytest.raises(ValueError, match="Bearer token not found"):
        await get_token("missing", config)


@pytest.mark.asyncio
async def test_get_token_no_auth(db):
    config = McpServerConfig(url="https://example.com", auth=False)
    token = await get_token("test", config)
    assert token is None


@pytest.mark.asyncio
async def test_get_token_bearer_from_db(db):
    await set_bearer_token("db-server", "my-db-token")
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="bearer_token")
    token = await get_token("db-server", config)
    assert token == "my-db-token"  # noqa: S105


# --- Discovery tests ---


def test_derive_base_urls():
    urls = _derive_base_urls("https://example.com/org/project/mcp")
    assert urls == [
        "https://example.com/org/project/mcp",
        "https://example.com/org/project",
        "https://example.com/org",
        "https://example.com",
    ]


def test_derive_base_urls_no_path():
    urls = _derive_base_urls("https://example.com")
    assert urls == ["https://example.com"]


MOCK_OPENID_DOC = {
    "issuer": "https://example.com",
    "authorization_endpoint": "https://example.com/authorize",
    "token_endpoint": "https://example.com/token",
    "registration_endpoint": "https://example.com/register",
    "scopes_supported": ["openid", "profile"],
    "grant_types_supported": ["authorization_code"],
    "response_types_supported": ["code"],
}


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


@pytest.mark.asyncio
async def test_discover_oauth_metadata_openid(monkeypatch):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(200, MOCK_OPENID_DOC)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)

    result = await discover_oauth_metadata("https://example.com/mcp")
    assert result["authorization_endpoint"] == "https://example.com/authorize"
    assert result["token_endpoint"] == "https://example.com/token"  # noqa: S105
    assert result["registration_endpoint"] == "https://example.com/register"
    assert result["scopes_supported"] == ["openid", "profile"]
    assert "discovery_url" in result


@pytest.mark.asyncio
async def test_discover_oauth_metadata_rfc8414_fallback(monkeypatch):
    call_count = 0

    async def mock_get(url):
        nonlocal call_count
        call_count += 1
        if "openid-configuration" in url:
            return _mock_response(404)
        return _mock_response(200, MOCK_OPENID_DOC)

    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)

    result = await discover_oauth_metadata("https://example.com")
    assert result["authorization_endpoint"] == "https://example.com/authorize"
    assert "oauth-authorization-server" in result["discovery_url"]


@pytest.mark.asyncio
async def test_discover_oauth_metadata_strips_path(monkeypatch):
    async def mock_get(url):
        if "example.com/mcp" in url:
            return _mock_response(404)
        if "example.com/.well-known/openid-configuration" in url:
            return _mock_response(200, MOCK_OPENID_DOC)
        return _mock_response(404)

    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)

    result = await discover_oauth_metadata("https://example.com/mcp")
    assert result["authorization_endpoint"] == "https://example.com/authorize"


@pytest.mark.asyncio
async def test_discover_oauth_metadata_all_fail(monkeypatch):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(404)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)

    with pytest.raises(ValueError, match="No OAuth metadata found"):
        await discover_oauth_metadata("https://example.com/mcp")
