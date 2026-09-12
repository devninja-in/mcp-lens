from __future__ import annotations

import logging
import re

from .models import CheckResult, LayerResult, Severity, Status, ToolResult

logger = logging.getLogger(__name__)

MCP_SPEC_VERSION = "2024-11-05"

_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
_CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
_PASCAL_CASE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")


def check_tool_protocol(tool: dict) -> list[CheckResult]:
    checks = [
        _check_name_present(tool),
        _check_name_valid(tool),
        _check_description_present(tool),
        _check_input_schema_structure(tool),
    ]
    checks.extend(_check_schema_properties(tool))
    checks.append(_check_required_valid(tool))
    checks.extend(_check_annotation_types(tool))
    checks.append(_check_additional_properties(tool))
    return checks


def check_protocol_all(tools: list[dict]) -> LayerResult:
    logger.info("Running protocol compliance checks on %d tools", len(tools))
    results = []
    for tool in tools:
        name = tool.get("name", "<unnamed>")
        checks = check_tool_protocol(tool)
        for c in checks:
            c.tool_name = name
        tr = ToolResult(tool_name=name, checks=checks)
        results.append(tr)
    fails = sum(1 for r in results for c in r.checks if c.status == Status.FAIL)
    if fails:
        logger.warning("Protocol checks: %d failures across %d tools", fails, len(tools))
    return LayerResult(layer="protocol", tools=results)


def _check_name_present(tool: dict) -> CheckResult:
    name = tool.get("name")
    if name is None:
        return CheckResult(
            check_id="protocol.name_present",
            status=Status.FAIL,
            message="Tool is missing 'name' field",
            severity=Severity.CRITICAL,
            details={
                "location": "name",
                "current_value": None,
                "suggestion": "Add a 'name' string field — this is required by the MCP spec for tool identification.",
            },
        )
    if not isinstance(name, str):
        return CheckResult(
            check_id="protocol.name_present",
            status=Status.FAIL,
            message=f"Tool 'name' must be a string, got {type(name).__name__}",
            severity=Severity.CRITICAL,
            details={
                "location": "name",
                "current_value": repr(name),
                "suggestion": f"Change 'name' to a string value instead of {type(name).__name__}.",
            },
        )
    return CheckResult(
        check_id="protocol.name_present",
        status=Status.PASS,
        message="Tool has a name",
    )


def _check_name_valid(tool: dict) -> CheckResult:
    name = tool.get("name", "")
    if not isinstance(name, str) or not name.strip():
        return CheckResult(
            check_id="protocol.name_non_empty",
            status=Status.FAIL,
            message="Tool name is empty",
            severity=Severity.CRITICAL,
            details={
                "location": "name",
                "current_value": repr(name),
                "suggestion": (
                    "Provide a non-empty tool name using snake_case or camelCase "
                    "(e.g., 'get_user', 'searchDocs')."
                ),
            },
        )
    if " " in name:
        return CheckResult(
            check_id="protocol.name_non_empty",
            status=Status.FAIL,
            message=f"Tool name '{name}' contains spaces",
            severity=Severity.HIGH,
            details={
                "location": "name",
                "current_value": name,
                "suggestion": f"Replace spaces with underscores: '{name.replace(' ', '_')}'.",
            },
        )
    return CheckResult(
        check_id="protocol.name_non_empty",
        status=Status.PASS,
        message=f"Tool name '{name}' is valid",
    )


def _check_description_present(tool: dict) -> CheckResult:
    desc = tool.get("description")
    if desc is None or (isinstance(desc, str) and not desc.strip()):
        return CheckResult(
            check_id="protocol.description_present",
            status=Status.WARN,
            message="Tool has no description. Without it, LLM agents cannot determine when or how to use this tool.",
            severity=Severity.MEDIUM,
            details={
                "location": "description",
                "current_value": None,
                "suggestion": (
                    "Add a description starting with an action verb, e.g., "
                    "'Retrieves user details by ID' or 'Creates a new invoice for a customer'."
                ),
            },
        )
    if not isinstance(desc, str):
        return CheckResult(
            check_id="protocol.description_present",
            status=Status.FAIL,
            message=f"Tool description must be a string, got {type(desc).__name__}",
            severity=Severity.HIGH,
            details={
                "location": "description",
                "current_value": repr(desc),
                "suggestion": f"Change 'description' to a string value instead of {type(desc).__name__}.",
            },
        )
    return CheckResult(
        check_id="protocol.description_present",
        status=Status.PASS,
        message="Tool has a description",
    )


def _check_input_schema_structure(tool: dict) -> CheckResult:
    schema = tool.get("inputSchema")
    if schema is None:
        return CheckResult(
            check_id="protocol.input_schema_valid",
            status=Status.SKIP,
            message="No inputSchema defined",
            severity=Severity.INFO,
        )
    if not isinstance(schema, dict):
        return CheckResult(
            check_id="protocol.input_schema_valid",
            status=Status.FAIL,
            message=f"inputSchema must be an object, got {type(schema).__name__}",
            severity=Severity.HIGH,
            details={
                "location": "inputSchema",
                "current_value": repr(schema)[:100],
                "suggestion": (
                    'Replace inputSchema with a JSON Schema object, '
                    'e.g., {"type": "object", "properties": {...}}.'
                ),
            },
        )
    schema_type = schema.get("type")
    if schema_type is not None and schema_type != "object":
        return CheckResult(
            check_id="protocol.input_schema_valid",
            status=Status.WARN,
            message=f"inputSchema type is '{schema_type}', expected 'object'",
            severity=Severity.MEDIUM,
            details={
                "location": "inputSchema.type",
                "current_value": schema_type,
                "suggestion": (
                    "Set inputSchema.type to 'object'. MCP tools expect parameters "
                    "as an object with named properties."
                ),
            },
        )
    return CheckResult(
        check_id="protocol.input_schema_valid",
        status=Status.PASS,
        message="inputSchema structure is valid",
    )


def _check_schema_properties(tool: dict) -> list[CheckResult]:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        return []
    props = schema.get("properties")
    if props is None:
        return []
    if not isinstance(props, dict):
        return [CheckResult(
            check_id="protocol.properties_valid",
            status=Status.FAIL,
            message="inputSchema.properties must be an object",
            severity=Severity.HIGH,
            details={
                "location": "inputSchema.properties",
                "current_value": repr(props)[:100],
                "suggestion": "Replace properties with an object mapping parameter names to JSON Schema definitions.",
            },
        )]

    results = []
    for pname, pdef in props.items():
        if not isinstance(pdef, dict):
            results.append(CheckResult(
                check_id="protocol.property_is_object",
                status=Status.FAIL,
                message=f"Property '{pname}' definition must be an object",
                severity=Severity.HIGH,
                details={
                    "property": pname,
                    "location": f"inputSchema.properties.{pname}",
                    "current_value": repr(pdef)[:100],
                    "suggestion": (
                        f"Define '{pname}' as a JSON Schema object, "
                        f'e.g., {{"type": "string", "description": "..."}}.'
                    ),
                },
            ))
            continue
        has_type = "type" in pdef or "anyOf" in pdef or "oneOf" in pdef or "allOf" in pdef or "$ref" in pdef
        if not has_type:
            results.append(CheckResult(
                check_id="protocol.property_has_type",
                status=Status.WARN,
                message=f"Property '{pname}' has no type definition",
                severity=Severity.LOW,
                details={
                    "property": pname,
                    "location": f"inputSchema.properties.{pname}",
                    "suggestion": (
                        f"Add a 'type' field (string, number, boolean, array, object) "
                        f"to the '{pname}' property definition."
                    ),
                },
            ))

    if not results:
        results.append(CheckResult(
            check_id="protocol.properties_valid",
            status=Status.PASS,
            message="All properties have valid type definitions",
        ))
    return results


def _check_required_valid(tool: dict) -> CheckResult:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        return CheckResult(
            check_id="protocol.required_valid",
            status=Status.SKIP,
            message="No inputSchema to check required fields",
        )
    required = schema.get("required")
    if required is None:
        return CheckResult(
            check_id="protocol.required_valid",
            status=Status.SKIP,
            message="No required array defined",
        )
    if not isinstance(required, list):
        return CheckResult(
            check_id="protocol.required_valid",
            status=Status.FAIL,
            message=f"'required' must be an array, got {type(required).__name__}",
            severity=Severity.HIGH,
            details={
                "location": "inputSchema.required",
                "current_value": repr(required)[:100],
                "suggestion": "Change 'required' to an array of property name strings, e.g., [\"id\", \"name\"].",
            },
        )
    props = schema.get("properties", {})
    invalid = [r for r in required if r not in props]
    if invalid:
        return CheckResult(
            check_id="protocol.required_valid",
            status=Status.FAIL,
            message=f"Required fields reference non-existent properties: {invalid}",
            severity=Severity.HIGH,
            details={
                "invalid_refs": invalid,
                "location": "inputSchema.required",
                "current_value": invalid,
                "suggestion": (
                    f"Either add {invalid} to inputSchema.properties, "
                    f"or remove them from the required array."
                ),
            },
        )
    return CheckResult(
        check_id="protocol.required_valid",
        status=Status.PASS,
        message="All required fields reference valid properties",
    )


def _check_annotation_types(tool: dict) -> list[CheckResult]:
    annotations = tool.get("annotations")
    if not isinstance(annotations, dict):
        return [CheckResult(
            check_id="protocol.annotations_present",
            status=Status.SKIP,
            message="No annotations defined",
        )]

    hint_keys = ["readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"]
    results = []
    for key in hint_keys:
        if key in annotations:
            val = annotations[key]
            if not isinstance(val, bool):
                results.append(CheckResult(
                    check_id=f"protocol.annotation_{key}_bool",
                    status=Status.FAIL,
                    message=f"Annotation '{key}' must be boolean, got {type(val).__name__} ({val!r})",
                    severity=Severity.MEDIUM,
                    details={
                        "key": key,
                        "value": val,
                        "location": f"annotations.{key}",
                        "current_value": repr(val),
                        "suggestion": f"Change annotations.{key} to true or false (boolean), not {type(val).__name__}.",
                    },
                ))

    if not results:
        results.append(CheckResult(
            check_id="protocol.annotation_types_valid",
            status=Status.PASS,
            message="All annotation hint values are correctly typed",
        ))
    return results


def _check_additional_properties(tool: dict) -> CheckResult:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        return CheckResult(
            check_id="protocol.additional_properties",
            status=Status.SKIP,
            message="No inputSchema to check additionalProperties",
        )
    if "additionalProperties" not in schema:
        return CheckResult(
            check_id="protocol.additional_properties",
            status=Status.WARN,
            message="inputSchema does not define 'additionalProperties'. Setting it to false is recommended.",
            severity=Severity.LOW,
            details={
                "location": "inputSchema.additionalProperties",
                "current_value": "(not set)",
                "suggestion": (
                    'Add "additionalProperties": false to inputSchema to prevent '
                    'unexpected parameters from being passed.'
                ),
            },
        )
    return CheckResult(
        check_id="protocol.additional_properties",
        status=Status.PASS,
        message="inputSchema defines 'additionalProperties'",
    )
