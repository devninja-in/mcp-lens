import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

import src.app.database as db_module
from src.app.database import save_comparison_report, set_server_config
from src.app.eval.comparison import (
    build_category_coverage,
    compare_capabilities,
    compare_eval_scores,
    diff_schemas,
    diff_tool_inventories,
)
from src.app.main import app


def test_diff_tool_inventories_basic():
    tools_a = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    tools_b = [{"name": "b"}, {"name": "c"}, {"name": "d"}]
    result = diff_tool_inventories(tools_a, tools_b)
    assert result["only_a"] == ["a"]
    assert result["only_b"] == ["d"]
    assert result["common"] == ["b", "c"]
    assert result["count_a"] == 3
    assert result["count_b"] == 3


def test_diff_tool_inventories_no_overlap():
    tools_a = [{"name": "x"}]
    tools_b = [{"name": "y"}]
    result = diff_tool_inventories(tools_a, tools_b)
    assert result["only_a"] == ["x"]
    assert result["only_b"] == ["y"]
    assert result["common"] == []


def test_diff_tool_inventories_identical():
    tools = [{"name": "a"}, {"name": "b"}]
    result = diff_tool_inventories(tools, tools)
    assert result["only_a"] == []
    assert result["only_b"] == []
    assert result["common"] == ["a", "b"]


def test_diff_tool_inventories_empty():
    result = diff_tool_inventories([], [])
    assert result["only_a"] == []
    assert result["only_b"] == []
    assert result["common"] == []
    assert result["count_a"] == 0
    assert result["count_b"] == 0


def test_compare_capabilities_both_present():
    init_a = {"result": {"capabilities": {"tools": {}, "resources": {}}, "serverInfo": {"name": "A", "version": "1.0"}}}
    init_b = {"result": {"capabilities": {"tools": {}}, "serverInfo": {"name": "B", "version": "2.0"}}}
    result = compare_capabilities(init_a, init_b)
    assert result is not None
    assert result["server_a"]["serverInfo"]["name"] == "A"
    assert result["server_b"]["serverInfo"]["name"] == "B"
    matrix = {row["capability"]: row for row in result["capability_matrix"]}
    assert matrix["tools"]["server_a"] is True
    assert matrix["tools"]["server_b"] is True
    assert matrix["resources"]["server_a"] is True
    assert matrix["resources"]["server_b"] is False


def test_compare_capabilities_none_input():
    assert compare_capabilities(None, {"result": {}}) is None
    assert compare_capabilities({"result": {}}, None) is None
    assert compare_capabilities(None, None) is None


def test_diff_schemas_identical():
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    tools_a = [{"name": "search", "inputSchema": schema}]
    tools_b = [{"name": "search", "inputSchema": schema}]
    result = diff_schemas(tools_a, tools_b, ["search"])
    assert len(result) == 1
    assert result[0]["tool_name"] == "search"
    assert result[0]["identical"] is True
    assert result[0]["differences"] == []


def test_diff_schemas_different():
    tools_a = [{"name": "search", "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}}]
    tools_b = [{"name": "search", "inputSchema": {"type": "object", "properties": {"q": {"type": "integer"}}}}]
    result = diff_schemas(tools_a, tools_b, ["search"])
    assert len(result) == 1
    assert result[0]["identical"] is False
    assert len(result[0]["differences"]) == 1
    diff = result[0]["differences"][0]
    assert diff["path"] == "$.properties.q.type"
    assert diff["server_a"] == "string"
    assert diff["server_b"] == "integer"


def test_diff_schemas_missing_key():
    schema_a = {"type": "object", "properties": {"a": {"type": "string"}}}
    schema_b = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "number"}}}
    tools_a = [{"name": "t", "inputSchema": schema_a}]
    tools_b = [{"name": "t", "inputSchema": schema_b}]
    result = diff_schemas(tools_a, tools_b, ["t"])
    assert result[0]["identical"] is False
    paths = [d["path"] for d in result[0]["differences"]]
    assert "$.properties.b" in paths


def test_diff_schemas_empty_common():
    result = diff_schemas([], [], [])
    assert result == []


def test_compare_eval_scores_both_present():
    report_a = {"overall_score": 82.5, "layers": {"protocol": {"score": 90}, "quality": {"score": 75}}}
    report_b = {"overall_score": 71.0, "layers": {"protocol": {"score": 85}, "security": {"score": 60}}}
    result = compare_eval_scores(report_a, report_b)
    assert result["server_a_score"] == 82.5
    assert result["server_b_score"] == 71.0
    assert result["layers"]["protocol"]["server_a"] == 90
    assert result["layers"]["protocol"]["server_b"] == 85
    assert result["layers"]["quality"]["server_a"] == 75
    assert result["layers"]["quality"]["server_b"] is None
    assert result["layers"]["security"]["server_a"] is None
    assert result["layers"]["security"]["server_b"] == 60


def test_compare_eval_scores_one_missing():
    report_a = {"overall_score": 80, "layers": {"protocol": {"score": 90}}}
    result = compare_eval_scores(report_a, None)
    assert result["server_a_score"] == 80
    assert result["server_b_score"] is None
    assert result["layers"]["protocol"]["server_b"] is None


def test_compare_eval_scores_both_missing():
    result = compare_eval_scores(None, None)
    assert result["server_a_score"] is None
    assert result["server_b_score"] is None
    assert result["layers"] == {}


def test_build_category_coverage():
    cats_a = {"Auth": ["login", "logout"], "Data": ["query"]}
    cats_b = {"Auth": ["login"], "Reporting": ["export"]}
    result = build_category_coverage(cats_a, cats_b)
    by_cat = {r["category"]: r for r in result}
    assert len(by_cat) == 3
    assert by_cat["Auth"]["server_a_count"] == 2
    assert by_cat["Auth"]["server_b_count"] == 1
    assert by_cat["Data"]["server_a_count"] == 1
    assert by_cat["Data"]["server_b_count"] == 0
    assert by_cat["Reporting"]["server_a_count"] == 0
    assert by_cat["Reporting"]["server_b_count"] == 1


def test_build_category_coverage_empty():
    result = build_category_coverage({}, {})
    assert result == []


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
async def test_comparison_report_crud(db):
    report_data = {"server_a": "s1", "server_b": "s2", "tool_inventory": {}}

    assert await db_module.get_comparison_report("s1", "s2") is None

    row_id = await db_module.save_comparison_report("s1", "s2", report_data)
    assert row_id > 0

    stored = await db_module.get_comparison_report("s1", "s2")
    assert stored is not None
    assert stored["server_a"] == "s1"

    stored_reversed = await db_module.get_comparison_report("s2", "s1")
    assert stored_reversed is not None
    assert stored_reversed["server_a"] == "s1"

    reports = await db_module.list_comparison_reports()
    assert len(reports) == 1
    assert reports[0]["server_a"] == "s1"
    assert reports[0]["server_b"] == "s2"

    updated_data = {"server_a": "s1", "server_b": "s2", "updated": True}
    row_id2 = await db_module.save_comparison_report("s2", "s1", updated_data)
    assert row_id2 == row_id

    stored2 = await db_module.get_comparison_report("s1", "s2")
    assert stored2["updated"] is True

    deleted = await db_module.delete_comparison_report(row_id)
    assert deleted is True

    assert await db_module.get_comparison_report("s1", "s2") is None

    deleted_again = await db_module.delete_comparison_report(row_id)
    assert deleted_again is False


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
    for name in ("server-a", "server-b"):
        await set_server_config(name, {"url": f"https://{name}.example.com/mcp", "enabled": True, "auth": False})
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    await db_module.dispose_db()


@pytest.mark.asyncio
async def test_api_check_no_report(api_client):
    resp = api_client.get("/api/compare", params={"server_a": "server-a", "server_b": "server-b"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is False
    assert data["report"] is None


@pytest.mark.asyncio
async def test_api_check_stored_report(api_client):
    report = {"server_a": "server-a", "server_b": "server-b", "timestamp": "2025-01-01T00:00:00"}
    await save_comparison_report("server-a", "server-b", report)
    resp = api_client.get("/api/compare", params={"server_a": "server-a", "server_b": "server-b"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["report"]["server_a"] == "server-a"


@pytest.mark.asyncio
async def test_api_check_reversed_pair(api_client):
    report = {"server_a": "server-a", "server_b": "server-b", "timestamp": "2025-01-01T00:00:00"}
    await save_comparison_report("server-a", "server-b", report)
    resp = api_client.get("/api/compare", params={"server_a": "server-b", "server_b": "server-a"})
    assert resp.status_code == 200
    assert resp.json()["exists"] is True


@pytest.mark.asyncio
async def test_api_list_comparisons(api_client):
    report = {"server_a": "server-a", "server_b": "server-b", "timestamp": "2025-01-01T00:00:00"}
    await save_comparison_report("server-a", "server-b", report)
    resp = api_client.get("/api/compare/list")
    assert resp.status_code == 200
    reports = resp.json()["reports"]
    assert len(reports) >= 1
    assert reports[0]["server_a"] == "server-a"


@pytest.mark.asyncio
async def test_api_delete_comparison(api_client):
    report = {"server_a": "server-a", "server_b": "server-b", "timestamp": "2025-01-01T00:00:00"}
    report_id = await save_comparison_report("server-a", "server-b", report)
    resp = api_client.delete(f"/api/compare/{report_id}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    resp2 = api_client.get("/api/compare", params={"server_a": "server-a", "server_b": "server-b"})
    assert resp2.json()["exists"] is False


@pytest.mark.asyncio
async def test_api_delete_nonexistent(api_client):
    resp = api_client.delete("/api/compare/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_compare_same_server(api_client):
    resp = api_client.post("/api/compare", json={"server_a": "server-a", "server_b": "server-a"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_compare_unknown_server(api_client):
    resp = api_client.post("/api/compare", json={"server_a": "server-a", "server_b": "nonexistent"})
    assert resp.status_code == 404
