from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..database import (
    delete_all_rule_configs,
    get_all_rule_configs,
    seed_rule_configs,
    set_rule_config,
)
from ..eval.registry import (
    RULE_REGISTRY,
    RuleConfig,
    Severity,
    export_rules,
    get_all_rule_defs,
    import_rules,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _build_rule_response(
    rule_defs: list[dict],
    db_configs: dict[str, dict],
) -> list[dict[str, Any]]:
    rules = []
    for rd in rule_defs:
        rule_id = rd["rule_id"]
        db = db_configs.get(rule_id, {})
        rules.append(
            {
                "rule_id": rule_id,
                "layer": rd["layer"],
                "description": rd["description"],
                "default_severity": rd["default_severity"],
                "default_enabled": rd["default_enabled"],
                "params_schema": rd["params_schema"],
                "enabled": db.get("enabled", rd["default_enabled"]),
                "severity_override": db.get("severity_override"),
                "params": db.get("config_data") or {},
            }
        )
    return rules


@router.get("")
async def list_rules() -> dict:
    rule_defs = get_all_rule_defs()
    db_configs = await get_all_rule_configs()
    rules = _build_rule_response(rule_defs, db_configs)
    return {"rules": rules, "total": len(rules)}


class RuleUpdateRequest(BaseModel):
    enabled: bool | None = None
    severity_override: str | None = None
    params: dict[str, Any] | None = None


@router.put("/{rule_id:path}")
async def update_rule(rule_id: str, body: RuleUpdateRequest) -> dict:
    if rule_id not in RULE_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown rule: {rule_id}")

    rule_def = RULE_REGISTRY[rule_id]
    db_configs = await get_all_rule_configs()
    current = db_configs.get(rule_id, {})

    enabled = body.enabled if body.enabled is not None else current.get("enabled", rule_def.default_enabled)
    severity_override = body.severity_override
    if severity_override is None and "severity_override" in current:
        severity_override = current["severity_override"]
    if severity_override is not None:
        try:
            Severity(severity_override)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid severity: {severity_override}. Valid: critical, high, medium, low, info",
            ) from exc

    params = body.params
    if params is None:
        params = current.get("config_data") or {}

    await set_rule_config(
        rule_id=rule_id,
        enabled=enabled,
        severity_override=severity_override,
        config_data=params if params else None,
    )
    logger.info("Rule '%s' updated: enabled=%s severity=%s", rule_id, enabled, severity_override)
    return {"success": True, "rule_id": rule_id}


@router.post("/reset")
async def reset_rules() -> dict:
    count = await delete_all_rule_configs()
    rule_defs = get_all_rule_defs()
    seeded = await seed_rule_configs(rule_defs)
    logger.info("Rules reset: deleted %d, re-seeded %d", count, seeded)
    return {"success": True, "reset_count": count, "seeded_count": seeded}


@router.get("/export")
async def export_rules_endpoint() -> dict:
    db_configs_raw = await get_all_rule_configs()
    db_configs: dict[str, RuleConfig] = {}
    for rule_id, data in db_configs_raw.items():
        severity = None
        if data.get("severity_override"):
            try:
                severity = Severity(data["severity_override"])
            except ValueError:
                severity = None
        db_configs[rule_id] = RuleConfig(
            rule_id=rule_id,
            enabled=data.get("enabled", True),
            severity_override=severity,
            params=data.get("config_data") or {},
        )

    exported = export_rules(db_configs)
    return {
        "version": "1.0",
        "exported_at": datetime.now(UTC).isoformat(),
        "rules": exported,
    }


class ImportRequest(BaseModel):
    version: str = "1.0"
    rules: list[dict[str, Any]]


@router.post("/import")
async def import_rules_endpoint(body: ImportRequest) -> dict:
    configs, warnings = import_rules(body.rules)
    for config in configs:
        await set_rule_config(
            rule_id=config.rule_id,
            enabled=config.enabled,
            severity_override=config.severity_override.value if config.severity_override else None,
            config_data=config.params if config.params else None,
        )
    logger.info("Imported %d rules (%d warnings)", len(configs), len(warnings))
    return {
        "success": True,
        "imported_count": len(configs),
        "warnings": warnings,
    }
