from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class CheckResult:
    check_id: str
    status: Status
    message: str
    severity: Severity = Severity.INFO
    tool_name: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["severity"] = self.severity.value
        return d


@dataclass
class ToolResult:
    tool_name: str
    checks: list[CheckResult] = field(default_factory=list)
    score: float = 0.0

    @property
    def passed(self) -> bool:
        return not any(
            c.status == Status.FAIL and c.severity in (Severity.CRITICAL, Severity.HIGH)
            for c in self.checks
        )

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.status == Status.PASS)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.status == Status.FAIL)

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.status == Status.WARN)

    @property
    def skip_count(self) -> int:
        return sum(1 for c in self.checks if c.status == Status.SKIP)

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "score": self.score,
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "summary": {
                "pass": self.pass_count,
                "fail": self.fail_count,
                "warn": self.warn_count,
                "skip": self.skip_count,
            },
        }


@dataclass
class LayerResult:
    layer: str
    tools: list[ToolResult] = field(default_factory=list)
    catalog_checks: list[CheckResult] = field(default_factory=list)
    score: float = 0.0

    @property
    def total_checks(self) -> int:
        return sum(len(t.checks) for t in self.tools) + len(self.catalog_checks)

    @property
    def total_pass(self) -> int:
        tool_pass = sum(t.pass_count for t in self.tools)
        cat_pass = sum(1 for c in self.catalog_checks if c.status == Status.PASS)
        return tool_pass + cat_pass

    @property
    def total_fail(self) -> int:
        tool_fail = sum(t.fail_count for t in self.tools)
        cat_fail = sum(1 for c in self.catalog_checks if c.status == Status.FAIL)
        return tool_fail + cat_fail

    def to_dict(self) -> dict:
        return {
            "layer": self.layer,
            "score": self.score,
            "tool_count": len(self.tools),
            "tools": [t.to_dict() for t in self.tools],
            "catalog_checks": [c.to_dict() for c in self.catalog_checks],
            "summary": {
                "total_checks": self.total_checks,
                "pass": self.total_pass,
                "fail": self.total_fail,
            },
        }


@dataclass
class EvalReport:
    timestamp: str = ""
    server_name: str = ""
    layers: dict[str, LayerResult] = field(default_factory=dict)
    overall_score: float = 0.0
    gate_passed: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "server_name": self.server_name,
            "overall_score": self.overall_score,
            "gate_passed": self.gate_passed,
            "layers": {k: v.to_dict() for k, v in self.layers.items()},
            "metadata": self.metadata,
        }


# --- Functional test models ---


@dataclass
class Assertion:
    type: str
    path: str = ""
    expected: Any = None


@dataclass
class TestCase:
    id: str
    tool_name: str
    description: str = ""
    input: dict = field(default_factory=dict)
    assertions: list[Assertion] = field(default_factory=list)
    expect_error: bool = False
    tags: list[str] = field(default_factory=list)


@dataclass
class TestSuite:
    server_name: str
    test_cases: list[TestCase] = field(default_factory=list)


# --- Benchmark / agent eval models ---


@dataclass
class BenchmarkScenario:
    id: str
    prompt: str
    expected_tools: list[str] = field(default_factory=list)
    expected_args: dict[str, dict] = field(default_factory=dict)
    expected_answer_contains: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class BenchmarkSuite:
    name: str
    server_name: str = ""
    version: str = "1.0"
    scenarios: list[BenchmarkScenario] = field(default_factory=list)


# --- Timing ---


@dataclass
class TimingStats:
    tool_name: str
    call_count: int = 0
    success_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return (self.success_count / self.call_count * 100) if self.call_count else 0.0

    def percentile(self, p: int) -> float:
        if not self.latencies_ms:
            return 0.0
        s = sorted(self.latencies_ms)
        idx = int(len(s) * p / 100)
        return s[min(idx, len(s) - 1)]

    @property
    def p50(self) -> float:
        return self.percentile(50)

    @property
    def p95(self) -> float:
        return self.percentile(95)

    @property
    def p99(self) -> float:
        return self.percentile(99)

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "call_count": self.call_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "timeout_count": self.timeout_count,
            "success_rate": round(self.success_rate, 1),
            "p50_ms": round(self.p50, 1),
            "p95_ms": round(self.p95, 1),
            "p99_ms": round(self.p99, 1),
        }


# --- Scoring config ---

DEFAULT_LAYER_WEIGHTS = {
    "protocol": 0.15,
    "quality": 0.10,
    "functional": 0.25,
    "security": 0.10,
    "selection": 0.15,
    "arguments": 0.15,
    "trajectory": 0.10,
    "llm": 0.10,
}


@dataclass
class ScoringConfig:
    layer_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_LAYER_WEIGHTS))
    gate_threshold: float = 70.0
    fail_on_layers: list[str] = field(default_factory=lambda: ["protocol", "security"])
    max_regression_drop: dict[str, float] = field(default_factory=dict)
