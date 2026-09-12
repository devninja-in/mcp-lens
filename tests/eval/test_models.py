from src.app.eval.models import (
    CheckResult, EvalReport, LayerResult, Severity, ScoringConfig,
    Status, TimingStats, ToolResult,
)


class TestCheckResult:
    def test_create(self):
        c = CheckResult(check_id="test.check", status=Status.PASS, message="ok")
        assert c.check_id == "test.check"
        assert c.status == Status.PASS
        assert c.severity == Severity.INFO

    def test_to_dict(self):
        c = CheckResult(
            check_id="test.check", status=Status.FAIL,
            message="bad", severity=Severity.HIGH,
        )
        d = c.to_dict()
        assert d["status"] == "fail"
        assert d["severity"] == "high"
        assert d["check_id"] == "test.check"

    def test_status_values(self):
        assert Status.PASS.value == "pass"
        assert Status.FAIL.value == "fail"
        assert Status.WARN.value == "warn"
        assert Status.SKIP.value == "skip"

    def test_severity_values(self):
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
        assert Severity.INFO.value == "info"


class TestToolResult:
    def test_passed_all_pass(self):
        tr = ToolResult(tool_name="t", checks=[
            CheckResult("a", Status.PASS, "ok"),
            CheckResult("b", Status.PASS, "ok"),
        ])
        assert tr.passed is True

    def test_passed_with_critical_fail(self):
        tr = ToolResult(tool_name="t", checks=[
            CheckResult("a", Status.PASS, "ok"),
            CheckResult("b", Status.FAIL, "bad", Severity.CRITICAL),
        ])
        assert tr.passed is False

    def test_passed_with_low_fail(self):
        tr = ToolResult(tool_name="t", checks=[
            CheckResult("a", Status.FAIL, "minor", Severity.LOW),
        ])
        assert tr.passed is True

    def test_counts(self):
        tr = ToolResult(tool_name="t", checks=[
            CheckResult("a", Status.PASS, ""),
            CheckResult("b", Status.FAIL, "", Severity.HIGH),
            CheckResult("c", Status.WARN, ""),
            CheckResult("d", Status.SKIP, ""),
        ])
        assert tr.pass_count == 1
        assert tr.fail_count == 1
        assert tr.warn_count == 1
        assert tr.skip_count == 1

    def test_to_dict(self):
        tr = ToolResult(tool_name="t", score=85.0, checks=[
            CheckResult("a", Status.PASS, "ok"),
        ])
        d = tr.to_dict()
        assert d["tool_name"] == "t"
        assert d["score"] == 85.0
        assert d["passed"] is True
        assert d["summary"]["pass"] == 1


class TestLayerResult:
    def test_totals(self):
        lr = LayerResult(
            layer="protocol",
            tools=[
                ToolResult("a", [CheckResult("x", Status.PASS, "")]),
                ToolResult("b", [CheckResult("y", Status.FAIL, "", Severity.HIGH)]),
            ],
            catalog_checks=[CheckResult("z", Status.PASS, "")],
        )
        assert lr.total_checks == 3
        assert lr.total_pass == 2
        assert lr.total_fail == 1

    def test_to_dict(self):
        lr = LayerResult(layer="quality", score=90.0)
        d = lr.to_dict()
        assert d["layer"] == "quality"
        assert d["score"] == 90.0
        assert d["tool_count"] == 0


class TestEvalReport:
    def test_to_dict(self):
        report = EvalReport(
            timestamp="2026-09-10",
            server_name="test-server",
            overall_score=91.4,
            gate_passed=True,
        )
        d = report.to_dict()
        assert d["server_name"] == "test-server"
        assert d["overall_score"] == 91.4
        assert d["gate_passed"] is True
        assert isinstance(d["layers"], dict)


class TestTimingStats:
    def test_percentiles(self):
        ts = TimingStats(
            tool_name="t",
            call_count=5,
            success_count=5,
            latencies_ms=[10, 20, 30, 40, 50],
        )
        assert ts.p50 == 30
        assert ts.p95 == 50
        assert ts.success_rate == 100.0

    def test_empty_latencies(self):
        ts = TimingStats(tool_name="t")
        assert ts.p50 == 0.0
        assert ts.success_rate == 0.0

    def test_to_dict(self):
        ts = TimingStats(tool_name="t", call_count=10, success_count=9, error_count=1)
        d = ts.to_dict()
        assert d["success_rate"] == 90.0


class TestScoringConfig:
    def test_defaults(self):
        cfg = ScoringConfig()
        assert cfg.gate_threshold == 70.0
        assert "protocol" in cfg.layer_weights
        assert "security" in cfg.fail_on_layers
