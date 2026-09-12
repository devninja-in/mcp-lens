from __future__ import annotations

import logging
import re

from .models import CheckResult, LayerResult, Severity, Status, ToolResult

logger = logging.getLogger(__name__)

READ_VERBS = {
    "get", "list", "search", "find", "read", "fetch", "query", "browse",
    "view", "show", "display", "check", "verify", "validate", "inspect",
    "describe", "count",
}

WRITE_VERBS = {
    "create", "update", "set", "put", "patch", "post", "add", "modify",
    "change", "edit", "save", "write", "insert", "upsert", "merge",
    "configure", "enable", "disable",
}

DELETE_VERBS = {
    "delete", "remove", "destroy", "drop", "purge", "clear", "erase",
    "wipe", "reset", "revoke", "cancel", "terminate", "kill",
}

EXTERNAL_VERBS = {
    "send", "publish", "post", "email", "notify", "broadcast", "transfer",
    "push", "deploy", "release", "submit", "forward", "export", "upload",
    "share", "invite",
}

_CAMEL_SPLIT = re.compile(r"[A-Z][a-z]*|[a-z]+")

_INJECTION_PATTERNS = re.compile(
    r"ignore\s+previous|override|system\s+prompt|you\s+are|forget\s+all",
    re.IGNORECASE,
)

_EXFIL_PARAM_NAMES = {"url", "endpoint", "webhook", "callback", "redirect"}

_QUERY_PARAM_NAMES = {"query", "sql", "command", "expression", "filter"}

_BROAD_PERMISSION_PATTERNS = re.compile(
    r"execute\s+any|run\s+any|arbitrary|unrestricted|all\s+permissions",
    re.IGNORECASE,
)


def _extract_first_verb(name: str) -> str:
    if "_" in name:
        return name.split("_")[0].lower()
    parts = _CAMEL_SPLIT.findall(name)
    if parts:
        return parts[0].lower()
    return name.lower()


def _classify_verb(verb: str) -> str | None:
    if verb in DELETE_VERBS:
        return "destructive"
    if verb in EXTERNAL_VERBS:
        return "external_side_effect"
    if verb in WRITE_VERBS:
        return "write"
    if verb in READ_VERBS:
        return "read_only"
    return None


def classify_tool_action(tool: dict) -> str:
    name = tool.get("name", "")
    verb = _extract_first_verb(name)
    result = _classify_verb(verb)
    if result:
        return result

    desc = (tool.get("description") or "").lower()
    all_verb_sets = [
        (DELETE_VERBS, "destructive"),
        (EXTERNAL_VERBS, "external_side_effect"),
        (WRITE_VERBS, "write"),
        (READ_VERBS, "read_only"),
    ]
    for verbs, classification in all_verb_sets:
        for v in verbs:
            if re.search(rf"\b{re.escape(v)}(s|es|ed|ing|d)?\b", desc):
                return classification

    return "unknown"


def _check_annotation_consistency(tool: dict) -> CheckResult:
    annotations = tool.get("annotations")
    if not isinstance(annotations, dict):
        return CheckResult(
            check_id="security.annotation_consistency",
            status=Status.PASS,
            message="No annotations to check for consistency",
        )

    action = classify_tool_action(tool)

    if annotations.get("readOnlyHint") is True and action in ("write", "destructive", "external_side_effect"):
        action_explanations = {
            "write": "its name or description contains write verbs (create, update, modify, etc.), suggesting it mutates data",
            "destructive": "its name or description contains destructive verbs (delete, remove, purge, etc.), suggesting it destroys data",
            "external_side_effect": "its name or description contains side-effect verbs (send, publish, export, share, etc.), suggesting it triggers external actions",
        }
        explanation = action_explanations[action]
        return CheckResult(
            check_id="security.annotation_consistency",
            status=Status.FAIL,
            message=(
                f"Annotation mismatch: readOnlyHint is true, but {explanation}. "
                f"An LLM agent trusting this hint may execute the tool without user confirmation."
            ),
            severity=Severity.CRITICAL,
            details={
                "classified_action": action,
                "location": "annotations.readOnlyHint",
                "current_value": True,
                "suggestion": "Set readOnlyHint to false or remove it to ensure agents request user confirmation before executing this tool.",
            },
        )

    if annotations.get("destructiveHint") is False and action == "destructive":
        return CheckResult(
            check_id="security.annotation_consistency",
            status=Status.FAIL,
            message=(
                "Annotation mismatch: destructiveHint is false, but the tool's name or description "
                "contains destructive verbs (delete, remove, purge, etc.). An LLM agent may skip "
                "confirmation dialogs for this tool."
            ),
            severity=Severity.HIGH,
            details={
                "classified_action": action,
                "location": "annotations.destructiveHint",
                "current_value": False,
                "suggestion": "Set destructiveHint to true so agents prompt for confirmation before executing destructive operations.",
            },
        )

    return CheckResult(
        check_id="security.annotation_consistency",
        status=Status.PASS,
        message="Annotations are consistent with tool behavior",
    )


def _check_destructive_without_guard(tool: dict) -> CheckResult:
    action = classify_tool_action(tool)
    if action != "destructive":
        return CheckResult(
            check_id="security.destructive_guard",
            status=Status.PASS,
            message="Tool is not destructive",
        )

    annotations = tool.get("annotations")
    if not isinstance(annotations, dict):
        return CheckResult(
            check_id="security.destructive_guard",
            status=Status.FAIL,
            message="Destructive tool has no annotations — agents cannot determine safety behavior without hints.",
            severity=Severity.HIGH,
            details={
                "location": "annotations",
                "current_value": None,
                "suggestion": 'Add annotations: {"destructiveHint": true, "readOnlyHint": false} so agents know to require user confirmation.',
            },
        )

    return CheckResult(
        check_id="security.destructive_guard",
        status=Status.PASS,
        message="Destructive tool has annotations defined",
    )


def _check_prompt_injection_surface(tool: dict) -> CheckResult:
    desc = tool.get("description") or ""
    match = _INJECTION_PATTERNS.search(desc)
    if match:
        return CheckResult(
            check_id="security.prompt_injection",
            status=Status.FAIL,
            message=f"Description contains suspicious pattern: '{match.group()}'",
            severity=Severity.MEDIUM,
            details={
                "matched": match.group(),
                "location": "description",
                "current_value": desc[:120] + ("..." if len(desc) > 120 else ""),
                "suggestion": f"Remove or rephrase the '{match.group()}' pattern from the description — it may trick LLM agents into unsafe behavior.",
            },
        )
    return CheckResult(
        check_id="security.prompt_injection",
        status=Status.PASS,
        message="No prompt injection patterns detected in description",
    )


def _check_data_exfil_risk(tool: dict) -> CheckResult:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        return CheckResult(
            check_id="security.data_exfil",
            status=Status.PASS,
            message="No input schema to check for exfiltration risk",
        )

    props = schema.get("properties")
    if not isinstance(props, dict):
        return CheckResult(
            check_id="security.data_exfil",
            status=Status.PASS,
            message="No properties to check for exfiltration risk",
        )

    flagged = [p for p in props if p.lower() in _EXFIL_PARAM_NAMES]
    if flagged:
        return CheckResult(
            check_id="security.data_exfil",
            status=Status.FAIL,
            message=f"Parameters {flagged} could be used for data exfiltration — an agent could be tricked into sending sensitive data to an attacker-controlled endpoint.",
            severity=Severity.MEDIUM,
            details={
                "flagged_params": flagged,
                "location": f"inputSchema.properties.[{', '.join(flagged)}]",
                "suggestion": "Constrain these parameters with enum values, URL pattern validation, or domain allowlists to prevent exfiltration.",
            },
        )

    return CheckResult(
        check_id="security.data_exfil",
        status=Status.PASS,
        message="No data exfiltration risk detected",
    )


def _check_sql_injection_surface(tool: dict) -> CheckResult:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        return CheckResult(
            check_id="security.sql_injection",
            status=Status.PASS,
            message="No input schema to check for injection risk",
        )

    props = schema.get("properties")
    if not isinstance(props, dict):
        return CheckResult(
            check_id="security.sql_injection",
            status=Status.PASS,
            message="No properties to check for injection risk",
        )

    for pname, pdef in props.items():
        if not isinstance(pdef, dict):
            continue
        if pname.lower() not in _QUERY_PARAM_NAMES:
            continue
        if pdef.get("type") != "string":
            continue
        if "enum" in pdef or "pattern" in pdef:
            continue
        return CheckResult(
            check_id="security.sql_injection",
            status=Status.FAIL,
            message=f"Parameter '{pname}' accepts freeform text that could contain SQL/commands — an agent could be manipulated into injecting malicious queries.",
            severity=Severity.HIGH,
            details={
                "parameter": pname,
                "location": f"inputSchema.properties.{pname}",
                "current_value": f'type: "{pdef.get("type")}", no enum/pattern constraint',
                "suggestion": f"Add an 'enum' array to restrict allowed values, or a 'pattern' regex to validate the format of '{pname}'.",
            },
        )

    return CheckResult(
        check_id="security.sql_injection",
        status=Status.PASS,
        message="No SQL injection surface detected",
    )


def _check_broad_permissions(tool: dict) -> CheckResult:
    desc = tool.get("description") or ""
    match = _BROAD_PERMISSION_PATTERNS.search(desc)
    if match:
        return CheckResult(
            check_id="security.broad_permissions",
            status=Status.FAIL,
            message=f"Description suggests overly broad permissions: '{match.group()}'",
            severity=Severity.HIGH,
            details={
                "matched": match.group(),
                "location": "description",
                "current_value": desc[:120] + ("..." if len(desc) > 120 else ""),
                "suggestion": "Scope the tool's permissions to specific actions rather than granting broad/arbitrary access. Describe exactly what it can do.",
            },
        )
    return CheckResult(
        check_id="security.broad_permissions",
        status=Status.PASS,
        message="No broad permission patterns detected",
    )


def check_tool_security(tool: dict) -> list[CheckResult]:
    return [
        _check_annotation_consistency(tool),
        _check_destructive_without_guard(tool),
        _check_prompt_injection_surface(tool),
        _check_data_exfil_risk(tool),
        _check_sql_injection_surface(tool),
        _check_broad_permissions(tool),
    ]


def check_security_all(tools: list[dict]) -> LayerResult:
    logger.info("Running security checks on %d tools", len(tools))
    results = []
    for tool in tools:
        name = tool.get("name", "<unnamed>")
        checks = check_tool_security(tool)
        for c in checks:
            c.tool_name = name
        tr = ToolResult(tool_name=name, checks=checks)
        results.append(tr)
    fails = sum(1 for r in results for c in r.checks if c.status == Status.FAIL)
    if fails:
        logger.warning("Security checks: %d failures across %d tools", fails, len(tools))
    return LayerResult(layer="security", tools=results)
