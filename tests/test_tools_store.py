from src.app.tools_store import load_tools, save_tools


def test_save_and_load_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("src.app.tools_store.TOOLS_DIR", tmp_path)
    tools = [
        {"name": "search", "description": "Search things", "inputSchema": {"type": "object"}},
        {"name": "create", "description": "Create things"},
    ]
    path = save_tools("test-server", tools)
    assert path.exists()

    loaded = load_tools("test-server")
    assert len(loaded) == 2
    assert loaded[0]["name"] == "search"
    assert loaded[1]["name"] == "create"


def test_load_tools_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.app.tools_store.TOOLS_DIR", tmp_path)
    result = load_tools("nonexistent")
    assert result is None
