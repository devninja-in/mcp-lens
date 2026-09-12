from src.app.eval.models import (
    CheckResult,
    EvalReport,
    LayerResult,
    ScoringConfig,
    Severity,
    Status,
    ToolResult,
)
from src.app.eval.scoring import apply_scoring, compute_layer_score, compute_overall_score


class TestComputeLayerScore:
    def test_all_pass(self):
        lr = LayerResult(
            layer="protocol",
            tools=[
                ToolResult(
                    "t",
                    [
                        CheckResult("a", Status.PASS, "ok"),
                        CheckResult("b", Status.PASS, "ok"),
                    ],
                )
            ],
        )
        assert compute_layer_score(lr) == 100.0

    def test_all_fail(self):
        lr = LayerResult(
            layer="protocol",
            tools=[
                ToolResult(
                    "t",
                    [
                        CheckResult("a", Status.FAIL, "bad", Severity.HIGH),
                    ],
                )
            ],
        )
        assert compute_layer_score(lr) == 0.0

    def test_mixed(self):
        lr = LayerResult(
            layer="protocol",
            tools=[
                ToolResult(
                    "t",
                    [
                        CheckResult("a", Status.PASS, "ok", Severity.HIGH),
                        CheckResult("b", Status.FAIL, "bad", Severity.LOW),
                    ],
                )
            ],
        )
        score = compute_layer_score(lr)
        assert 0 < score < 100

    def test_skip_counts_as_pass(self):
        lr = LayerResult(
            layer="protocol",
            tools=[
                ToolResult(
                    "t",
                    [
                        CheckResult("a", Status.SKIP, "skip"),
                    ],
                )
            ],
        )
        assert compute_layer_score(lr) == 100.0

    def test_empty_checks(self):
        lr = LayerResult(layer="protocol")
        assert compute_layer_score(lr) == 100.0

    def test_severity_weighting(self):
        lr_critical = LayerResult(
            layer="x",
            tools=[
                ToolResult(
                    "t",
                    [
                        CheckResult("a", Status.FAIL, "", Severity.CRITICAL),
                        CheckResult("b", Status.PASS, "", Severity.INFO),
                    ],
                )
            ],
        )
        lr_low = LayerResult(
            layer="x",
            tools=[
                ToolResult(
                    "t",
                    [
                        CheckResult("a", Status.FAIL, "", Severity.LOW),
                        CheckResult("b", Status.PASS, "", Severity.INFO),
                    ],
                )
            ],
        )
        assert compute_layer_score(lr_critical) < compute_layer_score(lr_low)


class TestComputeOverallScore:
    def test_weighted_average(self):
        layers = {
            "protocol": LayerResult(
                layer="protocol",
                tools=[ToolResult("t", [CheckResult("a", Status.PASS, "ok")])],
            ),
            "quality": LayerResult(
                layer="quality",
                tools=[ToolResult("t", [CheckResult("a", Status.PASS, "ok")])],
            ),
        }
        config = ScoringConfig(layer_weights={"protocol": 0.5, "quality": 0.5})
        score, gate = compute_overall_score(layers, config)
        assert score == 100.0
        assert gate is True

    def test_gate_fails_below_threshold(self):
        layers = {
            "protocol": LayerResult(
                layer="protocol",
                tools=[
                    ToolResult(
                        "t",
                        [
                            CheckResult("a", Status.FAIL, "bad", Severity.CRITICAL),
                        ],
                    )
                ],
            ),
        }
        config = ScoringConfig(
            layer_weights={"protocol": 1.0},
            gate_threshold=50.0,
        )
        score, gate = compute_overall_score(layers, config)
        assert score < 50
        assert gate is False

    def test_critical_security_fails_gate(self):
        layers = {
            "security": LayerResult(
                layer="security",
                tools=[
                    ToolResult(
                        "t",
                        [
                            CheckResult("a", Status.FAIL, "bad", Severity.CRITICAL),
                        ],
                    )
                ],
            ),
            "protocol": LayerResult(
                layer="protocol",
                tools=[ToolResult("t", [CheckResult("b", Status.PASS, "ok")])],
            ),
        }
        config = ScoringConfig(
            layer_weights={"security": 0.5, "protocol": 0.5},
            gate_threshold=0.0,
            fail_on_layers=["security"],
        )
        _, gate = compute_overall_score(layers, config)
        assert gate is False


class TestApplyScoring:
    def test_updates_report(self):
        report = EvalReport(
            timestamp="2026-09-10",
            server_name="test",
            layers={
                "protocol": LayerResult(
                    layer="protocol",
                    tools=[ToolResult("t", [CheckResult("a", Status.PASS, "ok")])],
                ),
            },
        )
        config = ScoringConfig(layer_weights={"protocol": 1.0})
        result = apply_scoring(report, config)
        assert result.overall_score == 100.0
        assert result.gate_passed is True
