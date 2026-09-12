from src.app.tools_store import delete_tools, load_tools, save_tools


def test_save_and_load_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("src.app.tools_store.TOOLS_DIR", tmp_path)
    tools = [
        {"name": "search", "description": "Search things", "inputSchema": {"type": "object"}},
        {"name": "create", "description": "Create things"},
    ]
    path = save_tools("test-server", tools)
    assert path.exists()

    result = load_tools("test-server")
    assert result is not None
    assert result["source"] == "fetched"
    assert len(result["tools"]) == 2
    assert result["tools"][0]["name"] == "search"
    assert result["tools"][1]["name"] == "create"


def test_save_tools_uploaded(tmp_path, monkeypatch):
    monkeypatch.setattr("src.app.tools_store.TOOLS_DIR", tmp_path)
    tools = [{"name": "my_tool", "description": "A tool"}]
    save_tools("test-server", tools, source="uploaded")

    result = load_tools("test-server")
    assert result is not None
    assert result["source"] == "uploaded"
    assert len(result["tools"]) == 1


def test_delete_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("src.app.tools_store.TOOLS_DIR", tmp_path)
    save_tools("test-server", [{"name": "t"}])
    assert delete_tools("test-server") is True
    assert load_tools("test-server") is None
    assert delete_tools("test-server") is False


def test_load_tools_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.app.tools_store.TOOLS_DIR", tmp_path)
    result = load_tools("nonexistent")
    assert result is None
