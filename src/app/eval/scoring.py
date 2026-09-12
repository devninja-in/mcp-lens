from __future__ import annotations

import logging

from .models import EvalReport, LayerResult, ScoringConfig, Severity, Status

logger = logging.getLogger(__name__)


def compute_layer_score(layer: LayerResult) -> float:
    all_checks = []
    for tr in layer.tools:
        all_checks.extend(tr.checks)
    all_checks.extend(layer.catalog_checks)

    if not all_checks:
        return 100.0

    total_weight = 0.0
    earned = 0.0
    for c in all_checks:
        w = _severity_weight(c.severity)
        total_weight += w
        if c.status in (Status.PASS, Status.SKIP):
            earned += w

    return round((earned / total_weight) * 100, 1) if total_weight > 0 else 100.0


def _severity_weight(severity: Severity) -> float:
    return {
        Severity.CRITICAL: 5.0,
        Severity.HIGH: 3.0,
        Severity.MEDIUM: 2.0,
        Severity.LOW: 1.0,
        Severity.INFO: 0.5,
    }.get(severity, 1.0)


def compute_overall_score(
    layers: dict[str, LayerResult],
    config: ScoringConfig,
) -> tuple[float, bool]:
    weights = config.layer_weights
    total_weight = 0.0
    weighted_sum = 0.0

    for layer_name, layer_result in layers.items():
        w = weights.get(layer_name, 0.0)
        layer_score = compute_layer_score(layer_result)
        layer_result.score = layer_score
        weighted_sum += layer_score * w
        total_weight += w

    overall = round(weighted_sum / total_weight, 1) if total_weight > 0 else 0.0

    gate_passed = overall >= config.gate_threshold
    for fail_layer in config.fail_on_layers:
        if fail_layer in layers:
            lr = layers[fail_layer]
            has_critical_fail = any(
                c.status == Status.FAIL and c.severity == Severity.CRITICAL
                for tr in lr.tools for c in tr.checks
            )
            if has_critical_fail:
                gate_passed = False

    return overall, gate_passed


def apply_scoring(report: EvalReport, config: ScoringConfig | None = None) -> EvalReport:
    if config is None:
        config = ScoringConfig()
    score, gate = compute_overall_score(report.layers, config)
    report.overall_score = score
    report.gate_passed = gate
    logger.info(
        "Scoring complete for '%s': overall=%.1f gate=%s (layers: %s)",
        report.server_name, score, gate,
        ", ".join(f"{k}={v.score:.1f}" for k, v in report.layers.items()),
    )
    return report
