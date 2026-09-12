"""Tests for ground truth YAML upload, storage, and integration with LLM eval."""

import asyncio

import yaml

from src.app.eval.llm_eval import (
    _check_arg_generation,
    _check_tool_selection,
    _get_ground_truth_for_tool,
)
from src.app.eval.model_adapter import MockAdapter
from src.app.eval.models import Status

SAMPLE_TOOLS = [
    {
        "name": "search_users",
        "description": "Search for users by name or email address",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_user_profile",
        "description": "Get the profile details of a specific user",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
            },
            "required": ["user_id"],
        },
    },
]


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class TestGetGroundTruthForTool:
    def test_returns_matching_test_case(self):
        gt = [
            {"expected_tool_selection": ["search_users"], "prompts": ["Find users named Alice"]},
            {"expected_tool_selection": ["get_user_profile"], "prompts": ["Show me user 123's profile"]},
        ]
        result = _get_ground_truth_for_tool("search_users", gt)
        assert len(result) == 1
        assert result[0]["prompts"] == ["Find users named Alice"]

    def test_returns_empty_for_unknown_tool(self):
        gt = [{"expected_tool_selection": ["search_users"], "prompts": ["Find users"]}]
        result = _get_ground_truth_for_tool("delete_user", gt)
        assert result == []

    def test_returns_empty_when_ground_truth_is_none(self):
        result = _get_ground_truth_for_tool("search_users", None)
        assert result == []

    def test_returns_empty_when_ground_truth_is_empty(self):
        result = _get_ground_truth_for_tool("search_users", [])
        assert result == []

    def test_returns_multiple_matching_cases(self):
        gt = [
            {"expected_tool_selection": ["search_users"], "prompts": ["First prompt"]},
            {"expected_tool_selection": ["search_users"], "prompts": ["Second prompt"]},
        ]
        result = _get_ground_truth_for_tool("search_users", gt)
        assert len(result) == 2

    def test_matches_multi_tool_selection(self):
        gt = [
            {"expected_tool_selection": ["search_users", "get_user_profile"], "prompts": ["Find and show user"]},
        ]
        result_search = _get_ground_truth_for_tool("search_users", gt)
        result_profile = _get_ground_truth_for_tool("get_user_profile", gt)
        assert len(result_search) == 1
        assert len(result_profile) == 1
        assert result_search[0] is result_profile[0]


class TestToolSelectionWithGroundTruth:
    def test_uses_ground_truth_prompt(self):
        gt = [{"expected_tool_selection": ["search_users"], "prompts": ["Find users named Alice"]}]

        class CapturingAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {"tool_name": "search_users", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                return "scenario"

        adapter = CapturingAdapter()
        results = _run(_check_tool_selection(SAMPLE_TOOLS[:1], adapter, ground_truth=gt))
        assert len(results) == 1
        check = results[0].checks[0]
        assert check.status == Status.PASS
        assert check.details["scenario_source"] == "user_provided"
        select_calls = [c for c in adapter.calls if c["method"] == "select_tool"]
        assert "Alice" in select_calls[0]["prompt"]

    def test_auto_generated_when_no_ground_truth_match(self):
        gt = [{"expected_tool_selection": ["other_tool"], "prompts": ["Some other prompt"]}]
        adapter = MockAdapter()
        results = _run(_check_tool_selection(SAMPLE_TOOLS[:1], adapter, ground_truth=gt))
        assert len(results) == 1
        check = results[0].checks[0]
        assert check.details["scenario_source"] == "auto_generated"

    def test_auto_generated_when_ground_truth_is_none(self):
        adapter = MockAdapter()
        results = _run(_check_tool_selection(SAMPLE_TOOLS[:1], adapter, ground_truth=None))
        assert len(results) == 1
        check = results[0].checks[0]
        assert check.details["scenario_source"] == "auto_generated"

    def test_multi_tool_selection_passes_for_any_expected(self):
        gt = [{"expected_tool_selection": ["search_users", "get_user_profile"], "prompts": ["Find and show user"]}]

        class ProfileAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {"tool_name": "get_user_profile", "arguments": {}}

        adapter = ProfileAdapter()
        results = _run(_check_tool_selection(SAMPLE_TOOLS[:1], adapter, ground_truth=gt))
        check = results[0].checks[0]
        assert check.status == Status.PASS
        assert check.details["selected"] == "get_user_profile"

    def test_all_prompts_tested(self):
        gt = [
            {
                "expected_tool_selection": ["search_users"],
                "prompts": ["Find users named Alice", "Look up users with email @example.com"],
            }
        ]
        adapter = MockAdapter()
        results = _run(_check_tool_selection(SAMPLE_TOOLS[:1], adapter, ground_truth=gt))
        assert len(results) == 1
        assert len(results[0].checks) == 2
        for check in results[0].checks:
            assert check.status == Status.PASS
            assert check.details["scenario_source"] == "user_provided"

    def test_scenario_source_on_fail(self):
        gt = [{"expected_tool_selection": ["search_users"], "prompts": ["Find users named Alice"]}]

        class WrongAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {"tool_name": "unknown_tool", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                if "reasonable prerequisite" in prompt:
                    return '{"prerequisite": false, "reason": "Not a prerequisite"}'
                return "Find users named Alice"

        adapter = WrongAdapter()
        results = _run(_check_tool_selection(SAMPLE_TOOLS, adapter, ground_truth=gt))
        check = results[0].checks[0]
        assert check.details["scenario_source"] == "user_provided"


class TestArgGenerationWithGroundTruth:
    def test_expected_args_match_passes(self):
        gt = [
            {
                "expected_tool_selection": ["search_users"],
                "prompts": ["Find users named Alice"],
                "expected_args": {"query": "Alice"},
            }
        ]

        class MatchingAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {"tool_name": "search_users", "arguments": {"query": "Alice"}}

            async def generate_answer(self, tool_result, prompt):
                return "Find users named Alice"

        adapter = MatchingAdapter()
        results = _run(_check_arg_generation(SAMPLE_TOOLS[:1], adapter, ground_truth=gt))
        checks = results[0].checks
        gt_checks = [c for c in checks if "ground_truth" in c.check_id]
        assert len(gt_checks) == 0
        pass_checks = [c for c in checks if c.status == Status.PASS]
        assert len(pass_checks) >= 1

    def test_expected_args_mismatch_warns(self):
        gt = [
            {
                "expected_tool_selection": ["search_users"],
                "prompts": ["Find users named Alice"],
                "expected_args": {"query": "Alice"},
            }
        ]

        class MismatchAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {"tool_name": "search_users", "arguments": {"query": "Bob"}}

            async def generate_answer(self, tool_result, prompt):
                return "Find users named Alice"

        adapter = MismatchAdapter()
        results = _run(_check_arg_generation(SAMPLE_TOOLS[:1], adapter, ground_truth=gt))
        checks = results[0].checks
        gt_checks = [c for c in checks if "ground_truth" in c.check_id]
        assert len(gt_checks) == 1
        assert gt_checks[0].status == Status.WARN
        assert "Alice" in gt_checks[0].message
        assert "Bob" in gt_checks[0].message

    def test_no_expected_args_skips_gt_validation(self):
        gt = [{"expected_tool_selection": ["search_users"], "prompts": ["Find users named Alice"]}]

        class SimpleAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {"tool_name": "search_users", "arguments": {"query": "Alice"}}

            async def generate_answer(self, tool_result, prompt):
                return "Find users"

        adapter = SimpleAdapter()
        results = _run(_check_arg_generation(SAMPLE_TOOLS[:1], adapter, ground_truth=gt))
        checks = results[0].checks
        gt_checks = [c for c in checks if "ground_truth" in c.check_id]
        assert len(gt_checks) == 0


class TestGroundTruthYamlValidation:
    def test_valid_yaml_structure(self):
        yaml_text = """
test_cases:
  - expected_tool_selection:
      - "search_users"
    prompts:
      - "Find users named Alice"
      - "Look up users by email"

  - expected_tool_selection:
      - "search_users"
      - "get_user_profile"
    prompts:
      - "Search for user and show their profile"
    expected_args:
      query: "alice"
"""
        data = yaml.safe_load(yaml_text)
        assert "test_cases" in data
        assert len(data["test_cases"]) == 2
        tc0 = data["test_cases"][0]
        assert tc0["expected_tool_selection"] == ["search_users"]
        assert len(tc0["prompts"]) == 2
        tc1 = data["test_cases"][1]
        assert tc1["expected_tool_selection"] == ["search_users", "get_user_profile"]
        assert tc1.get("expected_args") == {"query": "alice"}

    def test_minimal_test_case(self):
        yaml_text = """
test_cases:
  - expected_tool_selection:
      - "my_tool"
    prompts:
      - "Do something"
"""
        data = yaml.safe_load(yaml_text)
        tc = data["test_cases"][0]
        assert "expected_tool_selection" in tc
        assert "prompts" in tc
        assert tc.get("expected_args") is None

    def test_empty_test_cases_list(self):
        yaml_text = "test_cases: []"
        data = yaml.safe_load(yaml_text)
        assert data["test_cases"] == []
