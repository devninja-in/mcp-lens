import asyncio

from src.app.eval.mock_server import GOOD_TOOLS, BAD_TOOLS, get_mock_tools
from src.app.eval.protocol import check_protocol_all
from src.app.eval.quality import check_quality_all
from src.app.eval.security import check_security_all
from src.app.eval.overlap import detect_overlaps
from src.app.eval.scoring import apply_scoring, compute_layer_score
from src.app.eval.report import render_json, render_text
from src.app.eval.models import EvalReport, Severity, Status

import json


class TestEndToEndGoodTools:
    def test_protocol_layer(self):
        result = check_protocol_all(GOOD_TOOLS)
        assert result.layer == "protocol"
        assert result.total_fail == 0

    def test_quality_layer(self):
        result = check_quality_all(GOOD_TOOLS)
        assert result.layer == "quality"
        assert len(result.tools) == 4

    def test_security_layer(self):
        result = check_security_all(GOOD_TOOLS)
        assert result.layer == "security"
        critical_fails = [
            c for tr in result.tools for c in tr.checks
            if c.status == Status.FAIL and c.severity == Severity.CRITICAL
        ]
        assert len(critical_fails) == 0

    def test_no_overlaps_in_good_tools(self):
        overlaps = detect_overlaps(GOOD_TOOLS)
        assert len(overlaps) == 0

    def test_full_report(self):
        layers = {
            "protocol": check_protocol_all(GOOD_TOOLS),
            "quality": check_quality_all(GOOD_TOOLS),
            "security": check_security_all(GOOD_TOOLS),
        }
        report = EvalReport(
            timestamp="2026-09-10",
            server_name="mock-good",
            layers=layers,
        )
        report = apply_scoring(report)
        assert report.overall_score > 50
        assert report.gate_passed is True

    def test_json_report_parseable(self):
        layers = {"protocol": check_protocol_all(GOOD_TOOLS)}
        report = EvalReport(
            timestamp="2026-09-10",
            server_name="mock",
            layers=layers,
        )
        report = apply_scoring(report)
        output = render_json(report, redact=False)
        data = json.loads(output)
        assert "overall_score" in data

    def test_text_report_readable(self):
        layers = {"protocol": check_protocol_all(GOOD_TOOLS)}
        report = EvalReport(
            timestamp="2026-09-10",
            server_name="mock",
            layers=layers,
        )
        report = apply_scoring(report)
        text = render_text(report)
        assert "mock" in text


class TestEndToEndBadTools:
    def test_protocol_finds_violations(self):
        result = check_protocol_all(BAD_TOOLS)
        assert result.total_fail > 0

    def test_security_finds_issues(self):
        result = check_security_all(BAD_TOOLS)
        critical = [
            c for tr in result.tools for c in tr.checks
            if c.status == Status.FAIL and c.severity == Severity.CRITICAL
        ]
        assert len(critical) > 0

    def test_overlap_detected(self):
        all_tools = get_mock_tools(include_bad=True)
        overlaps = detect_overlaps(all_tools, threshold=0.5)
        overlap_names = []
        for o in overlaps:
            overlap_names.append(o.details.get("tool_a", ""))
            overlap_names.append(o.details.get("tool_b", ""))
        assert "search_customers" in overlap_names or "find_customers" in overlap_names

    def test_bad_tools_lower_score(self):
        good_layers = {"protocol": check_protocol_all(GOOD_TOOLS)}
        good_report = EvalReport(timestamp="", server_name="good", layers=good_layers)
        good_report = apply_scoring(good_report)

        bad_layers = {"protocol": check_protocol_all(BAD_TOOLS)}
        bad_report = EvalReport(timestamp="", server_name="bad", layers=bad_layers)
        bad_report = apply_scoring(bad_report)

        assert good_report.overall_score > bad_report.overall_score


class TestEndToEndWithLlm:
    def test_full_pipeline_with_llm_layer(self):
        from src.app.eval.model_adapter import MockAdapter
        from src.app.eval.llm_eval import check_llm_all

        adapter = MockAdapter()
        layers = {
            "protocol": check_protocol_all(GOOD_TOOLS),
            "quality": check_quality_all(GOOD_TOOLS),
            "security": check_security_all(GOOD_TOOLS),
        }

        llm_layer = asyncio.get_event_loop().run_until_complete(
            check_llm_all(GOOD_TOOLS, adapter)
        )
        layers["llm"] = llm_layer

        report = EvalReport(
            timestamp="2026-09-10",
            server_name="mock-llm",
            layers=layers,
            metadata={"llm_provider": "mock", "llm_model": "default"},
        )
        report = apply_scoring(report)
        assert 0 <= report.overall_score <= 100
        assert "llm" in report.layers
        assert report.metadata["llm_provider"] == "mock"

        json_out = render_json(report, redact=False)
        data = json.loads(json_out)
        assert "llm" in data["layers"]
        assert data["metadata"]["llm_provider"] == "mock"

    def test_report_without_llm_has_no_llm_layer(self):
        layers = {
            "protocol": check_protocol_all(GOOD_TOOLS),
        }
        report = EvalReport(timestamp="", server_name="no-llm", layers=layers)
        report = apply_scoring(report)
        assert "llm" not in report.layers


class TestEndToEndMixed:
    def test_all_checkers_no_crash(self):
        all_tools = get_mock_tools(include_bad=True)
        check_protocol_all(all_tools)
        check_quality_all(all_tools)
        check_security_all(all_tools)
        detect_overlaps(all_tools)

    def test_full_pipeline_with_scoring(self):
        all_tools = get_mock_tools(include_bad=True)
        layers = {
            "protocol": check_protocol_all(all_tools),
            "quality": check_quality_all(all_tools),
            "security": check_security_all(all_tools),
        }
        overlaps = detect_overlaps(all_tools, threshold=0.5)
        layers["quality"].catalog_checks.extend(overlaps)

        report = EvalReport(
            timestamp="2026-09-10",
            server_name="mixed",
            layers=layers,
        )
        report = apply_scoring(report)
        assert 0 <= report.overall_score <= 100
        text = render_text(report)
        assert "mixed" in text
        json_out = render_json(report, redact=False)
        data = json.loads(json_out)
        assert len(data["layers"]) == 3
