from __future__ import annotations

from typing import Any

from .models import CheckResult, LayerResult, Severity, Status, ToolResult


async def evaluate_tool_selection(
    scenario: Any,
    tools: list[dict],
    adapter: Any,
) -> ToolResult:
    selection = await adapter.select_tool(tools, scenario.prompt)
    selected_name = selection.get("tool_name", "")
    expected = scenario.expected_tools

    checks = []
    if selected_name in expected:
        checks.append(CheckResult(
            check_id="agent.tool_selection",
            status=Status.PASS,
            message=f"Correctly selected '{selected_name}'",
            severity=Severity.INFO,
            details={"selected": selected_name, "expected": expected},
        ))
    else:
        checks.append(CheckResult(
            check_id="agent.tool_selection",
            status=Status.FAIL,
            message=f"Selected '{selected_name}', expected one of {expected}",
            severity=Severity.HIGH,
            details={"selected": selected_name, "expected": expected},
        ))

    is_destructive = any(
        t.get("name") == selected_name and (
            t.get("annotations", {}).get("destructiveHint", False)
            or any(v in (t.get("name", "") or "").lower() for v in ("delete", "remove", "destroy"))
        )
        for t in tools
    )
    if is_destructive and selected_name not in expected:
        checks.append(CheckResult(
            check_id="agent.destructive_false_positive",
            status=Status.FAIL,
            message=f"Incorrectly selected destructive tool '{selected_name}'",
            severity=Severity.CRITICAL,
            details={"selected": selected_name},
        ))

    return ToolResult(
        tool_name=scenario.id,
        checks=checks,
        score=100.0 if selected_name in expected else 0.0,
    )


async def evaluate_arg_generation(
    scenario: Any,
    tools: list[dict],
    adapter: Any,
) -> ToolResult:
    selection = await adapter.select_tool(tools, scenario.prompt)
    selected_name = selection.get("tool_name", "")
    actual_args = selection.get("arguments", {})

    expected_args = scenario.expected_args.get(selected_name, {})
    if not expected_args:
        return ToolResult(
            tool_name=scenario.id,
            checks=[CheckResult(
                check_id="agent.arg_generation",
                status=Status.SKIP,
                message="No expected arguments defined for this scenario",
            )],
        )

    accuracy = score_arg_accuracy(expected_args, actual_args)
    checks = []

    for key, expected_val in expected_args.items():
        actual_val = actual_args.get(key)
        if actual_val is None:
            checks.append(CheckResult(
                check_id=f"agent.arg.{key}",
                status=Status.FAIL,
                message=f"Missing argument '{key}' (expected {expected_val!r})",
                severity=Severity.HIGH,
                details={"key": key, "expected": expected_val},
            ))
        elif _values_match(expected_val, actual_val):
            checks.append(CheckResult(
                check_id=f"agent.arg.{key}",
                status=Status.PASS,
                message=f"Argument '{key}' matches expected value",
                details={"key": key, "expected": expected_val, "actual": actual_val},
            ))
        else:
            checks.append(CheckResult(
                check_id=f"agent.arg.{key}",
                status=Status.FAIL,
                message=f"Argument '{key}': expected {expected_val!r}, got {actual_val!r}",
                severity=Severity.MEDIUM,
                details={"key": key, "expected": expected_val, "actual": actual_val},
            ))

    unexpected = set(actual_args.keys()) - set(expected_args.keys())
    for key in unexpected:
        checks.append(CheckResult(
            check_id=f"agent.arg.unexpected.{key}",
            status=Status.WARN,
            message=f"Unexpected argument '{key}' with value {actual_args[key]!r}",
            severity=Severity.LOW,
            details={"key": key, "value": actual_args[key]},
        ))

    return ToolResult(tool_name=scenario.id, checks=checks, score=accuracy)


def score_arg_accuracy(expected: dict, actual: dict) -> float:
    if not expected:
        return 100.0
    matches = 0
    total = len(expected)
    for key, exp_val in expected.items():
        act_val = actual.get(key)
        if _values_match(exp_val, act_val):
            matches += 1
    return round((matches / total) * 100, 1)


def _values_match(expected: Any, actual: Any) -> bool:
    if expected == actual:
        return True
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().lower() == actual.strip().lower()
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if expected == 0:
            return actual == 0
        return abs(expected - actual) / max(abs(expected), 1) < 0.01
    return False


async def evaluate_trajectory(
    steps: list[dict],
    expected_steps: list[dict],
) -> ToolResult:
    checks = []

    if steps and expected_steps:
        first_actual = steps[0].get("tool", "")
        first_expected = expected_steps[0].get("tool", "")
        checks.append(CheckResult(
            check_id="agent.trajectory.first_tool",
            status=Status.PASS if first_actual == first_expected else Status.FAIL,
            message=f"First tool: expected '{first_expected}', got '{first_actual}'",
            severity=Severity.HIGH if first_actual != first_expected else Severity.INFO,
        ))

    expected_tools = [s.get("tool") for s in expected_steps]
    actual_tools = [s.get("tool") for s in steps]

    correct_sequence = _is_subsequence(expected_tools, actual_tools)
    checks.append(CheckResult(
        check_id="agent.trajectory.sequence",
        status=Status.PASS if correct_sequence else Status.FAIL,
        message="Expected tools appear in correct order" if correct_sequence
        else f"Expected sequence {expected_tools}, got {actual_tools}",
        severity=Severity.HIGH if not correct_sequence else Severity.INFO,
    ))

    unnecessary = [t for t in actual_tools if t not in expected_tools]
    if unnecessary:
        checks.append(CheckResult(
            check_id="agent.trajectory.unnecessary_calls",
            status=Status.WARN,
            message=f"Unnecessary tool calls: {unnecessary}",
            severity=Severity.MEDIUM,
            details={"unnecessary": unnecessary},
        ))

    repeated = []
    for i, t in enumerate(actual_tools):
        if i > 0 and t == actual_tools[i - 1]:
            repeated.append(t)
    if repeated:
        checks.append(CheckResult(
            check_id="agent.trajectory.repeated_calls",
            status=Status.WARN,
            message=f"Repeated consecutive calls: {repeated}",
            severity=Severity.LOW,
            details={"repeated": repeated},
        ))

    if not checks:
        checks.append(CheckResult(
            check_id="agent.trajectory.empty",
            status=Status.SKIP,
            message="No trajectory to evaluate",
        ))

    score = sum(1 for c in checks if c.status == Status.PASS) / max(len(checks), 1) * 100
    return ToolResult(tool_name="trajectory", checks=checks, score=round(score, 1))


def _is_subsequence(expected: list, actual: list) -> bool:
    it = iter(actual)
    return all(item in it for item in expected)
