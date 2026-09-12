from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .models import CheckResult, Severity, Status


def resolve_path(data: Any, path: str) -> Any:
    if not path:
        return data
    current = data
    for segment in _split_path(path):
        if isinstance(segment, int):
            if not isinstance(current, (list, tuple)) or segment >= len(current):
                raise KeyError(f"Index {segment} out of range at path '{path}'")
            current = current[segment]
        elif isinstance(current, dict):
            if segment not in current:
                raise KeyError(f"Key '{segment}' not found at path '{path}'")
            current = current[segment]
        else:
            raise KeyError(f"Cannot traverse '{segment}' on {type(current).__name__}")
    return current


def _split_path(path: str) -> list[str | int]:
    segments: list[str | int] = []
    for part in re.split(r"\.", path):
        if not part:
            continue
        m = re.match(r"^([^\[]+)(.*)$", part)
        if m:
            segments.append(m.group(1))
            rest = m.group(2)
            for idx_match in re.finditer(r"\[(\d+)\]", rest):
                segments.append(int(idx_match.group(1)))
        else:
            segments.append(part)
    return segments


def evaluate_assertion(assertion: Any, data: Any) -> CheckResult:
    handler = ASSERTION_HANDLERS.get(assertion.type)
    if handler is None:
        return CheckResult(
            check_id=f"assertion.{assertion.type}",
            status=Status.FAIL,
            message=f"Unknown assertion type: '{assertion.type}'",
            severity=Severity.HIGH,
        )
    try:
        value = resolve_path(data, assertion.path) if assertion.path else data
    except KeyError as e:
        if assertion.type in ("not_exists", "is_null"):
            return handler(None, assertion.expected, assertion.path)
        return CheckResult(
            check_id=f"assertion.{assertion.type}",
            status=Status.FAIL,
            message=f"Path resolution failed: {e}",
            severity=Severity.HIGH,
            details={"path": assertion.path},
        )
    return handler(value, assertion.expected, assertion.path)


def _make_check(name: str, passed: bool, path: str, msg_pass: str, msg_fail: str) -> CheckResult:
    return CheckResult(
        check_id=f"assertion.{name}",
        status=Status.PASS if passed else Status.FAIL,
        message=msg_pass if passed else msg_fail,
        severity=Severity.INFO if passed else Severity.HIGH,
        details={"path": path},
    )


def _assert_equals(value: Any, expected: Any, path: str) -> CheckResult:
    return _make_check(
        "equals",
        value == expected,
        path,
        f"Value equals {expected!r}",
        f"Expected {expected!r}, got {value!r}",
    )


def _assert_not_equals(value: Any, expected: Any, path: str) -> CheckResult:
    return _make_check(
        "not_equals",
        value != expected,
        path,
        f"Value does not equal {expected!r}",
        f"Expected value to differ from {expected!r}",
    )


def _assert_contains(value: Any, expected: Any, path: str) -> CheckResult:
    if isinstance(value, str):
        passed = str(expected) in value
    elif isinstance(value, (list, tuple)):
        passed = expected in value
    else:
        passed = False
    return _make_check(
        "contains",
        passed,
        path,
        f"Contains {expected!r}",
        f"Does not contain {expected!r}",
    )


def _assert_not_contains(value: Any, expected: Any, path: str) -> CheckResult:
    if isinstance(value, str):
        passed = str(expected) not in value
    elif isinstance(value, (list, tuple)):
        passed = expected not in value
    else:
        passed = True
    return _make_check(
        "not_contains",
        passed,
        path,
        f"Does not contain {expected!r}",
        f"Contains {expected!r}",
    )


def _assert_starts_with(value: Any, expected: Any, path: str) -> CheckResult:
    passed = isinstance(value, str) and value.startswith(str(expected))
    return _make_check(
        "starts_with",
        passed,
        path,
        f"Starts with {expected!r}",
        f"Does not start with {expected!r}",
    )


def _assert_ends_with(value: Any, expected: Any, path: str) -> CheckResult:
    passed = isinstance(value, str) and value.endswith(str(expected))
    return _make_check(
        "ends_with",
        passed,
        path,
        f"Ends with {expected!r}",
        f"Does not end with {expected!r}",
    )


def _assert_regex(value: Any, expected: Any, path: str) -> CheckResult:
    passed = isinstance(value, str) and bool(re.search(str(expected), value))
    return _make_check(
        "regex",
        passed,
        path,
        f"Matches pattern {expected!r}",
        f"Does not match pattern {expected!r}",
    )


def _assert_exists(value: Any, expected: Any, path: str) -> CheckResult:
    return _make_check(
        "exists",
        value is not None,
        path,
        f"Path '{path}' exists",
        f"Path '{path}' does not exist",
    )


def _assert_not_exists(value: Any, expected: Any, path: str) -> CheckResult:
    return _make_check(
        "not_exists",
        value is None,
        path,
        f"Path '{path}' does not exist",
        f"Path '{path}' exists",
    )


def _assert_is_null(value: Any, expected: Any, path: str) -> CheckResult:
    return _make_check(
        "is_null",
        value is None,
        path,
        "Value is null",
        f"Expected null, got {type(value).__name__}",
    )


def _assert_is_not_null(value: Any, expected: Any, path: str) -> CheckResult:
    return _make_check(
        "is_not_null",
        value is not None,
        path,
        "Value is not null",
        "Value is null",
    )


def _assert_is_array(value: Any, expected: Any, path: str) -> CheckResult:
    return _make_check(
        "is_array",
        isinstance(value, list),
        path,
        "Value is an array",
        f"Expected array, got {type(value).__name__}",
    )


def _assert_is_object(value: Any, expected: Any, path: str) -> CheckResult:
    return _make_check(
        "is_object",
        isinstance(value, dict),
        path,
        "Value is an object",
        f"Expected object, got {type(value).__name__}",
    )


def _assert_is_string(value: Any, expected: Any, path: str) -> CheckResult:
    return _make_check(
        "is_string",
        isinstance(value, str),
        path,
        "Value is a string",
        f"Expected string, got {type(value).__name__}",
    )


def _assert_is_number(value: Any, expected: Any, path: str) -> CheckResult:
    return _make_check(
        "is_number",
        isinstance(value, (int, float)) and not isinstance(value, bool),
        path,
        "Value is a number",
        f"Expected number, got {type(value).__name__}",
    )


def _assert_length(value: Any, expected: Any, path: str) -> CheckResult:
    try:
        actual = len(value)
    except TypeError:
        return _make_check("length", False, path, "", "Value has no length")
    return _make_check(
        "length",
        actual == int(expected),
        path,
        f"Length is {expected}",
        f"Expected length {expected}, got {actual}",
    )


def _assert_length_gte(value: Any, expected: Any, path: str) -> CheckResult:
    try:
        actual = len(value)
    except TypeError:
        return _make_check("length_gte", False, path, "", "Value has no length")
    return _make_check(
        "length_gte",
        actual >= int(expected),
        path,
        f"Length {actual} >= {expected}",
        f"Length {actual} < {expected}",
    )


def _assert_length_lte(value: Any, expected: Any, path: str) -> CheckResult:
    try:
        actual = len(value)
    except TypeError:
        return _make_check("length_lte", False, path, "", "Value has no length")
    return _make_check(
        "length_lte",
        actual <= int(expected),
        path,
        f"Length {actual} <= {expected}",
        f"Length {actual} > {expected}",
    )


def _assert_gt(value: Any, expected: Any, path: str) -> CheckResult:
    passed = isinstance(value, (int, float)) and value > float(expected)
    return _make_check(
        "gt",
        passed,
        path,
        f"{value} > {expected}",
        f"{value} is not > {expected}",
    )


def _assert_gte(value: Any, expected: Any, path: str) -> CheckResult:
    passed = isinstance(value, (int, float)) and value >= float(expected)
    return _make_check(
        "gte",
        passed,
        path,
        f"{value} >= {expected}",
        f"{value} is not >= {expected}",
    )


def _assert_lt(value: Any, expected: Any, path: str) -> CheckResult:
    passed = isinstance(value, (int, float)) and value < float(expected)
    return _make_check(
        "lt",
        passed,
        path,
        f"{value} < {expected}",
        f"{value} is not < {expected}",
    )


def _assert_lte(value: Any, expected: Any, path: str) -> CheckResult:
    passed = isinstance(value, (int, float)) and value <= float(expected)
    return _make_check(
        "lte",
        passed,
        path,
        f"{value} <= {expected}",
        f"{value} is not <= {expected}",
    )


def _assert_not_empty(value: Any, expected: Any, path: str) -> CheckResult:
    try:
        passed = len(value) > 0
    except TypeError:
        passed = value is not None
    return _make_check(
        "not_empty",
        passed,
        path,
        "Value is not empty",
        "Value is empty",
    )


def _assert_subset(value: Any, expected: Any, path: str) -> CheckResult:
    if not isinstance(expected, list) or not isinstance(value, list):
        return _make_check("subset", False, path, "", "Both values must be arrays for subset check")
    passed = all(item in value for item in expected)
    return _make_check(
        "subset",
        passed,
        path,
        "Expected items are a subset",
        f"Missing items: {[x for x in expected if x not in value]}",
    )


ASSERTION_HANDLERS: dict[str, Callable[[Any, Any, str], CheckResult]] = {
    "equals": _assert_equals,
    "not_equals": _assert_not_equals,
    "contains": _assert_contains,
    "not_contains": _assert_not_contains,
    "starts_with": _assert_starts_with,
    "ends_with": _assert_ends_with,
    "regex": _assert_regex,
    "exists": _assert_exists,
    "not_exists": _assert_not_exists,
    "is_null": _assert_is_null,
    "is_not_null": _assert_is_not_null,
    "is_array": _assert_is_array,
    "is_object": _assert_is_object,
    "is_string": _assert_is_string,
    "is_number": _assert_is_number,
    "length": _assert_length,
    "length_gte": _assert_length_gte,
    "length_lte": _assert_length_lte,
    "gt": _assert_gt,
    "gte": _assert_gte,
    "lt": _assert_lt,
    "lte": _assert_lte,
    "not_empty": _assert_not_empty,
    "subset": _assert_subset,
}
