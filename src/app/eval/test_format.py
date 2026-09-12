from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Assertion, TestCase, TestSuite


def load_test_suite(path: Path) -> TestSuite:
    raw = yaml.safe_load(path.read_text())
    server = raw.get("server", "")
    test_cases: list[TestCase] = []
    for t in raw.get("tests", []):
        assertions = [
            Assertion(
                type=a["type"],
                path=a.get("path", ""),
                expected=a.get("expected"),
            )
            for a in t.get("assertions", [])
        ]
        test_cases.append(
            TestCase(
                id=t["id"],
                tool_name=t["tool"],
                description=t.get("description", ""),
                input=t.get("input", {}),
                assertions=assertions,
                expect_error=t.get("expect_error", False),
                tags=t.get("tags", []),
            )
        )
    return TestSuite(server_name=server, test_cases=test_cases)


def load_all_test_suites(directory: Path) -> list[TestSuite]:
    suites: list[TestSuite] = []
    for p in sorted(directory.iterdir()):
        if p.suffix in (".yaml", ".yml") and p.is_file():
            suites.append(load_test_suite(p))
    return suites


def generate_negative_tests(tool: dict) -> list[TestCase]:
    schema = tool.get("inputSchema", {})
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if not properties:
        return []

    tool_name = tool.get("name", "unknown")
    tests: list[TestCase] = []

    base_input = _make_base_input(properties)

    for param in required:
        missing = {k: v for k, v in base_input.items() if k != param}
        tests.append(
            TestCase(
                id=f"{tool_name}_missing_{param}",
                tool_name=tool_name,
                description=f"Missing required parameter: {param}",
                input=missing,
                expect_error=True,
                tags=["negative", "auto-generated"],
            )
        )

    for param, prop in properties.items():
        ptype = prop.get("type", "")
        if ptype == "string":
            wrong = {**base_input, param: 12345}
            tests.append(
                TestCase(
                    id=f"{tool_name}_wrong_type_{param}",
                    tool_name=tool_name,
                    description=f"Wrong type for {param}: int instead of string",
                    input=wrong,
                    expect_error=True,
                    tags=["negative", "auto-generated"],
                )
            )
        elif ptype in ("integer", "number"):
            wrong = {**base_input, param: "not_a_number"}
            tests.append(
                TestCase(
                    id=f"{tool_name}_wrong_type_{param}",
                    tool_name=tool_name,
                    description=f"Wrong type for {param}: string instead of {ptype}",
                    input=wrong,
                    expect_error=True,
                    tags=["negative", "auto-generated"],
                )
            )

        if "enum" in prop:
            wrong = {**base_input, param: "__INVALID_ENUM_VALUE__"}
            tests.append(
                TestCase(
                    id=f"{tool_name}_invalid_enum_{param}",
                    tool_name=tool_name,
                    description=f"Invalid enum value for {param}",
                    input=wrong,
                    expect_error=True,
                    tags=["negative", "auto-generated"],
                )
            )

    return tests


def generate_boundary_tests(tool: dict) -> list[TestCase]:
    schema = tool.get("inputSchema", {})
    properties = schema.get("properties", {})
    if not properties:
        return []

    tool_name = tool.get("name", "unknown")
    tests: list[TestCase] = []
    base_input = _make_base_input(properties)

    for param, prop in properties.items():
        ptype = prop.get("type", "")
        if ptype in ("integer", "number"):
            for val, label in [(0, "zero"), (-1, "negative"), (999999999, "large")]:
                tests.append(
                    TestCase(
                        id=f"{tool_name}_boundary_{param}_{label}",
                        tool_name=tool_name,
                        description=f"Boundary test for {param}: {label} ({val})",
                        input={**base_input, param: val},
                        tags=["boundary", "auto-generated"],
                    )
                )
        elif ptype == "string":
            tests.append(
                TestCase(
                    id=f"{tool_name}_boundary_{param}_empty",
                    tool_name=tool_name,
                    description=f"Boundary test for {param}: empty string",
                    input={**base_input, param: ""},
                    tags=["boundary", "auto-generated"],
                )
            )
            tests.append(
                TestCase(
                    id=f"{tool_name}_boundary_{param}_long",
                    tool_name=tool_name,
                    description=f"Boundary test for {param}: very long string",
                    input={**base_input, param: "x" * 10000},
                    tags=["boundary", "auto-generated"],
                )
            )
        elif ptype == "array":
            tests.append(
                TestCase(
                    id=f"{tool_name}_boundary_{param}_empty_array",
                    tool_name=tool_name,
                    description=f"Boundary test for {param}: empty array",
                    input={**base_input, param: []},
                    tags=["boundary", "auto-generated"],
                )
            )

    return tests


def _make_base_input(properties: dict[str, Any]) -> dict[str, Any]:
    base: dict[str, Any] = {}
    for name, prop in properties.items():
        ptype = prop.get("type", "")
        if "enum" in prop:
            base[name] = prop["enum"][0]
        elif ptype == "string":
            base[name] = "test"
        elif ptype == "integer":
            base[name] = 1
        elif ptype == "number":
            base[name] = 1.0
        elif ptype == "boolean":
            base[name] = True
        elif ptype == "array":
            base[name] = []
        elif ptype == "object":
            base[name] = {}
    return base
