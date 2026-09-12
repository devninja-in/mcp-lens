from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC
from pathlib import Path

import yaml

from .llm_config import get_eval_adapter, load_llm_config
from .models import EvalReport, ScoringConfig
from .overlap import detect_overlaps
from .protocol import check_protocol_all
from .quality import check_quality_all
from .regression import compare_reports, load_report_from_json
from .report import render_json, render_text, save_report
from .scoring import apply_scoring
from .security import check_security_all


def _load_tools(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    data = yaml.safe_load(p.read_text())
    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict):
        tools: list[dict] = data.get("tools", [])
        return tools
    return []


def _build_report(tools: list[dict], server_name: str = "", run_llm: bool = False) -> EvalReport:
    from datetime import datetime

    layers = {}
    layers["protocol"] = check_protocol_all(tools)
    layers["quality"] = check_quality_all(tools)
    layers["security"] = check_security_all(tools)

    overlaps = detect_overlaps(tools)
    if overlaps:
        layers["quality"].catalog_checks.extend(overlaps)

    llm_meta: dict = {}
    if run_llm:
        llm_config = load_llm_config()
        if llm_config:
            try:
                adapter = get_eval_adapter()
                if adapter:
                    from .llm_eval import check_llm_all

                    llm_layer = asyncio.get_event_loop().run_until_complete(check_llm_all(tools, adapter))
                    layers["llm"] = llm_layer
                    llm_meta = {
                        "llm_provider": llm_config["provider"],
                        "llm_model": llm_config.get("model") or "default",
                    }
            except Exception as e:
                print(f"LLM evaluation failed: {e}", file=sys.stderr)
                llm_meta = {
                    "llm_provider": llm_config["provider"],
                    "llm_model": llm_config.get("model") or "default",
                    "llm_error": str(e),
                }
        else:
            print("Warning: --llm flag set but EVAL_LLM_PROVIDER not configured in environment", file=sys.stderr)

    report = EvalReport(
        timestamp=datetime.now(UTC).isoformat(),
        server_name=server_name,
        layers=layers,
        metadata=llm_meta,
    )
    return apply_scoring(report)


def cmd_validate(args: argparse.Namespace) -> int:
    tools = _load_tools(args.target)
    report = _build_report(tools, server_name=Path(args.target).stem, run_llm=args.llm)
    print(render_text(report))
    return 0 if report.gate_passed else 1


def cmd_security(args: argparse.Namespace) -> int:
    tools = _load_tools(args.target)
    layer = check_security_all(tools)

    from .scoring import compute_layer_score

    layer.score = compute_layer_score(layer)

    report = EvalReport(
        timestamp="",
        server_name=Path(args.target).stem,
        layers={"security": layer},
        overall_score=layer.score,
        gate_passed=layer.score >= 70,
    )
    print(render_text(report))
    has_fail = any(c.status.value == "fail" for tr in layer.tools for c in tr.checks)
    return 1 if has_fail else 0


def cmd_report(args: argparse.Namespace) -> int:
    tools = _load_tools(args.target)

    config = ScoringConfig()
    if args.config:
        import json

        config_data = json.loads(Path(args.config).read_text())
        if "layer_weights" in config_data:
            config.layer_weights = config_data["layer_weights"]
        if "gate_threshold" in config_data:
            config.gate_threshold = config_data["gate_threshold"]

    report = _build_report(tools, server_name=Path(args.target).stem, run_llm=args.llm)
    report = apply_scoring(report, config)

    if args.output:
        save_report(report, args.output, fmt=args.format)
        print(f"Report saved to {args.output}")
    else:
        if args.format == "json":
            print(render_json(report))
        else:
            print(render_text(report))

    return 0 if report.gate_passed else 1


def cmd_compare(args: argparse.Namespace) -> int:
    baseline = load_report_from_json(Path(args.baseline))
    current = load_report_from_json(Path(args.current))
    diff = compare_reports(baseline, current)

    print(f"Score delta: {diff.score_delta:+.1f}")
    print(f"Regressed: {diff.regressed}")
    if diff.new_failures:
        print(f"\nNew failures ({len(diff.new_failures)}):")
        for f in diff.new_failures:
            print(f"  - [{f['layer']}] {f['tool']}: {f['message']}")
    if diff.fixed:
        print(f"\nFixed ({len(diff.fixed)}):")
        for f in diff.fixed:
            print(f"  - [{f['layer']}] {f['tool']}: {f['message']}")

    return 1 if diff.regressed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcp-eval",
        description="MCP Tool Evaluation Framework",
    )
    sub = parser.add_subparsers(dest="command")

    p_validate = sub.add_parser("validate", help="Protocol + quality validation")
    p_validate.add_argument("target", help="Path to tools YAML file")
    p_validate.add_argument(
        "--llm",
        action="store_true",
        help="Run LLM-assisted evaluation (requires EVAL_LLM_PROVIDER in env)",
    )

    p_security = sub.add_parser("security", help="Security analysis")
    p_security.add_argument("target", help="Path to tools YAML file")

    p_report = sub.add_parser("report", help="Full evaluation report")
    p_report.add_argument("target", help="Path to tools YAML file")
    p_report.add_argument("--format", choices=["json", "text"], default="text")
    p_report.add_argument("--output", help="Output file path")
    p_report.add_argument("--config", help="Scoring config JSON file")
    p_report.add_argument(
        "--llm",
        action="store_true",
        help="Run LLM-assisted evaluation (requires EVAL_LLM_PROVIDER in env)",
    )

    p_compare = sub.add_parser("compare", help="Compare baseline vs current reports")
    p_compare.add_argument("baseline", help="Baseline report JSON")
    p_compare.add_argument("current", help="Current report JSON")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 2

    handlers = {
        "validate": cmd_validate,
        "security": cmd_security,
        "report": cmd_report,
        "compare": cmd_compare,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
