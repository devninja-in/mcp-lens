import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

import src.app.database as db_module
from src.app.database import set_server_config
from src.app.main import app


async def _noop():
    pass


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(db_module, "_migrate_tokens_json", _noop)
    monkeypatch.setattr(db_module, "_migrate_mcp_json", _noop)
    monkeypatch.setattr("src.app.tools_store.TOOLS_DIR", tmp_path / "tools")
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()
    await set_server_config("test-server", {
        "url": "https://example.com/mcp",
        "enabled": True,
        "auth": False,
    })
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    await db_module.dispose_db()


@pytest.mark.asyncio
async def test_get_tools_not_fetched(client):
    resp = client.get("/api/servers/test-server/tools")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_tools_missing_server(client):
    resp = client.get("/api/servers/nonexistent/tools")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_tools_success(client):
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    resp = client.get("/api/servers/test-server/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert data["server"] == "test-server"
    assert data["count"] == 2
    assert len(data["tools"]) == 2


# Sample tools for testing
SAMPLE_TOOLS = [
    {
        "name": "search_users",
        "description": "Search for users",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_profile",
        "description": "Get user profile",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# Ground truth upload tests
@pytest.mark.asyncio
async def test_upload_ground_truth_valid(client):
    import io

    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    yaml_content = """test_cases:
  - expected_tool_selection:
      - "search_users"
    prompts:
      - "Find all users named John"
  - expected_tool_selection:
      - "get_profile"
    prompts:
      - "Show me the profile"
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["test_case_count"] == 2
    assert data["prompt_count"] == 2


@pytest.mark.asyncio
async def test_upload_ground_truth_missing_test_cases_key(client):
    import io

    yaml_content = """other_key:
  - some: value
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "must contain a 'test_cases' key" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_test_cases_not_list(client):
    import io

    yaml_content = """test_cases:
  key: value
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "'test_cases' must be a list" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_invalid_test_case(client):
    import io

    yaml_content = """test_cases:
  - "not an object"
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "test_cases[0] must be an object" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_missing_fields(client):
    import io

    yaml_content = """test_cases:
  - expected_tool_selection:
      - "tool1"
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "must have 'expected_tool_selection' and 'prompts' fields" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_invalid_expected_tool_selection(client):
    import io

    yaml_content = """test_cases:
  - expected_tool_selection: "not a list"
    prompts:
      - "prompt"
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "expected_tool_selection must be a non-empty list of strings" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_empty_expected_tool_selection(client):
    import io

    yaml_content = """test_cases:
  - expected_tool_selection: []
    prompts:
      - "prompt"
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "expected_tool_selection must be a non-empty list of strings" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_empty_string_in_tools(client):
    import io

    yaml_content = """test_cases:
  - expected_tool_selection:
      - ""
    prompts:
      - "prompt"
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "expected_tool_selection must be a non-empty list of strings" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_invalid_prompts(client):
    import io

    yaml_content = """test_cases:
  - expected_tool_selection:
      - "tool1"
    prompts: "not a list"
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "prompts must be a non-empty list of strings" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_empty_prompts(client):
    import io

    yaml_content = """test_cases:
  - expected_tool_selection:
      - "tool1"
    prompts: []
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "prompts must be a non-empty list of strings" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_empty_string_in_prompts(client):
    import io

    yaml_content = """test_cases:
  - expected_tool_selection:
      - "tool1"
    prompts:
      - ""
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "prompts must be a non-empty list of strings" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_too_large(client):
    import io

    # Create a file larger than 1MB
    yaml_content = "test_cases:\n" + ("  - x: y\n" * 200000)
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "File too large" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_non_utf8(client):
    import io

    # Create invalid UTF-8 content
    file = io.BytesIO(b"\xff\xfe invalid utf-8")
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "must be valid UTF-8" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_invalid_yaml(client):
    import io

    yaml_content = """test_cases:
  - invalid: [unclosed
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 400
    assert "Invalid YAML" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_ground_truth_warning_tool_not_found(client):
    import io

    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    yaml_content = """test_cases:
  - expected_tool_selection:
      - "nonexistent_tool"
    prompts:
      - "Do something"
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    resp = client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["warnings"]) > 0
    assert "nonexistent_tool" in data["warnings"][0]


# Get ground truth tests
@pytest.mark.asyncio
async def test_get_ground_truth_exists(client):
    import io

    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    yaml_content = """test_cases:
  - expected_tool_selection:
      - "search_users"
    prompts:
      - "Find users"
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )

    resp = client.get("/api/servers/test-server/ground-truth")
    assert resp.status_code == 200
    data = resp.json()
    assert data["server_name"] == "test-server"
    assert data["test_case_count"] == 1
    assert data["prompt_count"] == 1
    assert len(data["test_cases"]) == 1


@pytest.mark.asyncio
async def test_get_ground_truth_not_exists(client):
    resp = client.get("/api/servers/test-server/ground-truth")
    assert resp.status_code == 404
    assert "No ground truth found" in resp.json()["detail"]


# Delete ground truth tests
@pytest.mark.asyncio
async def test_delete_ground_truth(client):
    import io

    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    yaml_content = """test_cases:
  - expected_tool_selection:
      - "search_users"
    prompts:
      - "Find users"
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )

    resp = client.delete("/api/servers/test-server/ground-truth")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Verify it's deleted
    resp = client.get("/api/servers/test-server/ground-truth")
    assert resp.status_code == 404


# Ground truth template tests
@pytest.mark.asyncio
async def test_get_ground_truth_template(client):
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    resp = client.get("/api/servers/test-server/ground-truth/template")
    assert resp.status_code == 200
    assert "yaml" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]

    import yaml
    data = yaml.safe_load(resp.content)
    assert "test_cases" in data
    assert len(data["test_cases"]) == 2


@pytest.mark.asyncio
async def test_get_ground_truth_template_no_tools(client):
    resp = client.get("/api/servers/test-server/ground-truth/template")
    assert resp.status_code == 404
    assert "No tools found" in resp.json()["detail"]


# Evaluate tests
@pytest.mark.asyncio
async def test_evaluate(client):
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    resp = client.get("/api/servers/test-server/evaluate")
    assert resp.status_code == 200
    data = resp.json()
    assert "server_summary" in data or "tools" in data


@pytest.mark.asyncio
async def test_evaluate_full(client):
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    resp = client.get("/api/servers/test-server/evaluate/full")
    assert resp.status_code == 200
    data = resp.json()
    assert "layers" in data
    assert "overall_score" in data
    assert "gate_passed" in data


@pytest.mark.asyncio
async def test_get_eval_report_not_exists(client):
    resp = client.get("/api/servers/test-server/evaluate/report")
    assert resp.status_code == 404
    assert "No evaluation report found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_eval_report_exists(client):
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    # Generate a report first
    client.get("/api/servers/test-server/evaluate/full")

    resp = client.get("/api/servers/test-server/evaluate/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "layers" in data


# False positive tests
@pytest.mark.asyncio
async def test_mark_false_positive(client):
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    # Generate a report first
    client.get("/api/servers/test-server/evaluate/full")

    resp = client.post(
        "/api/servers/test-server/evaluate/false-positive",
        json={"check_key": "test_check", "justification": "This is a false positive"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "test_check" in data["false_positives"]
    assert data["false_positives"]["test_check"] == "This is a false positive"


@pytest.mark.asyncio
async def test_mark_false_positive_remove(client):
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    # Generate a report first
    client.get("/api/servers/test-server/evaluate/full")

    # Add a false positive
    client.post(
        "/api/servers/test-server/evaluate/false-positive",
        json={"check_key": "test_check", "justification": "This is a false positive"},
    )

    # Remove it by setting justification to None
    resp = client.post(
        "/api/servers/test-server/evaluate/false-positive",
        json={"check_key": "test_check", "justification": None},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "test_check" not in data["false_positives"]


# Test connection tests
@pytest.mark.asyncio
async def test_test_connection_success(client, monkeypatch):
    async def mock_initialize(name, config):
        return {
            "result": {
                "serverInfo": {
                    "name": "test-server",
                    "version": "1.0.0",
                }
            }
        }, None

    monkeypatch.setattr("src.app.routes.tools.mcp_initialize", mock_initialize)

    resp = client.post("/api/servers/test-server/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "server_info" in data


@pytest.mark.asyncio
async def test_test_connection_error(client, monkeypatch):
    async def mock_initialize(name, config):
        return {"error": "Connection failed"}, None

    monkeypatch.setattr("src.app.routes.tools.mcp_initialize", mock_initialize)

    resp = client.post("/api/servers/test-server/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "MCP error" in data["message"]


@pytest.mark.asyncio
async def test_test_connection_exception(client, monkeypatch):
    async def mock_initialize(name, config):
        raise Exception("Network error")

    monkeypatch.setattr("src.app.routes.tools.mcp_initialize", mock_initialize)

    resp = client.post("/api/servers/test-server/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_test_connection_reauth_required(client, monkeypatch):
    from src.app.mcp_client import ReAuthRequiredError

    async def mock_initialize(name, config):
        raise ReAuthRequiredError("Need to re-authenticate")

    monkeypatch.setattr("src.app.routes.tools.mcp_initialize", mock_initialize)

    resp = client.post("/api/servers/test-server/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data.get("reauth") is True


@pytest.mark.asyncio
async def test_test_connection_server_not_found(client):
    resp = client.post("/api/servers/nonexistent/test")
    assert resp.status_code == 404


# Fetch tools tests
@pytest.mark.asyncio
async def test_fetch_tools_success(client, monkeypatch):
    async def mock_list_tools(name, config):
        return SAMPLE_TOOLS

    monkeypatch.setattr("src.app.routes.tools.mcp_list_tools", mock_list_tools)

    resp = client.post("/api/servers/test-server/fetch-tools")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 2
    assert len(data["tools"]) == 2


@pytest.mark.asyncio
async def test_fetch_tools_exception(client, monkeypatch):
    async def mock_list_tools(name, config):
        raise Exception("Failed to connect")

    monkeypatch.setattr("src.app.routes.tools.mcp_list_tools", mock_list_tools)

    resp = client.post("/api/servers/test-server/fetch-tools")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_fetch_tools_reauth_required(client, monkeypatch):
    from src.app.mcp_client import ReAuthRequiredError

    async def mock_list_tools(name, config):
        raise ReAuthRequiredError("Need to re-authenticate")

    monkeypatch.setattr("src.app.routes.tools.mcp_list_tools", mock_list_tools)

    resp = client.post("/api/servers/test-server/fetch-tools")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data.get("reauth") is True
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_fetch_tools_server_not_found(client):
    resp = client.post("/api/servers/nonexistent/fetch-tools")
    assert resp.status_code == 404


# LLM evaluation tests
@pytest.mark.asyncio
async def test_evaluate_llm_no_config(client, monkeypatch):
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    # Mock load_llm_config to return None
    monkeypatch.setattr("src.app.routes.tools.load_llm_config", lambda: None)
    monkeypatch.setattr("src.app.routes.tools.get_default_llm_name", lambda: None)

    resp = client.get("/api/servers/test-server/evaluate/llm")
    assert resp.status_code == 404
    assert "LLM evaluation not configured" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_evaluate_llm_with_mock_adapter(client, monkeypatch):
    from src.app.eval.model_adapter import MockAdapter
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    # Mock LLM config
    monkeypatch.setattr("src.app.routes.tools.load_llm_config", lambda: {
        "provider": "mock",
        "model": None,
        "api_key": None,
        "project": None,
        "location": None,
        "base_url": None,
    })
    monkeypatch.setattr("src.app.routes.tools.get_eval_adapter", lambda: MockAdapter())

    resp = client.get("/api/servers/test-server/evaluate/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert "layer" in data
    assert "overall_score" in data
    assert "metadata" in data


@pytest.mark.asyncio
async def test_evaluate_llm_with_ground_truth(client, monkeypatch):
    import io

    from src.app.eval.model_adapter import MockAdapter
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    # Upload ground truth first
    yaml_content = """test_cases:
  - expected_tool_selection:
      - "search_users"
    prompts:
      - "Find all users"
"""
    file = io.BytesIO(yaml_content.encode("utf-8"))
    client.post(
        "/api/servers/test-server/ground-truth",
        files={"file": ("test.yaml", file, "application/x-yaml")},
    )

    # Mock LLM config
    monkeypatch.setattr("src.app.routes.tools.load_llm_config", lambda: {
        "provider": "mock",
        "model": None,
        "api_key": None,
        "project": None,
        "location": None,
        "base_url": None,
    })
    monkeypatch.setattr("src.app.routes.tools.get_eval_adapter", lambda: MockAdapter())

    resp = client.get("/api/servers/test-server/evaluate/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["ground_truth_loaded"] is True


@pytest.mark.asyncio
async def test_evaluate_llm_multi_llm(client, monkeypatch):
    from src.app.eval.model_adapter import MockAdapter
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    # Mock multiple LLM configs
    def mock_get_adapter_for_config(name):
        return MockAdapter()

    def mock_get_available_llm_configs():
        return {
            "config1": {"provider": "mock", "model": "model1"},
            "config2": {"provider": "mock", "model": "model2"},
        }

    monkeypatch.setattr("src.app.routes.tools.get_adapter_for_config", mock_get_adapter_for_config)
    monkeypatch.setattr("src.app.routes.tools.get_available_llm_configs", mock_get_available_llm_configs)
    monkeypatch.setattr("src.app.routes.tools.get_default_llm_name", lambda: None)

    resp = client.get("/api/servers/test-server/evaluate/llm?llms=config1,config2")
    assert resp.status_code == 200
    data = resp.json()
    assert "per_llm" in data
    assert "config1" in data["per_llm"]
    assert "config2" in data["per_llm"]


@pytest.mark.asyncio
async def test_evaluate_llm_with_default_llm_name(client, monkeypatch):
    from src.app.eval.model_adapter import MockAdapter
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    # Mock default LLM name
    def mock_get_adapter_for_config(name):
        return MockAdapter()

    def mock_get_available_llm_configs():
        return {"default-config": {"provider": "mock", "model": "model1"}}

    monkeypatch.setattr("src.app.routes.tools.get_adapter_for_config", mock_get_adapter_for_config)
    monkeypatch.setattr("src.app.routes.tools.get_available_llm_configs", mock_get_available_llm_configs)
    monkeypatch.setattr("src.app.routes.tools.get_default_llm_name", lambda: "default-config")

    resp = client.get("/api/servers/test-server/evaluate/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert "per_llm" in data


@pytest.mark.asyncio
async def test_evaluate_llm_adapter_error(client, monkeypatch):
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    # Mock adapter creation to fail
    def mock_get_adapter_for_config(name):
        raise ValueError("Invalid adapter config")

    def mock_get_available_llm_configs():
        return {"bad-config": {"provider": "invalid"}}

    monkeypatch.setattr("src.app.routes.tools.get_adapter_for_config", mock_get_adapter_for_config)
    monkeypatch.setattr("src.app.routes.tools.get_available_llm_configs", mock_get_available_llm_configs)
    monkeypatch.setattr("src.app.routes.tools.get_default_llm_name", lambda: None)

    resp = client.get("/api/servers/test-server/evaluate/llm?llms=bad-config")
    assert resp.status_code == 200
    data = resp.json()
    assert "per_llm" in data
    assert "bad-config" in data["per_llm"]
    assert "error" in data["per_llm"]["bad-config"]


@pytest.mark.asyncio
async def test_evaluate_llm_import_error(client, monkeypatch):
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    # Mock to raise ImportError
    def mock_get_eval_adapter():
        raise ImportError("anthropic package not installed")

    monkeypatch.setattr("src.app.routes.tools.load_llm_config", lambda: {
        "provider": "anthropic",
        "model": "claude-3-5-sonnet-20241022",
        "api_key": None,
        "project": None,
        "location": None,
        "base_url": None,
    })
    monkeypatch.setattr("src.app.routes.tools.get_eval_adapter", mock_get_eval_adapter)
    monkeypatch.setattr("src.app.routes.tools.get_default_llm_name", lambda: None)

    resp = client.get("/api/servers/test-server/evaluate/llm")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_evaluate_llm_execution_error(client, monkeypatch):
    from src.app.eval.model_adapter import MockAdapter
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    # Mock adapter that raises an error during evaluation
    class FailingAdapter(MockAdapter):
        async def select_tool(self, tools, user_prompt):
            raise RuntimeError("LLM API error")

    monkeypatch.setattr("src.app.routes.tools.load_llm_config", lambda: {
        "provider": "mock",
        "model": None,
        "api_key": None,
        "project": None,
        "location": None,
        "base_url": None,
    })
    monkeypatch.setattr("src.app.routes.tools.get_eval_adapter", lambda: FailingAdapter())

    resp = client.get("/api/servers/test-server/evaluate/llm")
    assert resp.status_code == 200
    data = resp.json()
    # The LLM layer handles errors gracefully, so we should get a result
    assert "layer" in data or "metadata" in data


@pytest.mark.asyncio
async def test_evaluate_llm_tools_not_found(client):
    resp = client.get("/api/servers/test-server/evaluate/llm")
    assert resp.status_code == 404
    assert "No tools found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_evaluate_full_no_tools(client):
    resp = client.get("/api/servers/test-server/evaluate/full")
    assert resp.status_code == 404
    assert "No tools found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_mark_false_positive_no_report(client):
    resp = client.post(
        "/api/servers/test-server/evaluate/false-positive",
        json={"check_key": "test_check", "justification": "This is a false positive"},
    )
    assert resp.status_code == 404
    assert "No evaluation report found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_evaluate_no_tools(client):
    resp = client.get("/api/servers/test-server/evaluate")
    assert resp.status_code == 404
    assert "No tools found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_fetch_tools_oauth_clears_tokens(client, monkeypatch):
    from src.app.database import set_server_config

    await set_server_config("oauth-server", {
        "url": "https://example.com/mcp",
        "enabled": True,
        "auth": True,
        "auth_mode": "oauth",
    })

    async def mock_list_tools(name, config):
        return SAMPLE_TOOLS

    cleared = []

    async def mock_clear(name):
        cleared.append(name)

    monkeypatch.setattr("src.app.routes.tools.mcp_list_tools", mock_list_tools)
    monkeypatch.setattr("src.app.routes.tools.persist_oauth_tokens", lambda: False)
    monkeypatch.setattr("src.app.routes.tools.clear_oauth_tokens", mock_clear)

    resp = client.post("/api/servers/oauth-server/fetch-tools")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert "oauth-server" in cleared


@pytest.mark.asyncio
async def test_evaluate_full_with_overlapping_tools(client):
    from src.app.tools_store import save_tools

    overlapping_tools = [
        {"name": "search_users", "description": "Search for users by name or email address",
         "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}}},
        {"name": "find_users", "description": "Find users by name or email address",
         "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}}},
    ]
    save_tools("test-server", overlapping_tools)

    resp = client.get("/api/servers/test-server/evaluate/full")
    assert resp.status_code == 200
    data = resp.json()
    assert "layers" in data


@pytest.mark.asyncio
async def test_evaluate_llm_with_server_description(client, monkeypatch):
    from src.app.database import set_server_config
    from src.app.eval.model_adapter import MockAdapter
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)
    await set_server_config("test-server", {
        "url": "https://example.com/mcp",
        "enabled": True,
        "auth": False,
        "description": "Atlassian MCP server for Confluence and Jira",
    })

    monkeypatch.setattr("src.app.routes.tools.load_llm_config", lambda: {
        "provider": "mock", "model": None, "api_key": None,
        "project": None, "location": None, "base_url": None,
    })
    monkeypatch.setattr("src.app.routes.tools.get_eval_adapter", lambda: MockAdapter())

    resp = client.get("/api/servers/test-server/evaluate/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert "layer" in data


@pytest.mark.asyncio
async def test_evaluate_llm_adapter_returns_none(client, monkeypatch):
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    monkeypatch.setattr("src.app.routes.tools.load_llm_config", lambda: {
        "provider": "mock", "model": None, "api_key": None,
        "project": None, "location": None, "base_url": None,
    })
    monkeypatch.setattr("src.app.routes.tools.get_eval_adapter", lambda: None)
    monkeypatch.setattr("src.app.routes.tools.get_default_llm_name", lambda: None)

    resp = client.get("/api/servers/test-server/evaluate/llm")
    assert resp.status_code == 500
    assert "Failed to create LLM adapter" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_evaluate_llm_single_with_overlapping_tools(client, monkeypatch):
    from src.app.eval.model_adapter import MockAdapter
    from src.app.tools_store import save_tools

    overlapping_tools = [
        {"name": "search_users", "description": "Search for users by name or email address",
         "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}}},
        {"name": "find_users", "description": "Find users by name or email address",
         "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}}},
    ]
    save_tools("test-server", overlapping_tools)

    monkeypatch.setattr("src.app.routes.tools.load_llm_config", lambda: {
        "provider": "mock", "model": None, "api_key": None,
        "project": None, "location": None, "base_url": None,
    })
    monkeypatch.setattr("src.app.routes.tools.get_eval_adapter", lambda: MockAdapter())
    monkeypatch.setattr("src.app.routes.tools.get_default_llm_name", lambda: None)

    resp = client.get("/api/servers/test-server/evaluate/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert "layer" in data


@pytest.mark.asyncio
async def test_evaluate_llm_single_exception_handler(client, monkeypatch):
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    monkeypatch.setattr("src.app.routes.tools.load_llm_config", lambda: {
        "provider": "mock", "model": None, "api_key": None,
        "project": None, "location": None, "base_url": None,
    })
    monkeypatch.setattr("src.app.routes.tools.get_eval_adapter", lambda: "not_an_adapter")
    monkeypatch.setattr("src.app.routes.tools.get_default_llm_name", lambda: None)
    monkeypatch.setattr("src.app.routes.tools.check_llm_all", _raise_runtime_error)

    resp = client.get("/api/servers/test-server/evaluate/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert "metadata" in data
    assert "llm_error" in data["metadata"]


@pytest.mark.asyncio
async def test_evaluate_llm_multi_exception_handler(client, monkeypatch):
    from src.app.eval.model_adapter import MockAdapter
    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    async def mock_check_llm_all_error(*args, **kwargs):
        raise RuntimeError("LLM crashed")

    monkeypatch.setattr("src.app.routes.tools.get_adapter_for_config", lambda name: MockAdapter())
    monkeypatch.setattr("src.app.routes.tools.get_available_llm_configs", lambda: {"cfg1": {"provider": "mock"}})
    monkeypatch.setattr("src.app.routes.tools.get_default_llm_name", lambda: None)
    monkeypatch.setattr("src.app.routes.tools.check_llm_all", mock_check_llm_all_error)

    resp = client.get("/api/servers/test-server/evaluate/llm?llms=cfg1")
    assert resp.status_code == 200
    data = resp.json()
    assert "per_llm" in data
    assert "error" in data["per_llm"]["cfg1"]


@pytest.mark.asyncio
async def test_evaluate_llm_multi_with_overlapping_tools(client, monkeypatch):
    from src.app.eval.model_adapter import MockAdapter
    from src.app.tools_store import save_tools

    overlapping_tools = [
        {"name": "search_users", "description": "Search for users by name or email address",
         "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}}},
        {"name": "find_users", "description": "Find users by name or email address",
         "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}}},
    ]
    save_tools("test-server", overlapping_tools)

    monkeypatch.setattr("src.app.routes.tools.get_adapter_for_config", lambda name: MockAdapter())
    monkeypatch.setattr(
        "src.app.routes.tools.get_available_llm_configs",
        lambda: {"cfg1": {"provider": "mock", "model": "m1"}},
    )
    monkeypatch.setattr("src.app.routes.tools.get_default_llm_name", lambda: None)

    resp = client.get("/api/servers/test-server/evaluate/llm?llms=cfg1")
    assert resp.status_code == 200
    data = resp.json()
    assert "per_llm" in data


async def _raise_runtime_error(*args, **kwargs):
    raise RuntimeError("Simulated crash")


@pytest.mark.asyncio
async def test_evaluate_llm_single_http_exception_reraise(client, monkeypatch):
    from fastapi import HTTPException

    from src.app.tools_store import save_tools

    save_tools("test-server", SAMPLE_TOOLS)

    monkeypatch.setattr("src.app.routes.tools.load_llm_config", lambda: {
        "provider": "mock", "model": None, "api_key": None,
        "project": None, "location": None, "base_url": None,
    })
    monkeypatch.setattr("src.app.routes.tools.get_eval_adapter", lambda: "dummy")
    monkeypatch.setattr("src.app.routes.tools.get_default_llm_name", lambda: None)

    async def raise_http(*args, **kwargs):
        raise HTTPException(status_code=503, detail="Service Unavailable")

    monkeypatch.setattr("src.app.routes.tools.check_llm_all", raise_http)

    resp = client.get("/api/servers/test-server/evaluate/llm")
    assert resp.status_code == 503
    assert "Service Unavailable" in resp.json()["detail"]
