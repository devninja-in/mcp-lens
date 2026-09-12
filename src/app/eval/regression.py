from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .models import EvalReport, Status

logger = logging.getLogger(__name__)


@dataclass
class RegressionDiff:
    score_delta: float = 0.0
    per_layer_deltas: dict[str, float] = field(default_factory=dict)
    new_failures: list[dict] = field(default_factory=list)
    fixed: list[dict] = field(default_factory=list)
    regressed: bool = False

    def to_dict(self) -> dict:
        return {
            "score_delta": round(self.score_delta, 1),
            "per_layer_deltas": {k: round(v, 1) for k, v in self.per_layer_deltas.items()},
            "new_failures": self.new_failures,
            "fixed": self.fixed,
            "regressed": self.regressed,
        }


def compare_reports(
    baseline: EvalReport,
    current: EvalReport,
    max_regression_drop: float = 5.0,
) -> RegressionDiff:
    logger.info("Comparing reports: baseline=%.1f current=%.1f", baseline.overall_score, current.overall_score)
    diff = RegressionDiff()
    diff.score_delta = current.overall_score - baseline.overall_score
    diff.regressed = diff.score_delta < -max_regression_drop

    all_layers = set(baseline.layers.keys()) | set(current.layers.keys())
    for layer in all_layers:
        base_score = baseline.layers[layer].score if layer in baseline.layers else 0.0
        curr_score = current.layers[layer].score if layer in current.layers else 0.0
        diff.per_layer_deltas[layer] = curr_score - base_score

    baseline_fails = _collect_failures(baseline)
    current_fails = _collect_failures(current)

    baseline_keys = {_fail_key(f) for f in baseline_fails}
    current_keys = {_fail_key(f) for f in current_fails}

    for f in current_fails:
        if _fail_key(f) not in baseline_keys:
            diff.new_failures.append(f)

    for f in baseline_fails:
        if _fail_key(f) not in current_keys:
            diff.fixed.append(f)

    if diff.regressed:
        logger.warning("Regression detected: score dropped by %.1f", abs(diff.score_delta))
    if diff.new_failures:
        logger.warning("New failures: %d", len(diff.new_failures))
    if diff.fixed:
        logger.info("Fixed issues: %d", len(diff.fixed))
    return diff


def _collect_failures(report: EvalReport) -> list[dict]:
    failures = []
    for layer_name, layer_result in report.layers.items():
        for tr in layer_result.tools:
            for c in tr.checks:
                if c.status == Status.FAIL:
                    failures.append(
                        {
                            "layer": layer_name,
                            "tool": tr.tool_name,
                            "check_id": c.check_id,
                            "message": c.message,
                        }
                    )
    return failures


def _fail_key(f: dict) -> str:
    return f"{f['layer']}:{f['tool']}:{f['check_id']}"


def load_report_from_json(path: Path) -> EvalReport:
    data = json.loads(path.read_text())
    report = EvalReport(
        timestamp=data.get("timestamp", ""),
        server_name=data.get("server_name", ""),
        overall_score=data.get("overall_score", 0.0),
        gate_passed=data.get("gate_passed", False),
        metadata=data.get("metadata", {}),
    )
    return report
