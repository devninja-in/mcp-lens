from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import EvalReport, Status
from .redaction import redact_secrets


def render_json(report: EvalReport, redact: bool = True) -> str:
    data = report.to_dict()
    if redact:
        data = redact_secrets(data)
    return json.dumps(data, indent=2, default=str)


def render_text(report: EvalReport) -> str:
    lines = []
    lines.append(f"MCP Tool Evaluation Report — {report.server_name}")
    lines.append(f"Timestamp: {report.timestamp}")
    lines.append(f"Overall Score: {report.overall_score:.1f}/100")
    lines.append(f"Gate: {'PASSED' if report.gate_passed else 'FAILED'}")
    lines.append("")

    for layer_name, layer_result in report.layers.items():
        lines.append(f"--- {layer_name.upper()} (score: {layer_result.score:.1f}) ---")
        if layer_result.catalog_checks:
            for c in layer_result.catalog_checks:
                lines.append(f"  [{c.status.value.upper()}] {c.message}")

        for tr in layer_result.tools:
            status_char = "+" if tr.passed else "x"
            lines.append(f"  [{status_char}] {tr.tool_name} (score: {tr.score:.1f})")
            for c in tr.checks:
                if c.status != Status.PASS:
                    lines.append(f"      [{c.status.value.upper()}] {c.message}")
        lines.append("")

    return "\n".join(lines)


def save_report(
    report: EvalReport,
    path: str | Path,
    fmt: str = "json",
    redact: bool = True,
) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        p.write_text(render_json(report, redact=redact))
    else:
        p.write_text(render_text(report))
