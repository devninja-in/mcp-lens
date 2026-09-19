from __future__ import annotations

import logging
import re

from .models import CheckResult, LayerResult, Severity, Status, ToolResult
from .registry import (
    ParamDef,
    RuleConfig,
    apply_severity_override,
    get_effective_config,
    get_rules_for_layer,
    register_rule,
)

logger = logging.getLogger(__name__)

ACTIONABLE_VERBS = {
    "get",
    "set",
    "create",
    "update",
    "delete",
    "search",
    "list",
    "fetch",
    "find",
    "add",
    "remove",
    "merge",
    "approve",
    "reject",
    "execute",
    "run",
    "query",
    "send",
    "read",
    "write",
    "upload",
    "download",
    "export",
    "import",
    "validate",
    "check",
    "test",
    "connect",
    "disconnect",
    "start",
    "stop",
    "deploy",
    "publish",
    "subscribe",
    "unsubscribe",
    "configure",
    "install",
    "move",
    "copy",
    "archive",
    "restore",
    "convert",
    "parse",
    "generate",
    "analyze",
    "compute",
    "calculate",
    "resolve",
    "discover",
    "put",
    "patch",
    "post",
    "close",
    "open",
    "enable",
    "disable",
    "reset",
    "refresh",
    "sync",
    "load",
    "save",
    "browse",
    "invite",
}

GENERIC_FILLERS = ["this tool", "a tool that", "tool for", "tool to"]

ENUM_HINT_KEYWORDS = {"status", "type", "mode", "format", "action"}

_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
_CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
_CAMEL_SPLIT = re.compile(r"[a-z]+|[A-Z][a-z]*")

WEIGHTS = {
    "description_quality": 0.25,
    "input_schema_completeness": 0.25,
    "required_fields": 0.15,
    "naming_conventions": 0.15,
    "annotations_metadata": 0.20,
}


def _split_name(name: str) -> list[str]:
    if "_" in name:
        return [s.lower() for s in name.split("_") if s]
    segments = _CAMEL_SPLIT.findall(name)
    return [s.lower() for s in segments] if segments else [name.lower()]


@register_rule(
    rule_id="quality.desc_actionable",
    layer="quality",
    description="Description starts with an action verb",
    default_severity=Severity.MEDIUM,
    params_schema={
        "actionable_verbs": ParamDef(
            type="list", default=list(ACTIONABLE_VERBS), description="Verbs considered actionable"
        ),
    },
)
def _check_desc_actionable(tool: dict, params: dict | None = None) -> CheckResult:
    params = params or {}
    verbs = set(params.get("actionable_verbs", ACTIONABLE_VERBS))
    desc = (tool.get("description") or "").strip()
    if not desc:
        return CheckResult(
            check_id="quality.desc_actionable",
            status=Status.FAIL,
            message="Description is empty",
            severity=Severity.HIGH,
            details={
                "location": "description",
                "current_value": None,
                "suggestion": (
                    "Add a description starting with an action verb like 'Get', 'Create', 'Search', 'Delete', etc."
                ),
            },
        )
    first_word = desc.lower().split()[0] if desc.split() else ""
    if first_word in verbs:
        return CheckResult(
            check_id="quality.desc_actionable",
            status=Status.PASS,
            message=f"Description starts with action verb '{first_word}'",
        )
    return CheckResult(
        check_id="quality.desc_actionable",
        status=Status.WARN,
        message=f"Description does not start with an action verb (first word: '{first_word}')",
        severity=Severity.MEDIUM,
        details={
            "location": "description",
            "current_value": desc[:80] + ("..." if len(desc) > 80 else ""),
            "suggestion": (
                f"Rephrase to start with an action verb (e.g., 'Get', 'List', 'Create') instead of '{first_word}'."
            ),
        },
    )


@register_rule(
    rule_id="quality.desc_adequate_length",
    layer="quality",
    description="Description has adequate length for clarity",
    default_severity=Severity.MEDIUM,
    params_schema={
        "min_length": ParamDef(type="int", default=20, description="Minimum description length in characters"),
    },
)
def _check_desc_adequate_length(tool: dict, params: dict | None = None) -> CheckResult:
    params = params or {}
    min_length = params.get("min_length", 20)
    desc = (tool.get("description") or "").strip()
    if not desc:
        return CheckResult(
            check_id="quality.desc_adequate_length",
            status=Status.FAIL,
            message="Description is empty or missing",
            severity=Severity.HIGH,
            details={
                "location": "description",
                "current_value": None,
                "suggestion": (
                    f"Add a description of at least {min_length} characters"
                    f" explaining what the tool does and when to use it."
                ),
            },
        )
    if len(desc) <= min_length:
        return CheckResult(
            check_id="quality.desc_adequate_length",
            status=Status.WARN,
            message=f"Description is only {len(desc)} chars (should be > {min_length})",
            severity=Severity.MEDIUM,
            details={
                "location": "description",
                "current_value": desc,
                "suggestion": (
                    f"Expand the description to at least {min_length} characters. Explain what the tool does, "
                    "its inputs, and expected output."
                ),
            },
        )
    return CheckResult(
        check_id="quality.desc_adequate_length",
        status=Status.PASS,
        message=f"Description length ({len(desc)} chars) is adequate",
    )


@register_rule(
    rule_id="quality.desc_no_filler",
    layer="quality",
    description="Description does not start with generic filler text",
    default_severity=Severity.LOW,
    params_schema={
        "filler_phrases": ParamDef(type="list", default=list(GENERIC_FILLERS), description="Phrases considered filler"),
    },
)
def _check_desc_no_filler(tool: dict, params: dict | None = None) -> CheckResult:
    params = params or {}
    fillers = params.get("filler_phrases", GENERIC_FILLERS)
    desc = (tool.get("description") or "").strip()
    if not desc:
        return CheckResult(
            check_id="quality.desc_no_filler",
            status=Status.PASS,
            message="No description to check for filler",
        )
    lower = desc.lower()
    for filler in fillers:
        if lower.startswith(filler):
            return CheckResult(
                check_id="quality.desc_no_filler",
                status=Status.WARN,
                message=f"Description starts with generic filler '{filler}'",
                severity=Severity.LOW,
                details={
                    "location": "description",
                    "current_value": desc[:80] + ("..." if len(desc) > 80 else ""),
                    "suggestion": (
                        f"Remove '{filler}' and start directly with an action verb describing the tool's behavior."
                    ),
                },
            )
    return CheckResult(
        check_id="quality.desc_no_filler",
        status=Status.PASS,
        message="Description does not start with generic filler",
    )


@register_rule(
    rule_id="quality.desc_explains_usage",
    layer="quality",
    description="Description is detailed enough to explain usage",
    default_severity=Severity.LOW,
    params_schema={
        "min_usage_length": ParamDef(type="int", default=50, description="Minimum chars for usage context"),
    },
)
def _check_desc_explains_usage(tool: dict, params: dict | None = None) -> CheckResult:
    params = params or {}
    min_usage_length = params.get("min_usage_length", 50)
    desc = (tool.get("description") or "").strip()
    if len(desc) > min_usage_length:
        return CheckResult(
            check_id="quality.desc_explains_usage",
            status=Status.PASS,
            message="Description is detailed enough to explain usage",
        )
    return CheckResult(
        check_id="quality.desc_explains_usage",
        status=Status.WARN,
        message=f"Description is {len(desc)} chars; consider adding usage context (> {min_usage_length} recommended)",
        severity=Severity.LOW,
        details={
            "location": "description",
            "current_value": desc,
            "suggestion": (
                "Add more context: what parameters it expects, what it returns, and when "
                "an agent should choose this tool over alternatives."
            ),
        },
    )


@register_rule(
    rule_id="quality.param_all_described",
    layer="quality",
    description="All parameters have descriptions",
    default_severity=Severity.MEDIUM,
)
def _check_param_all_described(tool: dict, params: dict | None = None) -> CheckResult:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        return CheckResult(
            check_id="quality.param_all_described",
            status=Status.SKIP,
            message="No inputSchema to check",
        )
    props = schema.get("properties", {})
    if not props:
        return CheckResult(
            check_id="quality.param_all_described",
            status=Status.PASS,
            message="No parameters to check",
        )
    missing = [name for name, defn in props.items() if isinstance(defn, dict) and "description" not in defn]
    if missing:
        return CheckResult(
            check_id="quality.param_all_described",
            status=Status.WARN,
            message=f"Parameters missing descriptions: {missing}",
            severity=Severity.MEDIUM,
            details={
                "missing": missing,
                "location": ", ".join(f"inputSchema.properties.{m}" for m in missing),
                "suggestion": (
                    f"Add a 'description' field to each of: {', '.join(missing)}. "
                    f"Describe what the parameter controls and its expected format."
                ),
            },
        )
    return CheckResult(
        check_id="quality.param_all_described",
        status=Status.PASS,
        message="All parameters have descriptions",
    )


@register_rule(
    rule_id="quality.param_all_typed",
    layer="quality",
    description="All parameters have type definitions",
    default_severity=Severity.MEDIUM,
)
def _check_param_all_typed(tool: dict, params: dict | None = None) -> CheckResult:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        return CheckResult(
            check_id="quality.param_all_typed",
            status=Status.SKIP,
            message="No inputSchema to check",
        )
    props = schema.get("properties", {})
    if not props:
        return CheckResult(
            check_id="quality.param_all_typed",
            status=Status.PASS,
            message="No parameters to check",
        )
    missing = [
        name
        for name, defn in props.items()
        if isinstance(defn, dict) and not any(k in defn for k in ("type", "anyOf", "oneOf"))
    ]
    if missing:
        return CheckResult(
            check_id="quality.param_all_typed",
            status=Status.WARN,
            message=f"Parameters missing type definitions: {missing}",
            severity=Severity.MEDIUM,
            details={
                "missing": missing,
                "location": ", ".join(f"inputSchema.properties.{m}" for m in missing),
                "suggestion": f"Add a 'type' field (string, number, boolean, array, object) to: {', '.join(missing)}.",
            },
        )
    return CheckResult(
        check_id="quality.param_all_typed",
        status=Status.PASS,
        message="All parameters have type definitions",
    )


@register_rule(
    rule_id="quality.param_enum_usage",
    layer="quality",
    description="String parameters with keyword names should use enum constraints",
    default_severity=Severity.INFO,
    params_schema={
        "enum_hint_keywords": ParamDef(
            type="list", default=list(ENUM_HINT_KEYWORDS), description="Keywords suggesting enum usage"
        ),
    },
)
def _check_param_enum_usage(tool: dict, params: dict | None = None) -> CheckResult:
    params = params or {}
    keywords = set(params.get("enum_hint_keywords", ENUM_HINT_KEYWORDS))
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        return CheckResult(
            check_id="quality.param_enum_usage",
            status=Status.SKIP,
            message="No inputSchema to check",
        )
    props = schema.get("properties", {})
    candidates = [
        name
        for name, defn in props.items()
        if isinstance(defn, dict)
        and defn.get("type") == "string"
        and "enum" not in defn
        and any(kw in name.lower() for kw in keywords)
    ]
    if candidates:
        return CheckResult(
            check_id="quality.param_enum_usage",
            status=Status.PASS,
            message=f"Parameters that could benefit from enum constraints: {candidates}",
            severity=Severity.INFO,
            details={"candidates": candidates},
        )
    return CheckResult(
        check_id="quality.param_enum_usage",
        status=Status.PASS,
        message="No parameters flagged for enum usage",
    )


@register_rule(
    rule_id="quality.naming_consistent",
    layer="quality",
    description="Tool name follows consistent snake_case or camelCase",
    default_severity=Severity.MEDIUM,
)
def _check_naming_consistent(tool: dict, params: dict | None = None) -> CheckResult:
    name = tool.get("name", "")
    if not name:
        return CheckResult(
            check_id="quality.naming_consistent",
            status=Status.WARN,
            message="Tool has no name",
            severity=Severity.MEDIUM,
        )
    if _SNAKE_CASE.match(name) or _CAMEL_CASE.match(name):
        return CheckResult(
            check_id="quality.naming_consistent",
            status=Status.PASS,
            message=f"Name '{name}' follows a consistent naming convention",
        )
    return CheckResult(
        check_id="quality.naming_consistent",
        status=Status.WARN,
        message=f"Name '{name}' does not follow snake_case or camelCase consistently",
        severity=Severity.MEDIUM,
        details={
            "location": "name",
            "current_value": name,
            "suggestion": (
                f"Rename to snake_case (e.g., '{name.lower()}') or camelCase for consistency with other tools."
            ),
        },
    )


@register_rule(
    rule_id="quality.naming_verb_prefix",
    layer="quality",
    description="Tool name starts with an action verb",
    default_severity=Severity.LOW,
)
def _check_naming_verb_prefix(tool: dict, params: dict | None = None) -> CheckResult:
    name = tool.get("name", "")
    if not name:
        return CheckResult(
            check_id="quality.naming_verb_prefix",
            status=Status.WARN,
            message="Tool has no name",
            severity=Severity.MEDIUM,
        )
    segments = _split_name(name)
    if segments and segments[0] in ACTIONABLE_VERBS:
        return CheckResult(
            check_id="quality.naming_verb_prefix",
            status=Status.PASS,
            message=f"Name starts with action verb '{segments[0]}'",
        )
    first_seg = segments[0] if segments else ""
    return CheckResult(
        check_id="quality.naming_verb_prefix",
        status=Status.WARN,
        message=f"Name does not start with an action verb (first segment: '{first_seg}')",
        severity=Severity.LOW,
        details={
            "location": "name",
            "current_value": name,
            "suggestion": (
                f"Prefix the name with an action verb like 'get_', 'list_', 'create_', 'search_' "
                f"(e.g., 'get_{name}' or 'search_{name}')."
            ),
        },
    )


@register_rule(
    rule_id="quality.annotation_hints",
    layer="quality",
    description="Tool has readOnlyHint and destructiveHint annotations",
    default_severity=Severity.LOW,
)
def _check_annotation_hints(tool: dict, params: dict | None = None) -> CheckResult:
    annotations = tool.get("annotations")
    if not isinstance(annotations, dict):
        return CheckResult(
            check_id="quality.annotation_hints",
            status=Status.WARN,
            message="No annotations defined; consider adding readOnlyHint and destructiveHint",
            severity=Severity.LOW,
            details={
                "location": "annotations",
                "current_value": None,
                "suggestion": (
                    'Add annotations: {"readOnlyHint": true/false, "destructiveHint": true/false} '
                    "to help agents understand tool safety."
                ),
            },
        )
    has_readonly = "readOnlyHint" in annotations
    has_destructive = "destructiveHint" in annotations
    if has_readonly and has_destructive:
        return CheckResult(
            check_id="quality.annotation_hints",
            status=Status.PASS,
            message="Both readOnlyHint and destructiveHint are present",
        )
    missing = []
    if not has_readonly:
        missing.append("readOnlyHint")
    if not has_destructive:
        missing.append("destructiveHint")
    return CheckResult(
        check_id="quality.annotation_hints",
        status=Status.WARN,
        message=f"Missing annotation hints: {missing}",
        severity=Severity.LOW,
        details={
            "missing": missing,
            "location": "annotations",
            "suggestion": f"Add {', '.join(missing)} to annotations to help agents determine tool safety behavior.",
        },
    )


@register_rule(
    rule_id="quality.output_schema",
    layer="quality",
    description="Tool has an outputSchema defined (optional)",
    default_severity=Severity.INFO,
)
def _check_output_schema(tool: dict, params: dict | None = None) -> CheckResult:
    if tool.get("outputSchema") is not None:
        return CheckResult(
            check_id="quality.output_schema",
            status=Status.PASS,
            message="Tool has an outputSchema",
        )
    return CheckResult(
        check_id="quality.output_schema",
        status=Status.PASS,
        message="No outputSchema defined (optional)",
        severity=Severity.INFO,
    )


def check_tool_quality(tool: dict, db_configs: dict[str, RuleConfig] | None = None) -> list[CheckResult]:
    if db_configs is None:
        db_configs = {}
    rules = get_rules_for_layer("quality")
    checks: list[CheckResult] = []
    for rule_id, rule_def in rules.items():
        enabled, severity, params = get_effective_config(rule_def, db_configs.get(rule_id))
        if not enabled:
            continue
        result = rule_def.check_fn(tool, params=params)
        if isinstance(result, list):
            for c in result:
                apply_severity_override(c, severity)
                checks.append(c)
        else:
            apply_severity_override(result, severity)
            checks.append(result)
    return checks


def check_quality_all(tools: list[dict], db_configs: dict[str, RuleConfig] | None = None) -> LayerResult:
    logger.info("Running quality checks on %d tools", len(tools))
    results = []
    for tool in tools:
        name = tool.get("name", "<unnamed>")
        checks = check_tool_quality(tool, db_configs)
        for c in checks:
            c.tool_name = name
        tr = ToolResult(tool_name=name, checks=checks)
        results.append(tr)
    fails = sum(1 for r in results for c in r.checks if c.status == Status.FAIL)
    if fails:
        logger.warning("Quality checks: %d failures across %d tools", fails, len(tools))
    return LayerResult(layer="quality", tools=results)


# ---------------------------------------------------------------------------
# Backward-compatible evaluator (drop-in replacement for src/app/evaluator.py)
# ---------------------------------------------------------------------------


def _score_description(tool: dict) -> dict:
    desc = (tool.get("description") or "").strip()
    checks = {
        "has_description": bool(desc),
        "length_gt_10": len(desc) > 10,
        "length_gt_50": len(desc) > 50,
        "has_actionable_verb": False,
        "no_generic_filler": True,
    }
    if desc:
        words = desc.lower().split()[:10]
        checks["has_actionable_verb"] = any(w in ACTIONABLE_VERBS for w in words)
        lower = desc.lower()
        checks["no_generic_filler"] = not any(lower.startswith(f) for f in GENERIC_FILLERS)
    score = sum(20 for v in checks.values() if v)
    return {"score": score, "checks": checks}


def _score_input_schema(tool: dict) -> dict:
    schema = tool.get("inputSchema")
    checks = {
        "has_input_schema": schema is not None,
        "has_properties": False,
        "all_have_types": False,
        "all_have_descriptions": False,
    }
    if not isinstance(schema, dict):
        return {"score": 0, "checks": checks}

    props = schema.get("properties", {})
    checks["has_properties"] = bool(props)

    if props:
        checks["all_have_types"] = all(
            "type" in p or "anyOf" in p or "oneOf" in p for p in props.values() if isinstance(p, dict)
        )
        checks["all_have_descriptions"] = all("description" in p for p in props.values() if isinstance(p, dict))

    score = sum(25 for v in checks.values() if v)
    return {"score": score, "checks": checks}


def _score_required_fields(tool: dict) -> dict:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        return {"score": 100, "checks": {"no_params": True, "has_required_array": True, "required_non_empty": True}}

    props = schema.get("properties", {})
    if not props:
        return {"score": 100, "checks": {"no_params": True, "has_required_array": True, "required_non_empty": True}}

    required = schema.get("required")
    checks = {
        "no_params": False,
        "has_required_array": isinstance(required, list),
        "required_non_empty": isinstance(required, list) and len(required) > 0,
    }
    score = 0
    if checks["has_required_array"]:
        score += 50
    if checks["required_non_empty"]:
        score += 50
    return {"score": score, "checks": checks}


def _score_naming(tool: dict) -> dict:
    name = tool.get("name", "")
    checks = {
        "consistent_case": False,
        "has_verb_prefix": False,
    }
    if not name:
        return {"score": 0, "checks": checks}

    checks["consistent_case"] = bool(_SNAKE_CASE.match(name) or _CAMEL_CASE.match(name))

    segments = _split_name(name)
    if segments:
        checks["has_verb_prefix"] = segments[0] in ACTIONABLE_VERBS

    score = sum(50 for v in checks.values() if v)
    return {"score": score, "checks": checks}


def _score_annotations(tool: dict) -> dict:
    annotations = tool.get("annotations")
    checks = {
        "has_annotations": isinstance(annotations, dict),
        "has_title": False,
        "has_hint": False,
        "has_output_schema": tool.get("outputSchema") is not None,
    }
    if isinstance(annotations, dict):
        checks["has_title"] = "title" in annotations
        hint_keys = {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}
        checks["has_hint"] = any(k in annotations for k in hint_keys)

    score = sum(25 for v in checks.values() if v)
    return {"score": score, "checks": checks}


def _compute_overall(dimensions: dict[str, dict]) -> float:
    total = sum(dimensions[dim]["score"] * weight for dim, weight in WEIGHTS.items())
    return float(round(total, 1))


def _evaluate_single_tool(tool: dict) -> dict:
    dimensions = {
        "description_quality": _score_description(tool),
        "input_schema_completeness": _score_input_schema(tool),
        "required_fields": _score_required_fields(tool),
        "naming_conventions": _score_naming(tool),
        "annotations_metadata": _score_annotations(tool),
    }
    return {
        "name": tool.get("name", ""),
        "overall_score": _compute_overall(dimensions),
        "dimensions": dimensions,
    }


def evaluate_tools_compat(tools: list[dict]) -> dict:
    if not tools:
        return {
            "server_summary": {
                "overall_score": 0,
                "tool_count": 0,
                "dimension_averages": {dim: 0 for dim in WEIGHTS},
                "score_distribution": {"green": 0, "yellow": 0, "red": 0},
            },
            "tools": [],
        }

    evaluated = [_evaluate_single_tool(t) for t in tools]

    dim_averages = {}
    for dim in WEIGHTS:
        avg = sum(t["dimensions"][dim]["score"] for t in evaluated) / len(evaluated)
        dim_averages[dim] = round(avg, 1)

    overall = sum(t["overall_score"] for t in evaluated) / len(evaluated)

    dist = {"green": 0, "yellow": 0, "red": 0}
    for t in evaluated:
        s = t["overall_score"]
        if s >= 80:
            dist["green"] += 1
        elif s >= 60:
            dist["yellow"] += 1
        else:
            dist["red"] += 1

    return {
        "server_summary": {
            "overall_score": round(overall, 1),
            "tool_count": len(evaluated),
            "dimension_averages": dim_averages,
            "score_distribution": dist,
        },
        "tools": evaluated,
    }
