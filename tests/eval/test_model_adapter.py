import asyncio

import pytest

from src.app.eval.model_adapter import MockAdapter, get_adapter


class TestMockAdapter:
    def test_default_selects_first_tool(self):
        adapter = MockAdapter()
        tools = [{"name": "search"}, {"name": "delete"}]
        result = asyncio.get_event_loop().run_until_complete(
            adapter.select_tool(tools, "some prompt")
        )
        assert result["tool_name"] == "search"

    def test_custom_response(self):
        adapter = MockAdapter(responses={
            "find user": {"tool_name": "search_users", "arguments": {"name": "Alice"}},
        })
        tools = [{"name": "search_users"}]
        result = asyncio.get_event_loop().run_until_complete(
            adapter.select_tool(tools, "find user")
        )
        assert result["tool_name"] == "search_users"
        assert result["arguments"]["name"] == "Alice"

    def test_generate_answer(self):
        adapter = MockAdapter()
        result = asyncio.get_event_loop().run_until_complete(
            adapter.generate_answer({"data": "test"}, "summarize")
        )
        assert "test" in result

    def test_tracks_calls(self):
        adapter = MockAdapter()
        asyncio.get_event_loop().run_until_complete(
            adapter.select_tool([{"name": "a"}], "p1")
        )
        asyncio.get_event_loop().run_until_complete(
            adapter.generate_answer({}, "p2")
        )
        assert len(adapter.calls) == 2
        assert adapter.calls[0]["method"] == "select_tool"
        assert adapter.calls[1]["method"] == "generate_answer"

    def test_empty_tools_list(self):
        adapter = MockAdapter()
        result = asyncio.get_event_loop().run_until_complete(
            adapter.select_tool([], "prompt")
        )
        assert result["tool_name"] == ""


class TestGetAdapter:
    def test_mock(self):
        adapter = get_adapter("mock")
        assert isinstance(adapter, MockAdapter)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown adapter"):
            get_adapter("nonexistent")

    def test_anthropic_missing_package(self):
        import contextlib

        with contextlib.suppress(ImportError, ValueError):
            get_adapter("anthropic")

    def test_openai_missing_package(self):
        import contextlib

        with contextlib.suppress(ImportError, ValueError):
            get_adapter("openai")
