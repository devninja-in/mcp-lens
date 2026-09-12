from src.app.eval.models import Status
from src.app.eval.quality import (
    check_quality_all,
    check_tool_quality,
    evaluate_tools_compat,
)


def _tool(**overrides):
    base = {"name": "get_users", "description": "Get all users from the database and return them as a list"}
    base.update(overrides)
    return base


class TestDescActionable:
    def test_verb_present(self):
        checks = check_tool_quality(_tool(description="Search for users in the database"))
        c = next(c for c in checks if c.check_id == "quality.desc_actionable")
        assert c.status == Status.PASS

    def test_no_verb(self):
        checks = check_tool_quality(_tool(description="Users in the database"))
        c = next(c for c in checks if c.check_id == "quality.desc_actionable")
        assert c.status == Status.WARN

    def test_empty_desc(self):
        checks = check_tool_quality(_tool(description=""))
        c = next(c for c in checks if c.check_id == "quality.desc_actionable")
        assert c.status == Status.FAIL


class TestDescLength:
    def test_short(self):
        checks = check_tool_quality(_tool(description="Short"))
        c = next(c for c in checks if c.check_id == "quality.desc_adequate_length")
        assert c.status == Status.WARN

    def test_adequate(self):
        checks = check_tool_quality(_tool(description="Search for users and return a list of matching results"))
        c = next(c for c in checks if c.check_id == "quality.desc_adequate_length")
        assert c.status == Status.PASS

    def test_missing(self):
        checks = check_tool_quality(_tool(description=None))
        c = next(c for c in checks if c.check_id == "quality.desc_adequate_length")
        assert c.status == Status.FAIL


class TestDescNoFiller:
    def test_clean(self):
        checks = check_tool_quality(_tool(description="Search for matching users"))
        c = next(c for c in checks if c.check_id == "quality.desc_no_filler")
        assert c.status == Status.PASS

    def test_generic_filler(self):
        checks = check_tool_quality(_tool(description="This tool searches for users"))
        c = next(c for c in checks if c.check_id == "quality.desc_no_filler")
        assert c.status == Status.WARN


class TestParamDescriptions:
    def test_all_described(self):
        tool = _tool(inputSchema={
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Query string"},
                "limit": {"type": "integer", "description": "Max results"},
            },
        })
        checks = check_tool_quality(tool)
        c = next(c for c in checks if c.check_id == "quality.param_all_described")
        assert c.status == Status.PASS

    def test_some_missing(self):
        tool = _tool(inputSchema={
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Query string"},
                "limit": {"type": "integer"},
            },
        })
        checks = check_tool_quality(tool)
        c = next(c for c in checks if c.check_id == "quality.param_all_described")
        assert c.status == Status.WARN
        assert "limit" in c.details.get("missing", [])


class TestParamTypes:
    def test_all_typed(self):
        tool = _tool(inputSchema={
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "limit": {"type": "integer"},
            },
        })
        checks = check_tool_quality(tool)
        c = next(c for c in checks if c.check_id == "quality.param_all_typed")
        assert c.status == Status.PASS

    def test_missing_types(self):
        tool = _tool(inputSchema={
            "type": "object",
            "properties": {
                "q": {"description": "Query"},
            },
        })
        checks = check_tool_quality(tool)
        c = next(c for c in checks if c.check_id == "quality.param_all_typed")
        assert c.status == Status.WARN

    def test_anyof_counts(self):
        tool = _tool(inputSchema={
            "type": "object",
            "properties": {
                "value": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            },
        })
        checks = check_tool_quality(tool)
        c = next(c for c in checks if c.check_id == "quality.param_all_typed")
        assert c.status == Status.PASS


class TestNaming:
    def test_snake_case_verb(self):
        checks = check_tool_quality(_tool(name="get_users"))
        consistent = next(c for c in checks if c.check_id == "quality.naming_consistent")
        verb = next(c for c in checks if c.check_id == "quality.naming_verb_prefix")
        assert consistent.status == Status.PASS
        assert verb.status == Status.PASS

    def test_camel_case_verb(self):
        checks = check_tool_quality(_tool(name="getUsers"))
        consistent = next(c for c in checks if c.check_id == "quality.naming_consistent")
        verb = next(c for c in checks if c.check_id == "quality.naming_verb_prefix")
        assert consistent.status == Status.PASS
        assert verb.status == Status.PASS

    def test_bad_case(self):
        checks = check_tool_quality(_tool(name="Get_Users"))
        consistent = next(c for c in checks if c.check_id == "quality.naming_consistent")
        assert consistent.status == Status.WARN

    def test_no_verb(self):
        checks = check_tool_quality(_tool(name="user_data"))
        verb = next(c for c in checks if c.check_id == "quality.naming_verb_prefix")
        assert verb.status == Status.WARN


class TestAnnotationHints:
    def test_both_present(self):
        tool = _tool(annotations={"readOnlyHint": True, "destructiveHint": False})
        checks = check_tool_quality(tool)
        c = next(c for c in checks if c.check_id == "quality.annotation_hints")
        assert c.status == Status.PASS

    def test_missing(self):
        checks = check_tool_quality(_tool())
        c = next(c for c in checks if c.check_id == "quality.annotation_hints")
        assert c.status == Status.WARN


class TestQualityAll:
    def test_multiple_tools(self):
        tools = [
            {"name": "get_users", "description": "Get all users from the database"},
            {"name": "Bad-Name", "description": "x"},
        ]
        result = check_quality_all(tools)
        assert result.layer == "quality"
        assert len(result.tools) == 2
        assert result.tools[0].tool_name == "get_users"
        assert result.tools[1].tool_name == "Bad-Name"
        for tr in result.tools:
            for check in tr.checks:
                assert check.tool_name == tr.tool_name


class TestEvaluateToolsCompat:
    def test_output_shape(self):
        tools = [
            {
                "name": "search_users",
                "description": "Search for users by name or email address in the database",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                    },
                    "required": ["query"],
                },
                "annotations": {
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "title": "Search Users",
                },
            }
        ]
        result = evaluate_tools_compat(tools)

        assert "server_summary" in result
        assert "tools" in result
        summary = result["server_summary"]
        assert "overall_score" in summary
        assert "tool_count" in summary
        assert "dimension_averages" in summary
        assert "score_distribution" in summary
        assert isinstance(summary["overall_score"], float)
        assert summary["tool_count"] == 1

        dims = summary["dimension_averages"]
        for key in ["description_quality", "input_schema_completeness",
                     "required_fields", "naming_conventions", "annotations_metadata"]:
            assert key in dims

        dist = summary["score_distribution"]
        for key in ["green", "yellow", "red"]:
            assert key in dist

        tool_result = result["tools"][0]
        assert "name" in tool_result
        assert "overall_score" in tool_result
        assert "dimensions" in tool_result
        for dim_name, dim_data in tool_result["dimensions"].items():
            assert "score" in dim_data
            assert "checks" in dim_data

    def test_empty_tools(self):
        result = evaluate_tools_compat([])
        assert result["server_summary"]["tool_count"] == 0
        assert result["server_summary"]["overall_score"] == 0
        assert result["tools"] == []
