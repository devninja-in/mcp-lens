from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .models import CheckResult, Severity, Status

logger = logging.getLogger(__name__)

RuleCheckFn = Callable[..., CheckResult | list[CheckResult]]


@dataclass
class ParamDef:
    type: str  # "int", "float", "str", "list", "bool"
    default: Any = None
    description: str = ""


@dataclass
class RuleDef:
    rule_id: str
    layer: str
    description: str
    default_severity: Severity
    default_enabled: bool
    check_fn: RuleCheckFn
    params_schema: dict[str, ParamDef] = field(default_factory=dict)
    is_async: bool = False


RULE_REGISTRY: dict[str, RuleDef] = {}


def register_rule(
    rule_id: str,
    layer: str,
    description: str,
    default_severity: Severity = Severity.MEDIUM,
    default_enabled: bool = True,
    params_schema: dict[str, ParamDef] | None = None,
    is_async: bool = False,
) -> Callable:
    def decorator(fn: RuleCheckFn) -> RuleCheckFn:
        RULE_REGISTRY[rule_id] = RuleDef(
            rule_id=rule_id,
            layer=layer,
            description=description,
            default_severity=default_severity,
            default_enabled=default_enabled,
            check_fn=fn,
            params_schema=params_schema or {},
            is_async=is_async,
        )
        return fn

    return decorator


@dataclass
class RuleConfig:
    rule_id: str
    enabled: bool = True
    severity_override: Severity | None = None
    params: dict[str, Any] = field(default_factory=dict)


def get_effective_config(
    rule_def: RuleDef,
    db_config: RuleConfig | None = None,
) -> tuple[bool, Severity | None, dict[str, Any]]:
    enabled = db_config.enabled if db_config is not None else rule_def.default_enabled
    severity = (
        db_config.severity_override if db_config is not None and db_config.severity_override is not None else None
    )
    params = {}
    for key, param_def in rule_def.params_schema.items():
        params[key] = param_def.default
    if db_config is not None:
        for key, value in db_config.params.items():
            if key in rule_def.params_schema:
                params[key] = value
    return enabled, severity, params


def apply_severity_override(check: CheckResult, severity: Severity | None) -> CheckResult:
    if severity is not None and check.status in (Status.FAIL, Status.WARN) and check.severity != severity:
        check.severity = severity
    return check


def get_rules_for_layer(layer: str) -> dict[str, RuleDef]:
    return {rid: rd for rid, rd in RULE_REGISTRY.items() if rd.layer == layer}


def export_rules(db_configs: dict[str, RuleConfig]) -> list[dict]:
    exported = []
    for rule_id, config in db_configs.items():
        if rule_id not in RULE_REGISTRY:
            continue
        rule_def = RULE_REGISTRY[rule_id]
        has_override = (
            config.enabled != rule_def.default_enabled or config.severity_override is not None or config.params
        )
        if has_override:
            entry: dict[str, Any] = {"rule_id": rule_id, "enabled": config.enabled}
            entry["severity"] = config.severity_override.value if config.severity_override else None
            entry["params"] = config.params if config.params else None
            exported.append(entry)
    return exported


def import_rules(data: list[dict]) -> tuple[list[RuleConfig], list[str]]:
    configs = []
    warnings = []
    for entry in data:
        rule_id = entry.get("rule_id", "")
        if rule_id not in RULE_REGISTRY:
            warnings.append(f"Unknown rule '{rule_id}' — skipped")
            continue
        severity = None
        if entry.get("severity"):
            try:
                severity = Severity(entry["severity"])
            except ValueError:
                warnings.append(f"Invalid severity '{entry['severity']}' for rule '{rule_id}' — skipped")
                severity = None
        configs.append(
            RuleConfig(
                rule_id=rule_id,
                enabled=entry.get("enabled", True),
                severity_override=severity,
                params=entry.get("params") or {},
            )
        )
    return configs, warnings


def get_all_rule_defs() -> list[dict[str, Any]]:
    result = []
    for rule_id, rd in RULE_REGISTRY.items():
        params_schema = {}
        for key, pd in rd.params_schema.items():
            params_schema[key] = {
                "type": pd.type,
                "default": pd.default,
                "description": pd.description,
            }
        result.append(
            {
                "rule_id": rule_id,
                "layer": rd.layer,
                "description": rd.description,
                "default_severity": rd.default_severity.value,
                "default_enabled": rd.default_enabled,
                "params_schema": params_schema,
            }
        )
    return result
