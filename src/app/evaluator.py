import logging
import re

logger = logging.getLogger(__name__)

WEIGHTS = {
    "description_quality": 0.25,
    "input_schema_completeness": 0.25,
    "required_fields": 0.15,
    "naming_conventions": 0.15,
    "annotations_metadata": 0.20,
}

ACTIONABLE_VERBS = {
    "get", "set", "create", "update", "delete", "search", "list",
    "fetch", "find", "add", "remove", "merge", "approve", "reject",
    "execute", "run", "query", "send", "read", "write", "upload",
    "download", "export", "import", "validate", "check", "test",
    "connect", "disconnect", "start", "stop", "deploy", "publish",
    "subscribe", "unsubscribe", "configure", "install", "move",
    "copy", "archive", "restore", "convert", "parse", "generate",
    "analyze", "compute", "calculate", "resolve", "discover",
    "put", "patch", "post", "close", "open", "enable", "disable",
    "reset", "refresh", "sync", "load", "save", "browse", "invite",
}

GENERIC_FILLERS = ["this tool", "a tool that", "tool for", "tool to"]

_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
_CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
_CAMEL_SPLIT = re.compile(r"[a-z]+|[A-Z][a-z]*")


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
            "type" in p or "anyOf" in p or "oneOf" in p
            for p in props.values()
            if isinstance(p, dict)
        )
        checks["all_have_descriptions"] = all(
            "description" in p
            for p in props.values()
            if isinstance(p, dict)
        )

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


def _split_name(name: str) -> list[str]:
    if "_" in name:
        return [s.lower() for s in name.split("_") if s]
    segments = _CAMEL_SPLIT.findall(name)
    return [s.lower() for s in segments] if segments else [name.lower()]


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
    total = sum(
        dimensions[dim]["score"] * weight
        for dim, weight in WEIGHTS.items()
    )
    return round(total, 1)


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


def evaluate_tools(tools: list[dict]) -> dict:
    logger.info("Evaluating %d tools (compat evaluator)", len(tools))
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
