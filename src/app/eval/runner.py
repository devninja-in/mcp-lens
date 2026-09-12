from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from .assertions import evaluate_assertion
from .models import CheckResult, LayerResult, Severity, Status, TestCase, TestSuite, ToolResult

logger = logging.getLogger(__name__)

CallFn = Callable[[str, dict], Awaitable[tuple[dict, float]]]


async def run_test_suite(suite: TestSuite, call_fn: CallFn) -> LayerResult:
    logger.info("Running test suite: %d test cases", len(suite.test_cases))
    results: list[ToolResult] = []
    for tc in suite.test_cases:
        tr = await run_single_test(tc, call_fn)
        results.append(tr)
    passed = sum(1 for r in results for c in r.checks if c.status == Status.PASS)
    failed = sum(1 for r in results for c in r.checks if c.status == Status.FAIL)
    logger.info("Test suite complete: %d passed, %d failed", passed, failed)
    return LayerResult(layer="functional", tools=results)


async def run_single_test(test_case: TestCase, call_fn: CallFn) -> ToolResult:
    logger.debug("Running test '%s' on tool '%s'", test_case.id, test_case.tool_name)
    checks: list[CheckResult] = []
    try:
        result, latency = await call_fn(test_case.tool_name, test_case.input)
    except Exception as exc:
        if test_case.expect_error:
            checks.append(
                CheckResult(
                    check_id=f"test.{test_case.id}.expected_error",
                    status=Status.PASS,
                    message=f"Call correctly rejected: {exc}",
                    severity=Severity.INFO,
                    tool_name=test_case.tool_name,
                )
            )
        else:
            checks.append(
                CheckResult(
                    check_id=f"test.{test_case.id}.unexpected_error",
                    status=Status.FAIL,
                    message=f"Unexpected error: {exc}",
                    severity=Severity.HIGH,
                    tool_name=test_case.tool_name,
                )
            )
        return ToolResult(tool_name=test_case.tool_name, checks=checks)

    if test_case.expect_error:
        checks.append(
            CheckResult(
                check_id=f"test.{test_case.id}.expected_error_missing",
                status=Status.FAIL,
                message="Expected error but call succeeded",
                severity=Severity.HIGH,
                tool_name=test_case.tool_name,
            )
        )
        return ToolResult(tool_name=test_case.tool_name, checks=checks)

    for assertion in test_case.assertions:
        check = evaluate_assertion(assertion, result)
        check.check_id = f"test.{test_case.id}.{check.check_id}"
        check.tool_name = test_case.tool_name
        checks.append(check)

    return ToolResult(tool_name=test_case.tool_name, checks=checks)
