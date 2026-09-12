import json

import pytest
import pytest_asyncio

import src.app.database as db_module
from src.app.database import (
    check_db_health,
    delete_ground_truth,
    get_eval_report,
    get_ground_truth,
    save_eval_report,
    save_ground_truth,
)


async def _noop():
    pass


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(db_module, "_migrate_tokens_json", _noop)
    monkeypatch.setattr(db_module, "_migrate_mcp_json", _noop)
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()
    yield
    await db_module.dispose_db()


# Ground truth CRUD tests
@pytest.mark.asyncio
async def test_save_and_get_ground_truth(db):
    yaml_content = """test_cases:
  - expected_tool_selection:
      - "tool1"
    prompts:
      - "prompt1"
"""
    await save_ground_truth("test-server", yaml_content)

    result = await get_ground_truth("test-server")
    assert result is not None
    assert "test_cases" in result
    assert len(result["test_cases"]) == 1
    assert result["test_cases"][0]["expected_tool_selection"] == ["tool1"]
    assert result["test_cases"][0]["prompts"] == ["prompt1"]


@pytest.mark.asyncio
async def test_save_ground_truth_upsert(db):
    yaml_content_1 = """test_cases:
  - expected_tool_selection:
      - "tool1"
    prompts:
      - "prompt1"
"""
    await save_ground_truth("test-server", yaml_content_1)

    yaml_content_2 = """test_cases:
  - expected_tool_selection:
      - "tool2"
    prompts:
      - "prompt2"
  - expected_tool_selection:
      - "tool3"
    prompts:
      - "prompt3"
"""
    await save_ground_truth("test-server", yaml_content_2)

    result = await get_ground_truth("test-server")
    assert result is not None
    assert len(result["test_cases"]) == 2
    assert result["test_cases"][0]["expected_tool_selection"] == ["tool2"]


@pytest.mark.asyncio
async def test_delete_ground_truth(db):
    yaml_content = """test_cases:
  - expected_tool_selection:
      - "tool1"
    prompts:
      - "prompt1"
"""
    await save_ground_truth("test-server", yaml_content)

    await delete_ground_truth("test-server")

    result = await get_ground_truth("test-server")
    assert result is None


@pytest.mark.asyncio
async def test_get_ground_truth_nonexistent(db):
    result = await get_ground_truth("nonexistent-server")
    assert result is None


# Eval report CRUD tests
@pytest.mark.asyncio
async def test_save_and_get_eval_report(db):
    report_data = {
        "timestamp": "2026-09-11T12:00:00Z",
        "server_name": "test-server",
        "layers": {
            "protocol": {"issues": []},
            "quality": {"issues": []},
        },
        "overall_score": 95.0,
        "gate_passed": True,
    }
    await save_eval_report("test-server", report_data, has_llm=False)

    result = await get_eval_report("test-server")
    assert result is not None
    assert result["server_name"] == "test-server"
    assert result["overall_score"] == 95.0
    assert result["gate_passed"] is True


@pytest.mark.asyncio
async def test_save_eval_report_upsert(db):
    report_data_1 = {
        "timestamp": "2026-09-11T12:00:00Z",
        "server_name": "test-server",
        "overall_score": 80.0,
        "gate_passed": False,
    }
    await save_eval_report("test-server", report_data_1, has_llm=False)

    report_data_2 = {
        "timestamp": "2026-09-11T13:00:00Z",
        "server_name": "test-server",
        "overall_score": 95.0,
        "gate_passed": True,
    }
    await save_eval_report("test-server", report_data_2, has_llm=True)

    result = await get_eval_report("test-server")
    assert result is not None
    assert result["overall_score"] == 95.0
    assert result["gate_passed"] is True
    assert result["timestamp"] == "2026-09-11T13:00:00Z"


@pytest.mark.asyncio
async def test_get_eval_report_nonexistent(db):
    result = await get_eval_report("nonexistent-server")
    assert result is None


@pytest.mark.asyncio
async def test_save_eval_report_with_llm_flag(db):
    report_data = {
        "timestamp": "2026-09-11T12:00:00Z",
        "server_name": "test-server",
        "layers": {
            "protocol": {"issues": []},
            "quality": {"issues": []},
            "llm": {"issues": []},
        },
        "overall_score": 95.0,
        "gate_passed": True,
    }
    await save_eval_report("test-server", report_data, has_llm=True)

    result = await get_eval_report("test-server")
    assert result is not None
    assert "llm" in result["layers"]


@pytest.mark.asyncio
async def test_check_db_health(db):
    result = await check_db_health()
    assert result is True


@pytest.mark.asyncio
async def test_check_db_health_before_init(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{tmp_path / 'nope.db'}")
    old_engine = db_module._engine
    old_factory = db_module._session_factory
    db_module._engine = None
    db_module._session_factory = None
    result = await check_db_health()
    assert result is False
    db_module._engine = old_engine
    db_module._session_factory = old_factory


@pytest.mark.asyncio
async def test_get_session_before_init(tmp_path, monkeypatch):
    db_module._engine = None
    db_module._session_factory = None
    with pytest.raises(RuntimeError, match="Database not initialized"):
        db_module._get_session()


@pytest.mark.asyncio
async def test_migrate_tokens_json(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()

    tokens_file = tmp_path / "tokens.json"
    tokens_data = {
        "myserver_bearer": "test_token_123",
        "myserver_apikey": "api_key_456",
    }
    tokens_file.write_text(json.dumps(tokens_data))
    monkeypatch.chdir(tmp_path)

    await db_module._migrate_tokens_json()

    from src.app.database import get_secret
    bearer = await get_secret("myserver", "bearer")
    assert bearer == "test_token_123"

    await db_module.dispose_db()


@pytest.mark.asyncio
async def test_migrate_tokens_json_skip_existing(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()

    from src.app.database import set_secret
    await set_secret("existing", "bearer", "existing_val")

    tokens_file = tmp_path / "tokens.json"
    tokens_data = {"newserver_bearer": "new_token"}
    tokens_file.write_text(json.dumps(tokens_data))
    monkeypatch.chdir(tmp_path)

    await db_module._migrate_tokens_json()

    from src.app.database import get_secret
    result = await get_secret("newserver", "bearer")
    assert result is None

    await db_module.dispose_db()


@pytest.mark.asyncio
async def test_migrate_mcp_json(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()

    mcp_file = tmp_path / "mcp.json"
    mcp_data = {
        "mcpServers": {
            "server1": {"url": "https://example.com/mcp", "enabled": True, "auth": False}
        }
    }
    mcp_file.write_text(json.dumps(mcp_data))
    monkeypatch.chdir(tmp_path)

    await db_module._migrate_mcp_json()

    from src.app.database import get_server_config
    config = await get_server_config("server1")
    assert config is not None
    assert config["url"] == "https://example.com/mcp"

    await db_module.dispose_db()


@pytest.mark.asyncio
async def test_migrate_mcp_json_skip_existing(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()

    from src.app.database import set_server_config
    await set_server_config("existing", {"url": "https://existing.com", "enabled": True, "auth": False})

    mcp_file = tmp_path / "mcp.json"
    mcp_data = {
        "mcpServers": {
            "new-server": {"url": "https://new.com", "enabled": True, "auth": False}
        }
    }
    mcp_file.write_text(json.dumps(mcp_data))
    monkeypatch.chdir(tmp_path)

    await db_module._migrate_mcp_json()

    from src.app.database import get_server_config
    config = await get_server_config("new-server")
    assert config is None

    await db_module.dispose_db()


@pytest.mark.asyncio
async def test_migrate_tokens_no_file(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()

    monkeypatch.chdir(tmp_path)
    await db_module._migrate_tokens_json()

    await db_module.dispose_db()


@pytest.mark.asyncio
async def test_migrate_mcp_no_file(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()

    monkeypatch.chdir(tmp_path)
    await db_module._migrate_mcp_json()

    await db_module.dispose_db()


@pytest.mark.asyncio
async def test_migrate_tokens_dcr_and_sso(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()

    tokens_file = tmp_path / "tokens.json"
    tokens_data = {
        "myserver_dcr": {"client_id": "cid", "client_secret": "csec"},
        "myserver_sso": {"token": "sso_token"},
        "generic_server": {"access_token": "at"},
    }
    tokens_file.write_text(json.dumps(tokens_data))
    monkeypatch.chdir(tmp_path)

    await db_module._migrate_tokens_json()

    from src.app.database import get_secret
    dcr = await get_secret("myserver", "dcr")
    assert dcr == {"client_id": "cid", "client_secret": "csec"}

    bearer = await get_secret("myserver", "bearer")
    assert bearer == {"token": "sso_token"}

    oauth = await get_secret("generic_server", "oauth")
    assert oauth == {"access_token": "at"}

    await db_module.dispose_db()
