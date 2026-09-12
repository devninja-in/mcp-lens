import pytest
import yaml
from pathlib import Path

from src.app.eval.test_format import (
    load_test_suite,
    load_all_test_suites,
    generate_negative_tests,
    generate_boundary_tests,
)
from src.app.eval.models import Assertion, TestCase, TestSuite


VALID_YAML = {
    "server": "test-server",
    "tests": [
        {
            "id": "t1",
            "tool": "my_tool",
            "description": "A test",
            "input": {"q": "hello"},
            "assertions": [
                {"path": "result", "type": "is_string"},
            ],
        },
    ],
}

YAML_WITH_ASSERTIONS = {
    "server": "srv",
    "tests": [
        {
            "id": "t2",
            "tool": "search",
            "input": {"q": "x"},
            "assertions": [
                {"path": "items", "type": "is_array"},
                {"path": "items", "type": "length_lte", "expected": 10},
                {"path": "count", "type": "equals", "expected": 5},
            ],
        },
    ],
}


class TestLoadTestSuite:
    def test_load_valid(self, tmp_path: Path):
        p = tmp_path / "suite.yaml"
        p.write_text(yaml.dump(VALID_YAML))
        suite = load_test_suite(p)
        assert suite.server_name == "test-server"
        assert len(suite.test_cases) == 1
        tc = suite.test_cases[0]
        assert tc.id == "t1"
        assert tc.tool_name == "my_tool"
        assert tc.description == "A test"
        assert tc.input == {"q": "hello"}

    def test_load_with_assertions(self, tmp_path: Path):
        p = tmp_path / "suite.yaml"
        p.write_text(yaml.dump(YAML_WITH_ASSERTIONS))
        suite = load_test_suite(p)
        tc = suite.test_cases[0]
        assert len(tc.assertions) == 3
        assert tc.assertions[0].type == "is_array"
        assert tc.assertions[0].path == "items"
        assert tc.assertions[1].type == "length_lte"
        assert tc.assertions[1].expected == 10
        assert tc.assertions[2].type == "equals"
        assert tc.assertions[2].expected == 5

    def test_load_with_expect_error_and_tags(self, tmp_path: Path):
        data = {
            "server": "srv",
            "tests": [
                {
                    "id": "neg1",
                    "tool": "t",
                    "input": {},
                    "expect_error": True,
                    "tags": ["negative"],
                },
            ],
        }
        p = tmp_path / "suite.yaml"
        p.write_text(yaml.dump(data))
        suite = load_test_suite(p)
        tc = suite.test_cases[0]
        assert tc.expect_error is True
        assert tc.tags == ["negative"]

    def test_load_missing_fields(self, tmp_path: Path):
        data = {"server": "srv", "tests": [{"id": "x", "tool": "t"}]}
        p = tmp_path / "suite.yaml"
        p.write_text(yaml.dump(data))
        suite = load_test_suite(p)
        tc = suite.test_cases[0]
        assert tc.description == ""
        assert tc.input == {}
        assert tc.assertions == []

    def test_load_all_suites(self, tmp_path: Path):
        (tmp_path / "a.yaml").write_text(yaml.dump({"server": "s1", "tests": [{"id": "t1", "tool": "x"}]}))
        (tmp_path / "b.yml").write_text(yaml.dump({"server": "s2", "tests": [{"id": "t2", "tool": "y"}]}))
        (tmp_path / "not_yaml.txt").write_text("ignore me")
        suites = load_all_test_suites(tmp_path)
        assert len(suites) == 2
        names = {s.server_name for s in suites}
        assert names == {"s1", "s2"}


TOOL_WITH_REQUIRED = {
    "name": "search",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["query"],
    },
}

TOOL_WITH_ENUM = {
    "name": "filter",
    "inputSchema": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["active", "inactive"]},
        },
        "required": [],
    },
}


class TestGenerateNegativeTests:
    def test_missing_required(self):
        tests = generate_negative_tests(TOOL_WITH_REQUIRED)
        missing_query = [t for t in tests if "missing_query" in t.id]
        assert len(missing_query) == 1
        tc = missing_query[0]
        assert tc.expect_error is True
        assert "query" not in tc.input
        assert "negative" in tc.tags

    def test_wrong_type(self):
        tests = generate_negative_tests(TOOL_WITH_REQUIRED)
        wrong_type_query = [t for t in tests if "wrong_type_query" in t.id]
        assert len(wrong_type_query) == 1
        tc = wrong_type_query[0]
        assert tc.expect_error is True
        assert isinstance(tc.input["query"], int)

        wrong_type_limit = [t for t in tests if "wrong_type_limit" in t.id]
        assert len(wrong_type_limit) == 1
        assert isinstance(wrong_type_limit[0].input["limit"], str)

    def test_invalid_enum(self):
        tests = generate_negative_tests(TOOL_WITH_ENUM)
        enum_tests = [t for t in tests if "invalid_enum" in t.id]
        assert len(enum_tests) == 1
        assert enum_tests[0].expect_error is True
        assert enum_tests[0].input["status"] == "__INVALID_ENUM_VALUE__"

    def test_no_schema(self):
        tests = generate_negative_tests({"name": "bare"})
        assert tests == []


TOOL_BOUNDARY = {
    "name": "analyze",
    "inputSchema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer"},
            "name": {"type": "string"},
            "items": {"type": "array"},
        },
    },
}


class TestGenerateBoundaryTests:
    def test_integer_boundaries(self):
        tests = generate_boundary_tests(TOOL_BOUNDARY)
        int_tests = [t for t in tests if "count" in t.id]
        assert len(int_tests) == 3
        values = {t.input["count"] for t in int_tests}
        assert values == {0, -1, 999999999}

    def test_string_boundaries(self):
        tests = generate_boundary_tests(TOOL_BOUNDARY)
        str_tests = [t for t in tests if "name" in t.id]
        assert len(str_tests) == 2
        inputs = {t.input["name"] for t in str_tests}
        assert "" in inputs
        assert any(len(v) == 10000 for v in inputs)

    def test_array_boundaries(self):
        tests = generate_boundary_tests(TOOL_BOUNDARY)
        arr_tests = [t for t in tests if "items" in t.id]
        assert len(arr_tests) == 1
        assert arr_tests[0].input["items"] == []

    def test_no_schema(self):
        tests = generate_boundary_tests({"name": "bare"})
        assert tests == []
