"""Tests for the rules configuration system: registry, DB CRUD, API routes, export/import."""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

import src.app.database as db_module
from src.app.database import (
    delete_all_rule_configs,
    get_all_rule_configs,
    get_rule_config,
    seed_rule_configs,
    set_rule_config,
)
from src.app.eval.models import CheckResult, Severity, Status
from src.app.eval.registry import (
    RULE_REGISTRY,
    ParamDef,
    RuleConfig,
    RuleDef,
    apply_severity_override,
    export_rules,
    get_all_rule_defs,
    get_effective_config,
    get_rules_for_layer,
    import_rules,
)
from src.app.main import app


async def _noop():
    pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(db_module, "_migrate_tokens_json", _noop)
    monkeypatch.setattr(db_module, "_migrate_mcp_json", _noop)
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()
    yield
    await db_module.dispose_db()


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(db_module, "_migrate_tokens_json", _noop)
    monkeypatch.setattr(db_module, "_migrate_mcp_json", _noop)
    db_module._engine = None
    db_module._session_factory = None
    await db_module.init_db()
    rule_defs = get_all_rule_defs()
    await seed_rule_configs(rule_defs)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    await db_module.dispose_db()


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_registry_has_rules(self):
        assert len(RULE_REGISTRY) > 0

    def test_all_layers_represented(self):
        layers = {rd.layer for rd in RULE_REGISTRY.values()}
        assert "protocol" in layers
        assert "quality" in layers
        assert "security" in layers

    def test_rule_def_fields(self):
        for rule_id, rd in RULE_REGISTRY.items():
            assert rd.rule_id == rule_id
            assert rd.layer in ("protocol", "quality", "security", "llm", "agent")
            assert rd.description
            assert isinstance(rd.default_severity, Severity)
            assert isinstance(rd.default_enabled, bool)
            assert callable(rd.check_fn)

    def test_get_rules_for_layer_filters(self):
        protocol_rules = get_rules_for_layer("protocol")
        for rd in protocol_rules.values():
            assert rd.layer == "protocol"

        quality_rules = get_rules_for_layer("quality")
        for rd in quality_rules.values():
            assert rd.layer == "quality"

    def test_get_rules_for_nonexistent_layer(self):
        rules = get_rules_for_layer("nonexistent")
        assert rules == {}

    def test_get_all_rule_defs_format(self):
        defs = get_all_rule_defs()
        assert isinstance(defs, list)
        assert len(defs) > 0
        for d in defs:
            assert "rule_id" in d
            assert "layer" in d
            assert "description" in d
            assert "default_severity" in d
            assert "default_enabled" in d
            assert "params_schema" in d


# ---------------------------------------------------------------------------
# get_effective_config tests
# ---------------------------------------------------------------------------


class TestGetEffectiveConfig:
    def _make_rule_def(self, **kwargs):
        defaults = dict(
            rule_id="test.rule",
            layer="test",
            description="test",
            default_severity=Severity.MEDIUM,
            default_enabled=True,
            check_fn=lambda tool: None,
            params_schema={"threshold": ParamDef(type="int", default=10, description="threshold")},
        )
        defaults.update(kwargs)
        return RuleDef(**defaults)

    def test_defaults_when_no_db_config(self):
        rd = self._make_rule_def()
        enabled, severity, params = get_effective_config(rd, None)
        assert enabled is True
        assert severity is None
        assert params == {"threshold": 10}

    def test_db_override_enabled(self):
        rd = self._make_rule_def()
        config = RuleConfig(rule_id="test.rule", enabled=False)
        enabled, severity, params = get_effective_config(rd, config)
        assert enabled is False

    def test_db_override_severity(self):
        rd = self._make_rule_def()
        config = RuleConfig(rule_id="test.rule", severity_override=Severity.CRITICAL)
        enabled, severity, params = get_effective_config(rd, config)
        assert severity == Severity.CRITICAL

    def test_no_severity_override_returns_none(self):
        rd = self._make_rule_def()
        config = RuleConfig(rule_id="test.rule", severity_override=None)
        enabled, severity, params = get_effective_config(rd, config)
        assert severity is None

    def test_db_override_params(self):
        rd = self._make_rule_def()
        config = RuleConfig(rule_id="test.rule", params={"threshold": 42})
        enabled, severity, params = get_effective_config(rd, config)
        assert params["threshold"] == 42

    def test_unknown_param_ignored(self):
        rd = self._make_rule_def()
        config = RuleConfig(rule_id="test.rule", params={"unknown_key": "value"})
        enabled, severity, params = get_effective_config(rd, config)
        assert "unknown_key" not in params
        assert params["threshold"] == 10


# ---------------------------------------------------------------------------
# apply_severity_override tests
# ---------------------------------------------------------------------------


class TestApplySeverityOverride:
    def test_overrides_fail_severity(self):
        check = CheckResult(check_id="t", status=Status.FAIL, message="m", severity=Severity.MEDIUM)
        apply_severity_override(check, Severity.CRITICAL)
        assert check.severity == Severity.CRITICAL

    def test_overrides_warn_severity(self):
        check = CheckResult(check_id="t", status=Status.WARN, message="m", severity=Severity.MEDIUM)
        apply_severity_override(check, Severity.HIGH)
        assert check.severity == Severity.HIGH

    def test_does_not_override_pass(self):
        check = CheckResult(check_id="t", status=Status.PASS, message="m", severity=Severity.MEDIUM)
        apply_severity_override(check, Severity.CRITICAL)
        assert check.severity == Severity.MEDIUM

    def test_none_severity_preserves_original(self):
        check = CheckResult(check_id="t", status=Status.FAIL, message="m", severity=Severity.HIGH)
        apply_severity_override(check, None)
        assert check.severity == Severity.HIGH

    def test_same_severity_is_noop(self):
        check = CheckResult(check_id="t", status=Status.FAIL, message="m", severity=Severity.CRITICAL)
        apply_severity_override(check, Severity.CRITICAL)
        assert check.severity == Severity.CRITICAL


# ---------------------------------------------------------------------------
# Export / Import tests
# ---------------------------------------------------------------------------


class TestExportImport:
    def test_export_only_overridden_rules(self):
        configs = {
            "rule.a": RuleConfig(rule_id="rule.a", enabled=True, severity_override=None, params={}),
            "rule.b": RuleConfig(rule_id="rule.b", enabled=False, severity_override=None, params={}),
        }
        first_rule = next(iter(RULE_REGISTRY.keys()))
        configs[first_rule] = RuleConfig(rule_id=first_rule, enabled=False, severity_override=Severity.HIGH, params={})
        exported = export_rules(configs)
        exported_ids = [e["rule_id"] for e in exported]
        assert first_rule in exported_ids
        assert "rule.a" not in exported_ids  # unknown rule, skipped

    def test_import_valid_rules(self):
        first_rule = next(iter(RULE_REGISTRY.keys()))
        data = [
            {"rule_id": first_rule, "enabled": False, "severity": "high", "params": None},
        ]
        configs, warnings = import_rules(data)
        assert len(configs) == 1
        assert configs[0].rule_id == first_rule
        assert configs[0].enabled is False
        assert configs[0].severity_override == Severity.HIGH
        assert len(warnings) == 0

    def test_import_unknown_rule_warns(self):
        data = [
            {"rule_id": "nonexistent.rule", "enabled": True},
        ]
        configs, warnings = import_rules(data)
        assert len(configs) == 0
        assert len(warnings) == 1
        assert "Unknown" in warnings[0]

    def test_import_invalid_severity_warns(self):
        first_rule = next(iter(RULE_REGISTRY.keys()))
        data = [
            {"rule_id": first_rule, "severity": "superbad"},
        ]
        configs, warnings = import_rules(data)
        assert len(configs) == 1
        assert configs[0].severity_override is None
        assert len(warnings) == 1
        assert "Invalid severity" in warnings[0]

    def test_roundtrip_export_import(self):
        first_rule = next(iter(RULE_REGISTRY.keys()))
        original = {
            first_rule: RuleConfig(
                rule_id=first_rule,
                enabled=False,
                severity_override=Severity.LOW,
                params={"some_key": "val"},
            ),
        }
        exported = export_rules(original)
        assert len(exported) > 0
        imported, warnings = import_rules(exported)
        assert len(imported) == 1
        assert imported[0].rule_id == first_rule
        assert imported[0].enabled is False
        assert imported[0].severity_override == Severity.LOW


# ---------------------------------------------------------------------------
# DB CRUD tests
# ---------------------------------------------------------------------------


class TestRuleConfigDB:
    @pytest.mark.asyncio
    async def test_set_and_get(self, db):
        await set_rule_config("test.rule1", enabled=True, severity_override="high")
        result = await get_rule_config("test.rule1")
        assert result is not None
        assert result["enabled"] is True
        assert result["severity_override"] == "high"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db):
        result = await get_rule_config("nonexistent.rule")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_with_config_data(self, db):
        await set_rule_config("test.rule2", config_data={"threshold": 42, "items": [1, 2]})
        result = await get_rule_config("test.rule2")
        assert result is not None
        assert result["config_data"] == {"threshold": 42, "items": [1, 2]}

    @pytest.mark.asyncio
    async def test_update_existing(self, db):
        await set_rule_config("test.rule3", enabled=True)
        await set_rule_config("test.rule3", enabled=False, severity_override="critical")
        result = await get_rule_config("test.rule3")
        assert result["enabled"] is False
        assert result["severity_override"] == "critical"

    @pytest.mark.asyncio
    async def test_get_all(self, db):
        await set_rule_config("r1", enabled=True)
        await set_rule_config("r2", enabled=False)
        all_configs = await get_all_rule_configs()
        assert "r1" in all_configs
        assert "r2" in all_configs
        assert all_configs["r1"]["enabled"] is True
        assert all_configs["r2"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_delete_all(self, db):
        await set_rule_config("r1", enabled=True)
        await set_rule_config("r2", enabled=True)
        count = await delete_all_rule_configs()
        assert count == 2
        all_configs = await get_all_rule_configs()
        assert len(all_configs) == 0

    @pytest.mark.asyncio
    async def test_seed_only_new(self, db):
        await set_rule_config("existing.rule", enabled=False, severity_override="high")
        rule_defs = [
            {"rule_id": "existing.rule", "default_enabled": True},
            {"rule_id": "new.rule", "default_enabled": True},
        ]
        seeded = await seed_rule_configs(rule_defs)
        assert seeded == 1
        existing = await get_rule_config("existing.rule")
        assert existing["enabled"] is False
        assert existing["severity_override"] == "high"


# ---------------------------------------------------------------------------
# API route tests
# ---------------------------------------------------------------------------


class TestRulesAPI:
    @pytest.mark.asyncio
    async def test_list_rules(self, client):
        resp = client.get("/api/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "rules" in data
        assert "total" in data
        assert data["total"] > 0
        rule = data["rules"][0]
        assert "rule_id" in rule
        assert "layer" in rule
        assert "enabled" in rule
        assert "default_severity" in rule

    @pytest.mark.asyncio
    async def test_update_rule_enable_disable(self, client):
        rules = client.get("/api/rules").json()["rules"]
        rule_id = rules[0]["rule_id"]

        resp = client.put(f"/api/rules/{rule_id}", json={"enabled": False})
        assert resp.status_code == 200

        rules_after = client.get("/api/rules").json()["rules"]
        updated = next(r for r in rules_after if r["rule_id"] == rule_id)
        assert updated["enabled"] is False

    @pytest.mark.asyncio
    async def test_update_rule_severity(self, client):
        rules = client.get("/api/rules").json()["rules"]
        rule_id = rules[0]["rule_id"]

        resp = client.put(f"/api/rules/{rule_id}", json={"severity_override": "low"})
        assert resp.status_code == 200

        rules_after = client.get("/api/rules").json()["rules"]
        updated = next(r for r in rules_after if r["rule_id"] == rule_id)
        assert updated["severity_override"] == "low"

    @pytest.mark.asyncio
    async def test_update_rule_invalid_severity(self, client):
        rules = client.get("/api/rules").json()["rules"]
        rule_id = rules[0]["rule_id"]

        resp = client.put(f"/api/rules/{rule_id}", json={"severity_override": "superbad"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_unknown_rule(self, client):
        resp = client.put("/api/rules/nonexistent.rule", json={"enabled": False})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_rule_params(self, client):
        rules = client.get("/api/rules").json()["rules"]
        rule_with_params = next((r for r in rules if r["params_schema"]), None)
        if rule_with_params is None:
            pytest.skip("No rules with params found")

        rule_id = rule_with_params["rule_id"]
        param_key = next(iter(rule_with_params["params_schema"]))
        new_params = {param_key: 999}

        resp = client.put(f"/api/rules/{rule_id}", json={"params": new_params})
        assert resp.status_code == 200

        rules_after = client.get("/api/rules").json()["rules"]
        updated = next(r for r in rules_after if r["rule_id"] == rule_id)
        assert updated["params"][param_key] == 999

    @pytest.mark.asyncio
    async def test_reset_rules(self, client):
        rules = client.get("/api/rules").json()["rules"]
        rule_id = rules[0]["rule_id"]
        client.put(f"/api/rules/{rule_id}", json={"enabled": False})

        resp = client.post("/api/rules/reset")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        rules_after = client.get("/api/rules").json()["rules"]
        reset_rule = next(r for r in rules_after if r["rule_id"] == rule_id)
        assert reset_rule["enabled"] == reset_rule["default_enabled"]

    @pytest.mark.asyncio
    async def test_export_rules(self, client):
        rules = client.get("/api/rules").json()["rules"]
        rule_id = rules[0]["rule_id"]
        client.put(f"/api/rules/{rule_id}", json={"enabled": False, "severity_override": "low"})

        resp = client.get("/api/rules/export")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "exported_at" in data
        assert "rules" in data
        exported_ids = [r["rule_id"] for r in data["rules"]]
        assert rule_id in exported_ids

    @pytest.mark.asyncio
    async def test_import_rules(self, client):
        rules = client.get("/api/rules").json()["rules"]
        rule_id = rules[0]["rule_id"]

        import_data = {
            "version": "1.0",
            "rules": [
                {"rule_id": rule_id, "enabled": False, "severity": "critical", "params": None},
            ],
        }
        resp = client.post("/api/rules/import", json=import_data)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported_count"] == 1
        assert data["warnings"] == []

        rules_after = client.get("/api/rules").json()["rules"]
        imported_rule = next(r for r in rules_after if r["rule_id"] == rule_id)
        assert imported_rule["enabled"] is False
        assert imported_rule["severity_override"] == "critical"

    @pytest.mark.asyncio
    async def test_import_unknown_rule_warns(self, client):
        import_data = {
            "version": "1.0",
            "rules": [
                {"rule_id": "totally.fake.rule", "enabled": True},
            ],
        }
        resp = client.post("/api/rules/import", json=import_data)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported_count"] == 0
        assert len(data["warnings"]) == 1

    @pytest.mark.asyncio
    async def test_export_import_roundtrip(self, client):
        rules = client.get("/api/rules").json()["rules"]
        rule_id = rules[0]["rule_id"]
        client.put(f"/api/rules/{rule_id}", json={"enabled": False, "severity_override": "high"})

        exported = client.get("/api/rules/export").json()

        client.post("/api/rules/reset")

        resp = client.post("/api/rules/import", json=exported)
        assert resp.status_code == 200

        rules_after = client.get("/api/rules").json()["rules"]
        reimported = next(r for r in rules_after if r["rule_id"] == rule_id)
        assert reimported["enabled"] is False
        assert reimported["severity_override"] == "high"

    @pytest.mark.asyncio
    async def test_export_with_invalid_severity_in_db(self, client):
        rules = client.get("/api/rules").json()["rules"]
        rule_id = rules[0]["rule_id"]
        await set_rule_config(rule_id, enabled=False, severity_override="bogus_value")

        resp = client.get("/api/rules/export")
        assert resp.status_code == 200
        data = resp.json()
        exported_rule = next((r for r in data["rules"] if r["rule_id"] == rule_id), None)
        assert exported_rule is not None
        assert exported_rule["severity"] is None


# ---------------------------------------------------------------------------
# Eval layer integration: severity override respects per-check severity
# ---------------------------------------------------------------------------


class TestSeverityOverrideInEval:
    def test_annotation_consistency_preserves_per_case_severity(self):
        from src.app.eval.security import check_tool_security

        tool = {
            "name": "delete_records",
            "description": "Deletes records",
            "annotations": {"destructiveHint": False},
        }
        checks = check_tool_security(tool)
        ann = next(c for c in checks if c.check_id == "security.annotation_consistency")
        assert ann.status == Status.FAIL
        assert ann.severity == Severity.HIGH

    def test_annotation_consistency_readonly_is_critical(self):
        from src.app.eval.security import check_tool_security

        tool = {
            "name": "delete_records",
            "description": "Deletes records",
            "annotations": {"readOnlyHint": True},
        }
        checks = check_tool_security(tool)
        ann = next(c for c in checks if c.check_id == "security.annotation_consistency")
        assert ann.status == Status.FAIL
        assert ann.severity == Severity.CRITICAL

    def test_db_severity_override_applied_to_checks(self):
        from src.app.eval.security import check_tool_security

        tool = {
            "name": "delete_records",
            "description": "Deletes records",
            "annotations": {"destructiveHint": False},
        }
        db_configs = {
            "security.annotation_consistency": RuleConfig(
                rule_id="security.annotation_consistency",
                severity_override=Severity.LOW,
            ),
        }
        checks = check_tool_security(tool, db_configs=db_configs)
        ann = next(c for c in checks if c.check_id == "security.annotation_consistency")
        assert ann.status == Status.FAIL
        assert ann.severity == Severity.LOW

    def test_disabled_rule_skipped(self):
        from src.app.eval.security import check_tool_security

        tool = {
            "name": "delete_records",
            "description": "Deletes records",
            "annotations": {"destructiveHint": False},
        }
        db_configs = {
            "security.annotation_consistency": RuleConfig(
                rule_id="security.annotation_consistency",
                enabled=False,
            ),
        }
        checks = check_tool_security(tool, db_configs=db_configs)
        ann_checks = [c for c in checks if c.check_id == "security.annotation_consistency"]
        assert len(ann_checks) == 0

    def test_protocol_rules_respect_config(self):
        from src.app.eval.protocol import check_tool_protocol

        tool = {"name": "test_tool"}
        db_configs = {
            "protocol.has_description": RuleConfig(
                rule_id="protocol.has_description",
                enabled=False,
            ),
        }
        checks = check_tool_protocol(tool, db_configs=db_configs)
        desc_checks = [c for c in checks if c.check_id == "protocol.has_description"]
        assert len(desc_checks) == 0

    def test_quality_rules_respect_config(self):
        from src.app.eval.quality import check_tool_quality

        tool = {
            "name": "test_tool",
            "description": "A tool for testing things",
            "inputSchema": {"type": "object", "properties": {}},
        }
        db_configs = {
            "quality.desc_actionable": RuleConfig(
                rule_id="quality.desc_actionable",
                enabled=False,
            ),
        }
        checks = check_tool_quality(tool, db_configs=db_configs)
        desc_checks = [c for c in checks if c.check_id == "quality.desc_actionable"]
        assert len(desc_checks) == 0
