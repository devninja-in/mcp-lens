import json

from src.app.eval.models import (
    CheckResult, EvalReport, LayerResult, Status, ToolResult,
)
from src.app.eval.report import render_json, render_text, save_report


def _make_report() -> EvalReport:
    return EvalReport(
        timestamp="2026-09-10T12:00:00",
        server_name="test-server",
        overall_score=85.0,
        gate_passed=True,
        layers={
            "protocol": LayerResult(
                layer="protocol",
                score=90.0,
                tools=[ToolResult("search", [
                    CheckResult("p.name", Status.PASS, "Name is valid"),
                    CheckResult("p.desc", Status.WARN, "Short description"),
                ])],
            ),
        },
    )


class TestRenderJson:
    def test_valid_json(self):
        report = _make_report()
        output = render_json(report, redact=False)
        data = json.loads(output)
        assert data["server_name"] == "test-server"
        assert data["overall_score"] == 85.0

    def test_indented(self):
        output = render_json(_make_report(), redact=False)
        assert "\n" in output

    def test_redaction_applied(self):
        report = _make_report()
        report.metadata = {"api_key": "sk-secret-123"}
        output = render_json(report, redact=True)
        data = json.loads(output)
        assert data["metadata"]["api_key"] == "***REDACTED***"


class TestRenderText:
    def test_contains_server_name(self):
        output = render_text(_make_report())
        assert "test-server" in output

    def test_contains_score(self):
        output = render_text(_make_report())
        assert "85.0" in output

    def test_contains_gate_status(self):
        output = render_text(_make_report())
        assert "PASSED" in output

    def test_shows_non_pass_checks(self):
        output = render_text(_make_report())
        assert "WARN" in output

    def test_gate_failed_text(self):
        report = _make_report()
        report.gate_passed = False
        output = render_text(report)
        assert "FAILED" in output


class TestSaveReport:
    def test_save_json(self, tmp_path):
        report = _make_report()
        path = tmp_path / "report.json"
        save_report(report, path, fmt="json", redact=False)
        data = json.loads(path.read_text())
        assert data["server_name"] == "test-server"

    def test_save_text(self, tmp_path):
        report = _make_report()
        path = tmp_path / "report.txt"
        save_report(report, path, fmt="text")
        content = path.read_text()
        assert "test-server" in content

    def test_creates_parent_dirs(self, tmp_path):
        report = _make_report()
        path = tmp_path / "nested" / "dir" / "report.json"
        save_report(report, path, fmt="json", redact=False)
        assert path.exists()
