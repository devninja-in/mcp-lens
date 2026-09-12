from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .agent_eval import evaluate_arg_generation, evaluate_tool_selection
from .models import BenchmarkScenario, BenchmarkSuite, LayerResult, ToolResult


def load_benchmark(path: Path) -> BenchmarkSuite:
    raw = yaml.safe_load(path.read_text())
    meta = raw.get("benchmark", {})
    scenarios = []
    for t in raw.get("tasks", []):
        scenarios.append(
            BenchmarkScenario(
                id=t["id"],
                prompt=t["prompt"],
                expected_tools=t.get("expected_tools", []),
                expected_args=t.get("expected_args", {}),
                expected_answer_contains=t.get("expected_answer_contains", []),
                tags=t.get("tags", []),
            )
        )
    return BenchmarkSuite(
        name=meta.get("name", ""),
        server_name=meta.get("server_name", ""),
        version=meta.get("version", ""),
        scenarios=scenarios,
    )


async def run_benchmark(
    suite: BenchmarkSuite,
    tools: list[dict],
    adapter: Any,
) -> LayerResult:
    selection_results: list[ToolResult] = []
    arg_results: list[ToolResult] = []

    for scenario in suite.scenarios:
        sel = await evaluate_tool_selection(scenario, tools, adapter)
        selection_results.append(sel)

        arg = await evaluate_arg_generation(scenario, tools, adapter)
        arg_results.append(arg)

    all_results = selection_results + arg_results
    return LayerResult(layer="benchmark", tools=all_results)
