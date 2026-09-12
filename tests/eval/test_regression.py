from src.app.eval.models import (
    CheckResult,
    EvalReport,
    LayerResult,
    Severity,
    Status,
    ToolResult,
)
from src.app.eval.regression import RegressionDiff, compare_reports


def _make_report(score: float, layers: dict | None = None) -> EvalReport:
    return EvalReport(
        timestamp="2026-09-10",
        server_name="test",
        overall_score=score,
        gate_passed=True,
        layers=layers or {},
    )


class TestCompareReports:
    def test_no_change(self):
        baseline = _make_report(80.0)
        current = _make_report(80.0)
        diff = compare_reports(baseline, current)
        assert diff.score_delta == 0.0
        assert diff.regressed is False

    def test_improvement(self):
        baseline = _make_report(70.0)
        current = _make_report(85.0)
        diff = compare_reports(baseline, current)
        assert diff.score_delta == 15.0
        assert diff.regressed is False

    def test_regression_detected(self):
        baseline = _make_report(80.0)
        current = _make_report(70.0)
        diff = compare_reports(baseline, current, max_regression_drop=5.0)
        assert diff.score_delta == -10.0
        assert diff.regressed is True

    def test_small_drop_not_regression(self):
        baseline = _make_report(80.0)
        current = _make_report(77.0)
        diff = compare_reports(baseline, current, max_regression_drop=5.0)
        assert diff.regressed is False

    def test_new_failures_detected(self):
        baseline = _make_report(
            80.0,
            layers={
                "protocol": LayerResult(
                    layer="protocol",
                    tools=[ToolResult("t", [
                        CheckResult("a", Status.PASS, "ok"),
                    ])],
                ),
            },
        )
        current = _make_report(
            70.0,
            layers={
                "protocol": LayerResult(
                    layer="protocol",
                    tools=[ToolResult("t", [
                        CheckResult("a", Status.FAIL, "broken", Severity.HIGH),
                    ])],
                ),
            },
        )
        diff = compare_reports(baseline, current)
        assert len(diff.new_failures) == 1
        assert diff.new_failures[0]["check_id"] == "a"

    def test_fixed_failures_detected(self):
        baseline = _make_report(
            70.0,
            layers={
                "protocol": LayerResult(
                    layer="protocol",
                    tools=[ToolResult("t", [
                        CheckResult("a", Status.FAIL, "broken", Severity.HIGH),
                    ])],
                ),
            },
        )
        current = _make_report(
            80.0,
            layers={
                "protocol": LayerResult(
                    layer="protocol",
                    tools=[ToolResult("t", [
                        CheckResult("a", Status.PASS, "fixed"),
                    ])],
                ),
            },
        )
        diff = compare_reports(baseline, current)
        assert len(diff.fixed) == 1

    def test_per_layer_deltas(self):
        baseline = _make_report(
            80.0,
            layers={"protocol": LayerResult(layer="protocol", score=90.0)},
        )
        current = _make_report(
            85.0,
            layers={"protocol": LayerResult(layer="protocol", score=95.0)},
        )
        diff = compare_reports(baseline, current)
        assert diff.per_layer_deltas["protocol"] == 5.0


class TestRegressionDiff:
    def test_to_dict(self):
        diff = RegressionDiff(
            score_delta=-3.0,
            per_layer_deltas={"protocol": -2.0},
            new_failures=[{"layer": "protocol", "tool": "t", "check_id": "a", "message": "bad"}],
            fixed=[],
            regressed=False,
        )
        d = diff.to_dict()
        assert d["score_delta"] == -3.0
        assert len(d["new_failures"]) == 1
        assert d["regressed"] is False
