import json
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

import src.app.database as db_module
from src.app.database import save_capability_analysis, set_server_config
from src.app.eval.comparison import categorize_tools_detailed
from src.app.main import app

# --- Unit tests for categorize_tools_detailed ---


class FakeAdapter:
    def __init__(self, response: str):
        self._response = response

    async def generate_answer(self, _context, _prompt):
        return self._response


@pytest.mark.asyncio
async def test_categorize_tools_detailed_valid():
    llm_response = json.dumps(
        {
            "categories": {
                "Data Access": {
                    "description": "Tools for querying and reading data.",
                    "tools": ["query_db", "read_file"],
                },
                "User Management": {
                    "description": "Tools for managing users and roles.",
                    "tools": ["create_user"],
                },
            }
        }
    )
    adapter = FakeAdapter(llm_response)
    tools = [
        {"name": "query_db", "description": "Query the database"},
        {"name": "read_file", "description": "Read a file"},
        {"name": "create_user", "description": "Create a new user"},
    ]
    result = await categorize_tools_detailed(tools, adapter)
    assert len(result) == 2
    assert "Data Access" in result
    assert result["Data Access"]["tools"] == ["query_db", "read_file"]
    assert "querying" in result["Data Access"]["description"].lower()
    assert result["User Management"]["tools"] == ["create_user"]


@pytest.mark.asyncio
async def test_categorize_tools_detailed_with_markdown_wrapper():
    llm_response = '```json\n{"categories": {"Tools": {"description": "All tools.", "tools": ["a"]}}}\n```'
    adapter = FakeAdapter(llm_response)
    result = await categorize_tools_detailed([{"name": "a"}], adapter)
    assert "Tools" in result
    assert result["Tools"]["tools"] == ["a"]


@pytest.mark.asyncio
async def test_categorize_tools_detailed_invalid_response():
    adapter = FakeAdapter("I cannot parse this as JSON")
    result = await categorize_tools_detailed([{"name": "a"}], adapter)
    assert result == {}


@pytest.mark.asyncio
async def test_categorize_tools_detailed_empty_tools():
    llm_response = '{"categories": {}}'
    adapter = FakeAdapter(llm_response)
    result = await categorize_tools_detailed([], adapter)
    assert result == {}


@pytest.mark.asyncio
async def test_categorize_tools_detailed_tools_without_description():
    llm_response = json.dumps(
        {"categories": {"Misc": {"description": "Miscellaneous tools.", "tools": ["tool_a", "tool_b"]}}}
    )
    adapter = FakeAdapter(llm_response)
    tools = [{"name": "tool_a"}, {"name": "tool_b"}]
    result = await categorize_tools_detailed(tools, adapter)
    assert result["Misc"]["tools"] == ["tool_a", "tool_b"]


# --- Database CRUD tests ---


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    async def _noop():
        pass

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(db_module, "_migrate_tokens_json", _noop)
    monkeypatch.setattr(db_module, "_migrate_mcp_json", _noop)
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()
    yield
    await db_module.dispose_db()


@pytest.mark.asyncio
async def test_capability_analysis_crud(db):
    assert await db_module.get_capability_analysis("test-server") is None

    analysis_data = {
        "success": True,
        "categories": {
            "Data": {"description": "Data tools.", "tools": ["query"]},
        },
        "tool_count": 1,
        "category_count": 1,
        "llm_name": "gpt-4o",
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
    }
    await db_module.save_capability_analysis("test-server", analysis_data)

    stored = await db_module.get_capability_analysis("test-server")
    assert stored is not None
    assert stored["success"] is True
    assert stored["llm_name"] == "gpt-4o"
    assert stored["categories"]["Data"]["tools"] == ["query"]


@pytest.mark.asyncio
async def test_capability_analysis_upsert(db):
    data_v1 = {
        "categories": {"A": {"description": "First.", "tools": ["t1"]}},
        "tool_count": 1,
        "category_count": 1,
        "llm_name": "gpt-4o",
    }
    await db_module.save_capability_analysis("srv", data_v1)

    data_v2 = {
        "categories": {"B": {"description": "Second.", "tools": ["t2", "t3"]}},
        "tool_count": 2,
        "category_count": 1,
        "llm_name": "claude",
    }
    await db_module.save_capability_analysis("srv", data_v2)

    stored = await db_module.get_capability_analysis("srv")
    assert "A" not in stored["categories"]
    assert "B" in stored["categories"]
    assert stored["llm_name"] == "claude"
    assert stored["tool_count"] == 2


@pytest.mark.asyncio
async def test_capability_analysis_multiple_servers(db):
    for name in ("s1", "s2"):
        await db_module.save_capability_analysis(
            name, {"categories": {}, "tool_count": 0, "category_count": 0, "llm_name": f"llm-{name}"}
        )

    s1 = await db_module.get_capability_analysis("s1")
    s2 = await db_module.get_capability_analysis("s2")
    assert s1["llm_name"] == "llm-s1"
    assert s2["llm_name"] == "llm-s2"


# --- API Route Integration Tests ---


async def _noop_fn():
    pass


@pytest_asyncio.fixture
async def api_client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(db_module, "_migrate_tokens_json", _noop_fn)
    monkeypatch.setattr(db_module, "_migrate_mcp_json", _noop_fn)
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()
    await set_server_config("test-srv", {"url": "https://test.example.com/mcp", "enabled": True, "auth": False})
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    await db_module.dispose_db()


@pytest.mark.asyncio
async def test_api_get_cached_no_analysis(api_client):
    resp = api_client.get("/api/servers/test-srv/capabilities/analyze")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["exists"] is False


@pytest.mark.asyncio
async def test_api_get_cached_with_analysis(api_client):
    analysis = {
        "success": True,
        "categories": {"IO": {"description": "IO ops.", "tools": ["read"]}},
        "tool_count": 1,
        "category_count": 1,
        "llm_name": "test-llm",
    }
    await save_capability_analysis("test-srv", analysis)
    resp = api_client.get("/api/servers/test-srv/capabilities/analyze")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["exists"] is True
    assert data["llm_name"] == "test-llm"
    assert "IO" in data["categories"]


@pytest.mark.asyncio
async def test_api_analyze_no_tools(api_client):
    resp = api_client.post("/api/servers/test-srv/capabilities/analyze")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_analyze_no_llm_config(api_client, tmp_path):
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    tools_file = tools_dir / "test-srv.json"
    tools_file.write_text(json.dumps({"tools": [{"name": "t1"}]}))

    with (
        patch("src.app.routes.tools.load_tools", return_value={"tools": [{"name": "t1"}]}),
        patch("src.app.routes.tools.get_default_llm_name", return_value=None),
    ):
        resp = api_client.post("/api/servers/test-srv/capabilities/analyze")
    assert resp.status_code == 422
    assert "LLM configuration required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_analyze_unknown_llm(api_client):
    with (
        patch("src.app.routes.tools.load_tools", return_value={"tools": [{"name": "t1"}]}),
        patch("src.app.routes.tools.get_default_llm_name", return_value=None),
        patch("src.app.routes.tools.get_available_llm_configs", return_value={"default": {}}),
    ):
        resp = api_client.post("/api/servers/test-srv/capabilities/analyze?llm=nonexistent")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_analyze_success_saves_to_db(api_client):
    fake_adapter = FakeAdapter(json.dumps({"categories": {"Ops": {"description": "Operations.", "tools": ["deploy"]}}}))

    with (
        patch("src.app.routes.tools.load_tools", return_value={"tools": [{"name": "deploy", "description": "Deploy"}]}),
        patch("src.app.routes.tools.get_default_llm_name", return_value="test-llm"),
        patch(
            "src.app.routes.tools.get_available_llm_configs",
            return_value={"test-llm": {"provider": "test", "model": "test-model"}},
        ),
        patch("src.app.routes.tools.get_adapter_for_config", return_value=fake_adapter),
    ):
        resp = api_client.post("/api/servers/test-srv/capabilities/analyze")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["llm_name"] == "test-llm"
    assert "Ops" in data["categories"]

    stored = await db_module.get_capability_analysis("test-srv")
    assert stored is not None
    assert stored["llm_name"] == "test-llm"
    assert "Ops" in stored["categories"]


@pytest.mark.asyncio
async def test_api_analyze_with_specific_llm(api_client):
    fake_adapter = FakeAdapter(json.dumps({"categories": {"X": {"description": "X.", "tools": ["x1"]}}}))

    with (
        patch("src.app.routes.tools.load_tools", return_value={"tools": [{"name": "x1"}]}),
        patch(
            "src.app.routes.tools.get_available_llm_configs",
            return_value={"llm-a": {"provider": "a", "model": "m-a"}, "llm-b": {"provider": "b", "model": "m-b"}},
        ),
        patch("src.app.routes.tools.get_adapter_for_config", return_value=fake_adapter),
    ):
        resp = api_client.post("/api/servers/test-srv/capabilities/analyze?llm=llm-b")

    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_name"] == "llm-b"
    assert data["llm_provider"] == "b"


@pytest.mark.asyncio
async def test_api_reanalyze_overwrites(api_client):
    await save_capability_analysis(
        "test-srv",
        {
            "categories": {"Old": {"description": "Old.", "tools": ["old"]}},
            "tool_count": 1,
            "category_count": 1,
            "llm_name": "old-llm",
        },
    )

    fake_adapter = FakeAdapter(json.dumps({"categories": {"New": {"description": "New.", "tools": ["new"]}}}))

    with (
        patch("src.app.routes.tools.load_tools", return_value={"tools": [{"name": "new"}]}),
        patch("src.app.routes.tools.get_default_llm_name", return_value="new-llm"),
        patch(
            "src.app.routes.tools.get_available_llm_configs",
            return_value={"new-llm": {"provider": "new", "model": "new-m"}},
        ),
        patch("src.app.routes.tools.get_adapter_for_config", return_value=fake_adapter),
    ):
        resp = api_client.post("/api/servers/test-srv/capabilities/analyze")

    assert resp.status_code == 200
    assert resp.json()["llm_name"] == "new-llm"

    stored = await db_module.get_capability_analysis("test-srv")
    assert "Old" not in stored["categories"]
    assert "New" in stored["categories"]
    assert stored["llm_name"] == "new-llm"
