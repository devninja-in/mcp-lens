import pytest

from src.app.database import (
    delete_secret,
    delete_server_config,
    get_all_servers,
    get_secret,
    get_server_config,
    set_secret,
    set_server_config,
)


@pytest.mark.asyncio
async def test_set_and_get_secret(db):
    await set_secret("my-server", "bearer", {"token": "abc123"})
    result = await get_secret("my-server", "bearer")
    assert result == {"token": "abc123"}


@pytest.mark.asyncio
async def test_get_secret_missing(db):
    result = await get_secret("nonexistent", "bearer")
    assert result is None


@pytest.mark.asyncio
async def test_set_secret_upsert(db):
    await set_secret("s1", "apikey", {"key": "old"})
    await set_secret("s1", "apikey", {"key": "new"})
    result = await get_secret("s1", "apikey")
    assert result == {"key": "new"}


@pytest.mark.asyncio
async def test_delete_secret(db):
    await set_secret("s1", "dcr", {"client_id": "cid"})
    await delete_secret("s1", "dcr")
    result = await get_secret("s1", "dcr")
    assert result is None


@pytest.mark.asyncio
async def test_delete_secret_missing(db):
    await delete_secret("nonexistent", "bearer")


@pytest.mark.asyncio
async def test_multiple_secret_types(db):
    await set_secret("s1", "bearer", {"token": "t1"})
    await set_secret("s1", "apikey", {"key": "k1"})
    await set_secret("s1", "oauth", {"access_token": "at1"})

    assert (await get_secret("s1", "bearer")) == {"token": "t1"}
    assert (await get_secret("s1", "apikey")) == {"key": "k1"}
    assert (await get_secret("s1", "oauth")) == {"access_token": "at1"}


# --- Server config CRUD tests ---


@pytest.mark.asyncio
async def test_set_and_get_server_config(db):
    await set_server_config("my-server", {"url": "https://example.com/mcp", "enabled": True})
    result = await get_server_config("my-server")
    assert result == {"url": "https://example.com/mcp", "enabled": True}


@pytest.mark.asyncio
async def test_get_server_config_missing(db):
    result = await get_server_config("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_set_server_config_upsert(db):
    await set_server_config("s1", {"url": "https://old.com"})
    await set_server_config("s1", {"url": "https://new.com"})
    result = await get_server_config("s1")
    assert result == {"url": "https://new.com"}


@pytest.mark.asyncio
async def test_delete_server_config(db):
    await set_server_config("s1", {"url": "https://example.com"})
    await delete_server_config("s1")
    result = await get_server_config("s1")
    assert result is None


@pytest.mark.asyncio
async def test_delete_server_config_missing(db):
    await delete_server_config("nonexistent")


@pytest.mark.asyncio
async def test_get_all_servers(db):
    await set_server_config("server-a", {"url": "https://a.com"})
    await set_server_config("server-b", {"url": "https://b.com"})
    all_servers = await get_all_servers()
    assert "server-a" in all_servers
    assert "server-b" in all_servers
    assert all_servers["server-a"] == {"url": "https://a.com"}


@pytest.mark.asyncio
async def test_get_all_servers_empty(db):
    all_servers = await get_all_servers()
    assert all_servers == {}
