import asyncio

from src.app.eval.mock_server import BAD_TOOLS, GOOD_TOOLS, get_mock_tools, mock_call_fn


class TestMockTools:
    def test_good_tools_count(self):
        assert len(GOOD_TOOLS) == 4

    def test_bad_tools_count(self):
        assert len(BAD_TOOLS) == 4

    def test_get_mock_tools_default(self):
        tools = get_mock_tools()
        assert len(tools) == 4

    def test_get_mock_tools_with_bad(self):
        tools = get_mock_tools(include_bad=True)
        assert len(tools) == 8

    def test_good_tools_have_names(self):
        for t in GOOD_TOOLS:
            assert t["name"]

    def test_bad_tool_empty_name(self):
        assert BAD_TOOLS[0]["name"] == ""

    def test_bad_tool_no_description(self):
        assert "description" not in BAD_TOOLS[1]

    def test_bad_tool_readonly_on_delete(self):
        delete_tool = BAD_TOOLS[2]
        assert delete_tool["name"] == "delete_everything"
        assert delete_tool["annotations"]["readOnlyHint"] is True


class TestMockCallFn:
    def test_search_customers(self):
        result, latency = asyncio.get_event_loop().run_until_complete(
            mock_call_fn("search_customers", {})
        )
        assert "content" in result
        assert latency > 0

    def test_get_customer(self):
        result, _ = asyncio.get_event_loop().run_until_complete(
            mock_call_fn("get_customer", {"customer_id": "c1"})
        )
        assert result["id"] == "c1"

    def test_unknown_tool_raises(self):
        import pytest
        with pytest.raises(ValueError, match="Unknown tool"):
            asyncio.get_event_loop().run_until_complete(
                mock_call_fn("nonexistent", {})
            )
