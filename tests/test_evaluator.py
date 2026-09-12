from src.app.evaluator import (
    _score_annotations,
    _score_description,
    _score_input_schema,
    _score_naming,
    _score_required_fields,
    evaluate_tools,
)


class TestScoreDescription:
    def test_no_description(self):
        result = _score_description({})
        assert result["score"] == 20  # no_generic_filler is True
        assert result["checks"]["has_description"] is False

    def test_short_description(self):
        result = _score_description({"description": "Get data"})
        assert result["checks"]["has_description"] is True
        assert result["checks"]["length_gt_10"] is False
        assert result["checks"]["has_actionable_verb"] is True
        assert result["score"] == 60

    def test_good_description(self):
        result = _score_description({
            "description": "Search for documents matching a query string and return paginated results with metadata"
        })
        assert result["score"] == 100
        assert all(result["checks"].values())

    def test_generic_filler(self):
        result = _score_description({
            "description": "This tool searches for documents matching a query string and returns results"
        })
        assert result["checks"]["no_generic_filler"] is False
        assert result["score"] == 80

    def test_empty_string(self):
        result = _score_description({"description": ""})
        assert result["checks"]["has_description"] is False
        assert result["score"] == 20


class TestScoreInputSchema:
    def test_no_schema(self):
        result = _score_input_schema({})
        assert result["score"] == 0

    def test_empty_schema(self):
        result = _score_input_schema({"inputSchema": {"type": "object"}})
        assert result["checks"]["has_input_schema"] is True
        assert result["checks"]["has_properties"] is False
        assert result["score"] == 25

    def test_complete_schema(self):
        result = _score_input_schema({
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results"},
                },
            }
        })
        assert result["score"] == 100

    def test_missing_descriptions(self):
        result = _score_input_schema({
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            }
        })
        assert result["checks"]["all_have_descriptions"] is False
        assert result["score"] == 75

    def test_anyof_type(self):
        result = _score_input_schema({
            "inputSchema": {
                "type": "object",
                "properties": {
                    "value": {
                        "anyOf": [{"type": "string"}, {"type": "integer"}],
                        "description": "A value",
                    }
                },
            }
        })
        assert result["checks"]["all_have_types"] is True
        assert result["score"] == 100


class TestScoreRequiredFields:
    def test_no_params(self):
        result = _score_required_fields({})
        assert result["score"] == 100

    def test_has_required(self):
        result = _score_required_fields({
            "inputSchema": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            }
        })
        assert result["score"] == 100

    def test_missing_required(self):
        result = _score_required_fields({
            "inputSchema": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
            }
        })
        assert result["score"] == 0

    def test_empty_required(self):
        result = _score_required_fields({
            "inputSchema": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": [],
            }
        })
        assert result["checks"]["has_required_array"] is True
        assert result["checks"]["required_non_empty"] is False
        assert result["score"] == 50


class TestScoreNaming:
    def test_snake_case_verb(self):
        result = _score_naming({"name": "get_users"})
        assert result["score"] == 100

    def test_camel_case_verb(self):
        result = _score_naming({"name": "getUsers"})
        assert result["score"] == 100

    def test_no_verb(self):
        result = _score_naming({"name": "users_list"})
        assert result["checks"]["consistent_case"] is True
        assert result["checks"]["has_verb_prefix"] is False
        assert result["score"] == 50

    def test_bad_case(self):
        result = _score_naming({"name": "Get_Users"})
        assert result["checks"]["consistent_case"] is False
        assert result["score"] == 50

    def test_empty_name(self):
        result = _score_naming({"name": ""})
        assert result["score"] == 0

    def test_missing_name(self):
        result = _score_naming({})
        assert result["score"] == 0


class TestScoreAnnotations:
    def test_no_annotations(self):
        result = _score_annotations({})
        assert result["score"] == 0

    def test_full_annotations(self):
        result = _score_annotations({
            "annotations": {"title": "Get Users", "readOnlyHint": True},
            "outputSchema": {"type": "object"},
        })
        assert result["score"] == 100

    def test_partial_annotations(self):
        result = _score_annotations({
            "annotations": {"title": "Get Users"},
        })
        assert result["checks"]["has_annotations"] is True
        assert result["checks"]["has_title"] is True
        assert result["checks"]["has_hint"] is False
        assert result["checks"]["has_output_schema"] is False
        assert result["score"] == 50


class TestEvaluateTools:
    def test_empty_list(self):
        result = evaluate_tools([])
        assert result["server_summary"]["tool_count"] == 0
        assert result["server_summary"]["overall_score"] == 0
        assert result["tools"] == []

    def test_single_high_quality_tool(self):
        tool = {
            "name": "search_documents",
            "description": "Search for documents matching a query and return paginated results with relevance scores",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results"},
                },
                "required": ["query"],
            },
            "annotations": {"title": "Search Documents", "readOnlyHint": True},
            "outputSchema": {"type": "object"},
        }
        result = evaluate_tools([tool])
        summary = result["server_summary"]
        assert summary["tool_count"] == 1
        assert summary["overall_score"] >= 80
        assert summary["score_distribution"]["green"] == 1

    def test_multi_tool_averages(self):
        good = {
            "name": "get_user",
            "description": "Retrieve a user by their unique identifier from the database",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string", "description": "User ID"}},
                "required": ["id"],
            },
        }
        bad = {"name": "X", "description": "x"}
        result = evaluate_tools([good, bad])
        assert result["server_summary"]["tool_count"] == 2
        assert len(result["tools"]) == 2
        scores = [t["overall_score"] for t in result["tools"]]
        assert scores[0] > scores[1]

    def test_score_distribution_buckets(self):
        green = {
            "name": "search_items",
            "description": "Search for items matching criteria and return sorted results with metadata",
            "inputSchema": {
                "type": "object",
                "properties": {"q": {"type": "string", "description": "Query"}},
                "required": ["q"],
            },
            "annotations": {"title": "Search", "readOnlyHint": True},
            "outputSchema": {"type": "object"},
        }
        red = {"name": "X"}
        result = evaluate_tools([green, red])
        dist = result["server_summary"]["score_distribution"]
        assert dist["green"] >= 1
        assert dist["red"] >= 1
