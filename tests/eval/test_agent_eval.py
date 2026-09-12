import asyncio
from dataclasses import dataclass

from src.app.eval.agent_eval import (
    _is_subsequence,
    _values_match,
    evaluate_arg_generation,
    evaluate_tool_selection,
    evaluate_trajectory,
    score_arg_accuracy,
)
from src.app.eval.model_adapter import MockAdapter
from src.app.eval.models import Severity, Status


@dataclass
class FakeScenario:
    id: str = "test_scenario"
    prompt: str = "Find Alice"
    expected_tools: list = None
    expected_args: dict = None

    def __post_init__(self):
        if self.expected_tools is None:
            self.expected_tools = []
        if self.expected_args is None:
            self.expected_args = {}


class TestToolSelection:
    def test_correct_selection(self):
        scenario = FakeScenario(expected_tools=["search"])
        tools = [{"name": "search"}, {"name": "delete"}]
        adapter = MockAdapter(responses={"Find Alice": {"tool_name": "search", "arguments": {}}})
        result = asyncio.get_event_loop().run_until_complete(
            evaluate_tool_selection(scenario, tools, adapter)
        )
        assert result.score == 100.0
        assert any(c.status == Status.PASS for c in result.checks)

    def test_wrong_selection(self):
        scenario = FakeScenario(expected_tools=["search"])
        tools = [{"name": "search"}, {"name": "delete"}]
        adapter = MockAdapter(responses={"Find Alice": {"tool_name": "delete", "arguments": {}}})
        result = asyncio.get_event_loop().run_until_complete(
            evaluate_tool_selection(scenario, tools, adapter)
        )
        assert result.score == 0.0
        assert any(c.status == Status.FAIL for c in result.checks)

    def test_destructive_false_positive(self):
        scenario = FakeScenario(expected_tools=["search"])
        tools = [
            {"name": "search"},
            {"name": "delete_all", "annotations": {"destructiveHint": True}},
        ]
        adapter = MockAdapter(responses={"Find Alice": {"tool_name": "delete_all", "arguments": {}}})
        result = asyncio.get_event_loop().run_until_complete(
            evaluate_tool_selection(scenario, tools, adapter)
        )
        critical = [c for c in result.checks if c.severity == Severity.CRITICAL]
        assert len(critical) == 1
        assert critical[0].check_id == "agent.destructive_false_positive"


class TestArgGeneration:
    def test_correct_args(self):
        scenario = FakeScenario(
            expected_tools=["search"],
            expected_args={"search": {"name": "Alice"}},
        )
        tools = [{"name": "search"}]
        adapter = MockAdapter(responses={"Find Alice": {"tool_name": "search", "arguments": {"name": "Alice"}}})
        result = asyncio.get_event_loop().run_until_complete(
            evaluate_arg_generation(scenario, tools, adapter)
        )
        assert result.score == 100.0

    def test_missing_arg(self):
        scenario = FakeScenario(
            expected_tools=["search"],
            expected_args={"search": {"name": "Alice"}},
        )
        tools = [{"name": "search"}]
        adapter = MockAdapter(responses={"Find Alice": {"tool_name": "search", "arguments": {}}})
        result = asyncio.get_event_loop().run_until_complete(
            evaluate_arg_generation(scenario, tools, adapter)
        )
        assert result.score == 0.0
        assert any(c.status == Status.FAIL for c in result.checks)

    def test_unexpected_arg_warns(self):
        scenario = FakeScenario(
            expected_tools=["search"],
            expected_args={"search": {"name": "Alice"}},
        )
        tools = [{"name": "search"}]
        adapter = MockAdapter(responses={
            "Find Alice": {"tool_name": "search", "arguments": {"name": "Alice", "extra": "val"}},
        })
        result = asyncio.get_event_loop().run_until_complete(
            evaluate_arg_generation(scenario, tools, adapter)
        )
        warns = [c for c in result.checks if c.status == Status.WARN]
        assert len(warns) == 1

    def test_skip_when_no_expected_args(self):
        scenario = FakeScenario(expected_tools=["search"])
        tools = [{"name": "search"}]
        adapter = MockAdapter(responses={"Find Alice": {"tool_name": "search", "arguments": {}}})
        result = asyncio.get_event_loop().run_until_complete(
            evaluate_arg_generation(scenario, tools, adapter)
        )
        assert any(c.status == Status.SKIP for c in result.checks)


class TestScoreArgAccuracy:
    def test_all_match(self):
        assert score_arg_accuracy({"a": 1, "b": 2}, {"a": 1, "b": 2}) == 100.0

    def test_none_match(self):
        assert score_arg_accuracy({"a": 1}, {"a": 99}) == 0.0

    def test_partial_match(self):
        assert score_arg_accuracy({"a": 1, "b": 2}, {"a": 1, "b": 99}) == 50.0

    def test_empty_expected(self):
        assert score_arg_accuracy({}, {"a": 1}) == 100.0


class TestValuesMatch:
    def test_exact(self):
        assert _values_match(42, 42) is True

    def test_string_case_insensitive(self):
        assert _values_match("Hello", "hello") is True

    def test_numeric_tolerance(self):
        assert _values_match(100, 100.5) is True

    def test_different_types(self):
        assert _values_match("42", 42) is False


class TestTrajectory:
    def test_correct_sequence(self):
        steps = [{"tool": "search"}, {"tool": "get"}]
        expected = [{"tool": "search"}, {"tool": "get"}]
        result = asyncio.get_event_loop().run_until_complete(
            evaluate_trajectory(steps, expected)
        )
        assert any(c.status == Status.PASS and "sequence" in c.check_id for c in result.checks)

    def test_wrong_first_tool(self):
        steps = [{"tool": "get"}, {"tool": "search"}]
        expected = [{"tool": "search"}, {"tool": "get"}]
        result = asyncio.get_event_loop().run_until_complete(
            evaluate_trajectory(steps, expected)
        )
        first = next(c for c in result.checks if "first_tool" in c.check_id)
        assert first.status == Status.FAIL

    def test_unnecessary_calls(self):
        steps = [{"tool": "search"}, {"tool": "extra"}, {"tool": "get"}]
        expected = [{"tool": "search"}, {"tool": "get"}]
        result = asyncio.get_event_loop().run_until_complete(
            evaluate_trajectory(steps, expected)
        )
        warns = [c for c in result.checks if "unnecessary" in c.check_id]
        assert len(warns) == 1

    def test_repeated_calls(self):
        steps = [{"tool": "search"}, {"tool": "search"}, {"tool": "get"}]
        expected = [{"tool": "search"}, {"tool": "get"}]
        result = asyncio.get_event_loop().run_until_complete(
            evaluate_trajectory(steps, expected)
        )
        repeated = [c for c in result.checks if "repeated" in c.check_id]
        assert len(repeated) == 1

    def test_empty_trajectory(self):
        result = asyncio.get_event_loop().run_until_complete(
            evaluate_trajectory([], [])
        )
        assert any(c.check_id == "agent.trajectory.sequence" for c in result.checks)


class TestIsSubsequence:
    def test_is_subsequence(self):
        assert _is_subsequence(["a", "c"], ["a", "b", "c"]) is True

    def test_is_not_subsequence(self):
        assert _is_subsequence(["c", "a"], ["a", "b", "c"]) is False

    def test_empty(self):
        assert _is_subsequence([], ["a", "b"]) is True
