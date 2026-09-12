import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

import src.app.database as db_module
from src.app.main import app


async def _noop():
    pass


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(db_module, "_migrate_tokens_json", _noop)
    monkeypatch.setattr(db_module, "_migrate_mcp_json", _noop)

    # Mock LLM config path
    llm_config_path = tmp_path / "llm.json"
    monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_config_path)

    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    await db_module.dispose_db()


@pytest.mark.asyncio
async def test_list_llm_configs_with_file(client, tmp_path, monkeypatch):
    import json

    llm_config_path = tmp_path / "llm.json"
    configs = {
        "configs": {
            "test-config": {
                "provider": "mock",
                "model": "test-model",
            },
            "another-config": {
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
            },
        },
        "default": "test-config",
    }
    llm_config_path.write_text(json.dumps(configs))

    monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_config_path)

    resp = client.get("/api/llm-configs")
    assert resp.status_code == 200
    data = resp.json()
    assert "configs" in data
    assert "default" in data
    assert len(data["configs"]) >= 1


@pytest.mark.asyncio
async def test_list_llm_configs_env_only(client, monkeypatch):

    # Set environment variable for LLM provider
    monkeypatch.setenv("EVAL_LLM_PROVIDER", "mock")

    # Ensure no llm.json file exists
    llm_config_path = client.app.state.__dict__.get("llm_config_path")
    if llm_config_path:
        import pathlib

        p = pathlib.Path(llm_config_path)
        if p.exists():
            p.unlink()

    resp = client.get("/api/llm-configs")
    assert resp.status_code == 200
    data = resp.json()
    assert "configs" in data
    assert "default" in data
