from src.app.eval.models import Status
from src.app.eval.protocol import check_protocol_all, check_tool_protocol


class TestCheckName:
    def test_valid_name(self):
        checks = check_tool_protocol({"name": "search_users"})
        name_checks = [c for c in checks if "name" in c.check_id]
        assert all(c.status == Status.PASS for c in name_checks)

    def test_missing_name(self):
        checks = check_tool_protocol({})
        name_check = next(c for c in checks if c.check_id == "protocol.name_present")
        assert name_check.status == Status.FAIL

    def test_empty_name(self):
        checks = check_tool_protocol({"name": ""})
        name_check = next(c for c in checks if c.check_id == "protocol.name_non_empty")
        assert name_check.status == Status.FAIL

    def test_name_with_spaces(self):
        checks = check_tool_protocol({"name": "bad name"})
        name_check = next(c for c in checks if c.check_id == "protocol.name_non_empty")
        assert name_check.status == Status.FAIL

    def test_non_string_name(self):
        checks = check_tool_protocol({"name": 123})
        name_check = next(c for c in checks if c.check_id == "protocol.name_present")
        assert name_check.status == Status.FAIL


class TestCheckDescription:
    def test_present(self):
        checks = check_tool_protocol({"name": "t", "description": "Does something"})
        desc = next(c for c in checks if c.check_id == "protocol.description_present")
        assert desc.status == Status.PASS

    def test_absent(self):
        checks = check_tool_protocol({"name": "t"})
        desc = next(c for c in checks if c.check_id == "protocol.description_present")
        assert desc.status == Status.WARN

    def test_empty_string(self):
        checks = check_tool_protocol({"name": "t", "description": ""})
        desc = next(c for c in checks if c.check_id == "protocol.description_present")
        assert desc.status == Status.WARN


class TestCheckInputSchema:
    def test_valid_object_schema(self):
        tool = {
            "name": "t",
            "inputSchema": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
            },
        }
        checks = check_tool_protocol(tool)
        schema_check = next(c for c in checks if c.check_id == "protocol.input_schema_valid")
        assert schema_check.status == Status.PASS

    def test_no_schema(self):
        checks = check_tool_protocol({"name": "t"})
        schema_check = next(c for c in checks if c.check_id == "protocol.input_schema_valid")
        assert schema_check.status == Status.SKIP

    def test_non_object_type(self):
        tool = {"name": "t", "inputSchema": {"type": "array"}}
        checks = check_tool_protocol(tool)
        schema_check = next(c for c in checks if c.check_id == "protocol.input_schema_valid")
        assert schema_check.status == Status.WARN


class TestCheckRequired:
    def test_valid_required(self):
        tool = {
            "name": "t",
            "inputSchema": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
        }
        checks = check_tool_protocol(tool)
        req = next(c for c in checks if c.check_id == "protocol.required_valid")
        assert req.status == Status.PASS

    def test_invalid_ref(self):
        tool = {
            "name": "t",
            "inputSchema": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q", "nonexistent"],
            },
        }
        checks = check_tool_protocol(tool)
        req = next(c for c in checks if c.check_id == "protocol.required_valid")
        assert req.status == Status.FAIL
        assert "nonexistent" in req.details.get("invalid_refs", [])


class TestCheckAnnotations:
    def test_valid_booleans(self):
        tool = {
            "name": "t",
            "annotations": {"readOnlyHint": True, "destructiveHint": False},
        }
        checks = check_tool_protocol(tool)
        ann_checks = [c for c in checks if "annotation" in c.check_id]
        assert all(c.status in (Status.PASS, Status.SKIP) for c in ann_checks)

    def test_non_boolean_hint(self):
        tool = {
            "name": "t",
            "annotations": {"readOnlyHint": "yes"},
        }
        checks = check_tool_protocol(tool)
        bad = [c for c in checks if c.status == Status.FAIL and "annotation" in c.check_id]
        assert len(bad) == 1

    def test_no_annotations(self):
        checks = check_tool_protocol({"name": "t"})
        ann = [c for c in checks if c.check_id == "protocol.annotations_present"]
        assert ann[0].status == Status.SKIP


class TestCheckAdditionalProperties:
    def test_defined(self):
        tool = {
            "name": "t",
            "inputSchema": {"type": "object", "additionalProperties": False},
        }
        checks = check_tool_protocol(tool)
        ap = next(c for c in checks if c.check_id == "protocol.additional_properties")
        assert ap.status == Status.PASS

    def test_not_defined(self):
        tool = {"name": "t", "inputSchema": {"type": "object"}}
        checks = check_tool_protocol(tool)
        ap = next(c for c in checks if c.check_id == "protocol.additional_properties")
        assert ap.status == Status.WARN


class TestCheckProtocolAll:
    def test_multiple_tools(self):
        tools = [
            {"name": "good_tool", "description": "Does good things"},
            {"name": "", "description": "Bad name"},
        ]
        result = check_protocol_all(tools)
        assert result.layer == "protocol"
        assert len(result.tools) == 2
        assert result.tools[0].tool_name == "good_tool"

    def test_tool_names_set(self):
        tools = [{"name": "search", "description": "Search stuff"}]
        result = check_protocol_all(tools)
        for check in result.tools[0].checks:
            assert check.tool_name == "search"
