import asyncio

import pytest

from src.app.eval.llm_eval import (
    check_llm_all,
    _check_description_clarity,
    _check_tool_selection,
    _check_arg_generation,
    _check_tool_disambiguation,
    _check_safety_resistance,
    _check_type,
    _suggest_improved_description,
)
from src.app.eval.model_adapter import MockAdapter
from src.app.eval.models import Status, Severity


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
        "name": "delete_user",
        "description": "Permanently delete a user account and all associated data",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "User ID to delete"},
            },
            "required": ["user_id"],
        },
        "annotations": {"destructiveHint": True, "readOnlyHint": False},
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
        "annotations": {"readOnlyHint": True},
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


class TestCheckType:
    def test_string(self):
        assert _check_type("hello", "string") is True
        assert _check_type(123, "string") is False

    def test_number(self):
        assert _check_type(3.14, "number") is True
        assert _check_type(42, "number") is True
        assert _check_type("42", "number") is False

    def test_integer(self):
        assert _check_type(42, "integer") is True
        assert _check_type(3.14, "integer") is False

    def test_boolean(self):
        assert _check_type(True, "boolean") is True
        assert _check_type("true", "boolean") is False

    def test_array(self):
        assert _check_type([1, 2], "array") is True
        assert _check_type({}, "array") is False

    def test_object(self):
        assert _check_type({"a": 1}, "object") is True
        assert _check_type([], "object") is False

    def test_unknown_type(self):
        assert _check_type("anything", "custom") is True


class ClarityMockAdapter(MockAdapter):
    """Returns canned JSON rating responses for generate_answer."""

    def __init__(self, rating: int = 9, reason: str = "Clear description"):
        super().__init__()
        self._rating = rating
        self._reason = reason

    async def generate_answer(self, tool_result, user_prompt):
        self.calls.append({"method": "generate_answer", "prompt": user_prompt})
        return f'{{"rating": {self._rating}, "reason": "{self._reason}"}}'


class TestDescriptionClarity:
    def test_high_rating_passes(self):
        adapter = ClarityMockAdapter(rating=9, reason="Very clear")
        results = _run(_check_description_clarity(SAMPLE_TOOLS[:1], adapter))
        assert len(results) == 1
        assert results[0].checks[0].status == Status.PASS
        assert "9/10" in results[0].checks[0].message

    def test_medium_rating_warns(self):
        adapter = ClarityMockAdapter(rating=6, reason="Adequate")
        results = _run(_check_description_clarity(SAMPLE_TOOLS[:1], adapter))
        assert results[0].checks[0].status == Status.WARN
        assert results[0].checks[0].severity == Severity.MEDIUM

    def test_low_rating_fails(self):
        adapter = ClarityMockAdapter(rating=3, reason="Unclear")
        results = _run(_check_description_clarity(SAMPLE_TOOLS[:1], adapter))
        assert results[0].checks[0].status == Status.FAIL
        assert results[0].checks[0].severity == Severity.HIGH

    def test_no_description_skips(self):
        adapter = ClarityMockAdapter()
        tool = {"name": "empty_tool"}
        results = _run(_check_description_clarity([tool], adapter))
        assert results[0].checks[0].status == Status.SKIP

    def test_details_include_location_and_suggestion(self):
        adapter = ClarityMockAdapter(rating=4, reason="Vague")
        results = _run(_check_description_clarity(SAMPLE_TOOLS[:1], adapter))
        details = results[0].checks[0].details
        assert details["location"] == "description"
        assert details["suggestion"] is not None

    def test_llm_error_skips(self):
        class ErrorAdapter(MockAdapter):
            async def generate_answer(self, tool_result, user_prompt):
                raise RuntimeError("API error")
        results = _run(_check_description_clarity(SAMPLE_TOOLS[:1], ErrorAdapter()))
        assert results[0].checks[0].status == Status.SKIP
        assert "skipped" in results[0].checks[0].message.lower()


class TestToolSelection:
    def test_correct_selection_passes(self):
        adapter = MockAdapter()
        results = _run(_check_tool_selection(SAMPLE_TOOLS[:1], adapter))
        assert len(results) == 1
        assert results[0].checks[0].status == Status.PASS

    def test_wrong_selection_fails(self):
        adapter = MockAdapter(responses={})
        tools = [
            {"name": "tool_a", "description": "Does A"},
            {"name": "tool_b", "description": "Does B"},
        ]

        class WrongAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {"tool_name": "tool_b", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                return "Use tool_a to do A"

        adapter = WrongAdapter()
        results = _run(_check_tool_selection(tools[:1], adapter))
        assert results[0].checks[0].status == Status.FAIL
        assert results[0].checks[0].severity == Severity.HIGH

    def test_prerequisite_selection_warns(self):
        tools = [
            {"name": "updateConfluencePage", "description": "Update a Confluence page with new content"},
            {"name": "getAccessibleAtlassianResources", "description": "Get list of accessible Atlassian cloud resources"},
        ]

        class PrereqAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {"tool_name": "getAccessibleAtlassianResources", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                if "prerequisite" in prompt:
                    return '{"prerequisite": true, "reason": "Need to discover available Confluence instances first"}'
                return "Update the Confluence page titled Project Status"

        adapter = PrereqAdapter()
        results = _run(_check_tool_selection(tools[:1], adapter))
        check = results[0].checks[0]
        assert check.status == Status.WARN
        assert check.severity == Severity.MEDIUM
        assert check.details.get("prerequisite") is True
        assert "prerequisite" in check.message.lower()

    def test_no_description_skips(self):
        adapter = MockAdapter()
        tool = {"name": "bare_tool"}
        results = _run(_check_tool_selection([tool], adapter))
        assert results[0].checks[0].status == Status.SKIP


class TestArgGeneration:
    def test_valid_args_passes(self):
        adapter = MockAdapter(responses={})

        class GoodArgAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {
                    "tool_name": "search_users",
                    "arguments": {"query": "alice", "limit": 10},
                }

            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                return "Search for users named alice"

        adapter = GoodArgAdapter()
        results = _run(_check_arg_generation(SAMPLE_TOOLS[:1], adapter))
        assert len(results) == 1
        checks = results[0].checks
        pass_checks = [c for c in checks if c.status == Status.PASS]
        assert len(pass_checks) >= 1

    def test_missing_required_arg_fails(self):
        class MissingArgAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {"tool_name": "search_users", "arguments": {"limit": 5}}

            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                return "Search users"

        adapter = MissingArgAdapter()
        results = _run(_check_arg_generation(SAMPLE_TOOLS[:1], adapter))
        checks = results[0].checks
        fail_checks = [c for c in checks if c.status == Status.FAIL]
        assert len(fail_checks) >= 1
        assert any("query" in c.message for c in fail_checks)

    def test_hallucinated_arg_warns(self):
        class HallucinatingAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {
                    "tool_name": "search_users",
                    "arguments": {"query": "test", "sort_by": "name"},
                }

            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                return "Search for test users"

        adapter = HallucinatingAdapter()
        results = _run(_check_arg_generation(SAMPLE_TOOLS[:1], adapter))
        checks = results[0].checks
        warn_checks = [c for c in checks if c.status == Status.WARN]
        assert len(warn_checks) >= 1
        assert any("sort_by" in c.message for c in warn_checks)

    def test_no_schema_skipped(self):
        adapter = MockAdapter()
        tool = {"name": "no_schema_tool", "description": "A tool"}
        results = _run(_check_arg_generation([tool], adapter))
        assert len(results) == 0

    def test_wrong_tool_selected_skips_arg_check(self):
        class WrongToolAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {"tool_name": "other_tool", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                return "scenario"

        adapter = WrongToolAdapter()
        results = _run(_check_arg_generation(SAMPLE_TOOLS[:1], adapter))
        checks = results[0].checks
        assert checks[0].status == Status.SKIP


class TestToolDisambiguation:
    def test_no_overlaps_returns_empty(self):
        adapter = MockAdapter()
        tools = [
            {"name": "create_user", "description": "Create a new user account"},
            {"name": "delete_file", "description": "Delete a file from storage"},
        ]
        results = _run(_check_tool_disambiguation(tools, adapter))
        assert len(results) == 0

    def test_overlap_correct_choice_passes(self):
        adapter = MockAdapter()
        tools = [
            {"name": "search_customers", "description": "Search for customers by name or email"},
            {"name": "find_customers", "description": "Find customers by name or email address"},
        ]

        class CorrectAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {"tool_name": "search_customers", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                return f"I need to search_customers"

        adapter = CorrectAdapter()
        results = _run(_check_tool_disambiguation(tools, adapter))
        if results:
            pass_checks = [c for tr in results for c in tr.checks if c.status == Status.PASS]
            fail_checks = [c for tr in results for c in tr.checks if c.status == Status.FAIL]
            assert len(pass_checks) + len(fail_checks) > 0


class TestSafetyResistance:
    def test_avoids_destructive_tool_passes(self):
        class SafeAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {"tool_name": "get_user_profile", "arguments": {"user_id": "123"}}

        adapter = SafeAdapter()
        results = _run(_check_safety_resistance(SAMPLE_TOOLS, adapter))
        assert len(results) >= 1
        for tr in results:
            for c in tr.checks:
                assert c.status == Status.PASS

    def test_selects_destructive_tool_fails(self):
        class UnsafeAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {"tool_name": "delete_user", "arguments": {"user_id": "123"}}

        adapter = UnsafeAdapter()
        results = _run(_check_safety_resistance(SAMPLE_TOOLS, adapter))
        fail_checks = [c for tr in results for c in tr.checks if c.status == Status.FAIL]
        assert len(fail_checks) >= 1
        assert any(c.severity == Severity.CRITICAL for c in fail_checks)

    def test_no_dangerous_tools_returns_empty(self):
        adapter = MockAdapter()
        safe_tools = [
            {"name": "list_items", "description": "List items", "annotations": {"readOnlyHint": True}},
        ]
        results = _run(_check_safety_resistance(safe_tools, adapter))
        assert len(results) == 0

    def test_no_read_tools_returns_empty(self):
        adapter = MockAdapter()
        write_only = [
            {
                "name": "delete_all",
                "description": "Delete everything",
                "annotations": {"destructiveHint": True, "readOnlyHint": False},
            },
        ]
        results = _run(_check_safety_resistance(write_only, adapter))
        assert len(results) == 0


class TestServerDescription:
    def test_description_clarity_includes_server_context(self):
        class CapturingAdapter(ClarityMockAdapter):
            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                assert "Atlassian" in prompt
                return '{"rating": 9, "reason": "Clear"}'

        adapter = CapturingAdapter(rating=9, reason="Clear")
        results = _run(_check_description_clarity(
            SAMPLE_TOOLS[:1], adapter, server_description="Atlassian MCP server for Confluence and Jira"
        ))
        assert len(results) == 1
        assert results[0].checks[0].status == Status.PASS

    def test_tool_selection_enriches_scenario_with_server_context(self):
        class ContextCapturingAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                assert "[Context:" in prompt
                assert "data platform" in prompt
                return {"tool_name": tools[0]["name"], "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                return "Search for users named alice"

        adapter = ContextCapturingAdapter()
        results = _run(_check_tool_selection(
            SAMPLE_TOOLS[:1], adapter, server_description="data platform for analytics"
        ))
        assert len(results) == 1
        assert results[0].checks[0].status == Status.PASS

    def test_check_llm_all_accepts_server_description(self):
        adapter = ClarityMockAdapter(rating=8, reason="Good")
        layer = _run(check_llm_all(SAMPLE_TOOLS, adapter, server_description="Test server"))
        assert layer.layer == "llm"
        assert len(layer.tools) > 0

    def test_check_llm_all_works_without_server_description(self):
        adapter = ClarityMockAdapter(rating=8, reason="Good")
        layer = _run(check_llm_all(SAMPLE_TOOLS, adapter))
        assert layer.layer == "llm"
        assert len(layer.tools) > 0


class TestCheckLlmAll:
    def test_produces_llm_layer(self):
        adapter = ClarityMockAdapter(rating=8, reason="Good")
        layer = _run(check_llm_all(SAMPLE_TOOLS, adapter))
        assert layer.layer == "llm"
        assert len(layer.tools) > 0

    def test_merges_checks_per_tool(self):
        adapter = ClarityMockAdapter(rating=8, reason="Good")
        layer = _run(check_llm_all(SAMPLE_TOOLS, adapter))
        for tr in layer.tools:
            check_ids = [c.check_id for c in tr.checks]
            assert len(check_ids) >= 1

    def test_individual_check_failure_doesnt_crash_layer(self):
        class PartialErrorAdapter(MockAdapter):
            async def generate_answer(self, tool_result, prompt):
                raise RuntimeError("LLM down")

            async def select_tool(self, tools, prompt):
                return {"tool_name": tools[0]["name"], "arguments": {}}

        adapter = PartialErrorAdapter()
        layer = _run(check_llm_all(SAMPLE_TOOLS, adapter))
        assert layer.layer == "llm"

    def test_empty_tools_returns_empty_layer(self):
        adapter = MockAdapter()
        layer = _run(check_llm_all([], adapter))
        assert layer.layer == "llm"
        assert len(layer.tools) == 0

    def test_ground_truth_passed_through(self):
        adapter = ClarityMockAdapter(rating=8, reason="Good")
        gt = [{"expected_tool_selection": ["search_users"], "prompts": ["Find users named Alice"]}]
        layer = _run(check_llm_all(SAMPLE_TOOLS, adapter, ground_truth=gt))
        assert layer.layer == "llm"
        assert len(layer.tools) > 0


class TestSuggestImprovedDescription:
    def test_returns_suggestion_text(self):
        class SuggestionAdapter(MockAdapter):
            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                return "Search for users by name, email, or ID in the user database"

        tool = {"name": "search_users", "description": "Search for users"}
        adapter = SuggestionAdapter()
        result = _run(_suggest_improved_description(
            adapter, tool, "Find users named Alice", "other_tool", "search_users",
        ))
        assert result is not None
        assert "user" in result.lower()

    def test_returns_none_on_adapter_error(self):
        class ErrorAdapter(MockAdapter):
            async def generate_answer(self, tool_result, prompt):
                raise RuntimeError("API error")

        tool = {"name": "search_users", "description": "Search for users"}
        adapter = ErrorAdapter()
        result = _run(_suggest_improved_description(
            adapter, tool, "Find users", "other_tool", "search_users",
        ))
        assert result is None

    def test_includes_server_description_context(self):
        class ContextAdapter(MockAdapter):
            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                assert "analytics platform" in prompt
                return "Improved description"

        tool = {"name": "search_users", "description": "Search for users"}
        adapter = ContextAdapter()
        result = _run(_suggest_improved_description(
            adapter, tool, "Find users", "other_tool", "search_users",
            server_description="analytics platform",
        ))
        assert result == "Improved description"


class TestDescriptionSuggestionInChecks:
    def test_suggestion_on_tool_selection_fail(self):
        tools = [
            {"name": "tool_a", "description": "Does A things"},
            {"name": "tool_b", "description": "Does B things"},
        ]

        class WrongWithSuggestion(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {"tool_name": "tool_b", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                if "reasonable prerequisite" in prompt:
                    return '{"prerequisite": false, "reason": "Not a prerequisite"}'
                if "Suggest an improved description" in prompt:
                    return "Better description for tool_a"
                return "Use tool_a to do A"

        adapter = WrongWithSuggestion()
        results = _run(_check_tool_selection(tools[:1], adapter))
        check = results[0].checks[0]
        assert check.status == Status.FAIL
        assert check.details.get("suggested_description") == "Better description for tool_a"

    def test_no_suggestion_on_pass(self):
        adapter = MockAdapter()
        results = _run(_check_tool_selection(SAMPLE_TOOLS[:1], adapter))
        check = results[0].checks[0]
        assert check.status == Status.PASS
        assert "suggested_description" not in (check.details or {})

    def test_no_suggestion_on_prerequisite_warn(self):
        tools = [
            {"name": "updatePage", "description": "Update a page"},
            {"name": "listResources", "description": "List available resources"},
        ]

        class PrereqAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {"tool_name": "listResources", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                if "reasonable prerequisite" in prompt:
                    return '{"prerequisite": true, "reason": "Need to discover resources first"}'
                return "Update the page"

        adapter = PrereqAdapter()
        results = _run(_check_tool_selection(tools[:1], adapter))
        check = results[0].checks[0]
        assert check.status == Status.WARN
        assert "suggested_description" not in (check.details or {})


class TestCoverageGaps:
    def test_gt_prerequisite_warn_in_multi_prompt_loop(self):
        """Test ground truth multi-prompt loop with prerequisite WARN."""
        tools = [
            {"name": "updateConfluencePage", "description": "Update a Confluence page"},
            {"name": "getAccessibleResources", "description": "Get accessible Atlassian resources"},
        ]

        class PrereqAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                self.calls.append({"method": "select_tool", "prompt": prompt})
                return {"tool_name": "getAccessibleResources", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                self.calls.append({"method": "generate_answer", "prompt": prompt})
                if "reasonable prerequisite" in prompt:
                    return '{"prerequisite": true, "reason": "Need to discover available resources first"}'
                return "Update the Confluence page"

        adapter = PrereqAdapter()
        gt = [{"expected_tool_selection": ["updateConfluencePage"], "prompts": ["Update the project status page"]}]
        results = _run(_check_tool_selection(tools, adapter, ground_truth=gt))
        checks = [c for tr in results for c in tr.checks if c.tool_name == "updateConfluencePage"]
        assert any(c.status == Status.WARN and c.details.get("prerequisite") for c in checks)

    def test_tool_selection_exception_handler_auto_generated(self):
        """Test tool selection exception handler in auto-generated path."""
        class ErrorAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                raise RuntimeError("API error")

            async def generate_answer(self, tool_result, prompt):
                return "scenario text"

        adapter = ErrorAdapter()
        results = _run(_check_tool_selection(SAMPLE_TOOLS[:1], adapter))
        assert results[0].checks[0].status == Status.SKIP
        assert "adapter error" in results[0].checks[0].message

    def test_arg_generation_empty_properties(self):
        """Test arg generation skips tools with empty properties."""
        adapter = MockAdapter()
        tool = {
            "name": "no_props_tool",
            "description": "A tool",
            "inputSchema": {"type": "object", "properties": {}},
        }
        results = _run(_check_arg_generation([tool], adapter))
        assert len(results) == 0

    def test_arg_generation_no_description(self):
        """Test arg generation skips tools with no description."""
        adapter = MockAdapter()
        tool = {
            "name": "no_desc_tool",
            "inputSchema": {"type": "object", "properties": {"arg": {"type": "string"}}},
        }
        results = _run(_check_arg_generation([tool], adapter))
        assert len(results) == 0

    def test_arg_generation_exception_handler(self):
        """Test arg generation exception handler."""
        class ErrorAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                raise RuntimeError("API error")

            async def generate_answer(self, tool_result, prompt):
                return "scenario"

        adapter = ErrorAdapter()
        results = _run(_check_arg_generation(SAMPLE_TOOLS[:1], adapter))
        assert results[0].checks[0].status == Status.SKIP

    def test_disambiguation_seen_pairs_dedup(self):
        """Test disambiguation deduplicates seen pairs."""
        tools = [
            {
                "name": "searchCustomers",
                "description": "Search for customers by name or email address",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}},
            },
            {
                "name": "findCustomers",
                "description": "Find customers by name or email address",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}},
            },
        ]

        class CorrectAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {"tool_name": "searchCustomers", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                return "Search for customers"

        adapter = CorrectAdapter()
        results = _run(_check_tool_disambiguation(tools, adapter))
        assert len(results) == 1

    def test_disambiguation_tool_not_found(self):
        """Test disambiguation when tool_a or tool_b not in tools list."""
        tools = [
            {"name": "existing_tool", "description": "An existing tool"},
        ]

        class MockOverlapAdapter(MockAdapter):
            pass

        adapter = MockOverlapAdapter()
        results = _run(_check_tool_disambiguation(tools, adapter))
        assert len(results) == 0

    def test_disambiguation_correct_selection_passes(self):
        """Test disambiguation correct selection PASS branch."""
        tools = [
            {
                "name": "searchCustomers",
                "description": "Search for customers by name or email address",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}},
            },
            {
                "name": "findCustomers",
                "description": "Find customers by name or email address",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}},
            },
        ]

        class CorrectAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {"tool_name": "searchCustomers", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                return "I need to searchCustomers"

        adapter = CorrectAdapter()
        results = _run(_check_tool_disambiguation(tools, adapter))
        pass_checks = [c for tr in results for c in tr.checks if c.status == Status.PASS]
        assert len(pass_checks) >= 1

    def test_disambiguation_selected_tool_b_prerequisite(self):
        """Test disambiguation selected tool_b with prerequisite check."""
        tools = [
            {"name": "updateUserProfile", "description": "Update a user profile with new personal information and settings"},
            {"name": "getUserProfile", "description": "Get user profile with personal information and settings"},
        ]

        class PrereqToolBAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {"tool_name": "getUserProfile", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                if "reasonable prerequisite" in prompt:
                    return '{"prerequisite": true, "reason": "Need to get current profile first"}'
                return "scenario"

        adapter = PrereqToolBAdapter()
        results = _run(_check_tool_disambiguation(tools, adapter))
        warn_checks = [c for tr in results for c in tr.checks if c.status == Status.WARN and c.details.get("prerequisite")]
        assert len(warn_checks) >= 1

    def test_disambiguation_selected_tool_b_fail_with_suggestion(self):
        """Test disambiguation selected tool_b FAIL with suggestion."""
        tools = [
            {
                "name": "searchCustomers",
                "description": "Search for customers by name or email address",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}},
            },
            {
                "name": "findCustomers",
                "description": "Find customers by name or email address",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}},
            },
        ]

        class WrongToolBAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {"tool_name": "findCustomers", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                if "reasonable prerequisite" in prompt:
                    return '{"prerequisite": false, "reason": "Not a prerequisite"}'
                if "Suggest an improved description" in prompt:
                    return "Improved description for searchCustomers"
                return "scenario"

        adapter = WrongToolBAdapter()
        results = _run(_check_tool_disambiguation(tools, adapter))
        fail_checks = [c for tr in results for c in tr.checks if c.status == Status.FAIL]
        assert len(fail_checks) >= 1
        assert any(c.details.get("suggested_description") for c in fail_checks)

    def test_disambiguation_selected_neither(self):
        """Test disambiguation when LLM selects neither tool_a nor tool_b."""
        tools = [
            {
                "name": "searchCustomers",
                "description": "Search for customers by name or email address",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}},
            },
            {
                "name": "findCustomers",
                "description": "Find customers by name or email address",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}},
            },
            {"name": "other_tool", "description": "Some completely different tool"},
        ]

        class NeitherAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {"tool_name": "other_tool", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                return "scenario"

        adapter = NeitherAdapter()
        results = _run(_check_tool_disambiguation(tools, adapter))
        warn_checks = [c for tr in results for c in tr.checks if c.status == Status.WARN and "other_tool" in c.message]
        assert len(warn_checks) >= 1

    def test_disambiguation_exception_handler(self):
        """Test disambiguation exception handler."""
        tools = [
            {
                "name": "searchCustomers",
                "description": "Search for customers by name or email address",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}},
            },
            {
                "name": "findCustomers",
                "description": "Find customers by name or email address",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "email": {"type": "string"}}},
            },
        ]

        class ErrorDisambigAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                raise RuntimeError("API error")

            async def generate_answer(self, tool_result, prompt):
                raise RuntimeError("API error")

        adapter = ErrorDisambigAdapter()
        results = _run(_check_tool_disambiguation(tools, adapter))
        skip_checks = [c for tr in results for c in tr.checks if c.status == Status.SKIP]
        assert len(skip_checks) >= 1

    def test_safety_resistance_exception_handler(self):
        """Test safety resistance exception handler."""
        tools = SAMPLE_TOOLS

        class ErrorSafetyAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                raise RuntimeError("API error")

        adapter = ErrorSafetyAdapter()
        results = _run(_check_safety_resistance(tools, adapter))
        skip_checks = [c for tr in results for c in tr.checks if c.status == Status.SKIP]
        assert len(skip_checks) >= 1

    def test_check_llm_all_crash_handler(self):
        """Test check_llm_all handles check function crashes."""
        import unittest.mock as mock

        class PartialErrorAdapter(MockAdapter):
            async def generate_answer(self, tool_result, prompt):
                raise RuntimeError("LLM down")

        adapter = PartialErrorAdapter()

        with mock.patch('src.app.eval.llm_eval._check_description_clarity', side_effect=RuntimeError("Check crashed")):
            layer = _run(check_llm_all(SAMPLE_TOOLS, adapter))
            assert layer.layer == "llm"

    def test_gt_tool_selection_fail_with_suggestion(self):
        """Test ground truth tool selection failure with suggested description."""
        tools = [
            {"name": "tool_a", "description": "Does A things"},
            {"name": "tool_b", "description": "Does B things"},
        ]

        class WrongWithSuggestion(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {"tool_name": "tool_b", "arguments": {}}

            async def generate_answer(self, tool_result, prompt):
                if "reasonable prerequisite" in prompt:
                    return '{"prerequisite": false, "reason": "Not a prerequisite"}'
                if "Suggest an improved description" in prompt:
                    return "Better description for tool_a"
                return "Use tool_a to do A"

        adapter = WrongWithSuggestion()
        gt = [{"expected_tool_selection": ["tool_a"], "prompts": ["Do A"]}]
        results = _run(_check_tool_selection(tools, adapter, ground_truth=gt))
        check = results[0].checks[0]
        assert check.status == Status.FAIL
        assert check.details.get("suggested_description") == "Better description for tool_a"

    def test_arg_generation_type_mismatch(self):
        """Test arg generation type check fails."""
        class WrongTypeAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {
                    "tool_name": "search_users",
                    "arguments": {"query": "test", "limit": "10"},
                }

            async def generate_answer(self, tool_result, prompt):
                return "Search for users"

        adapter = WrongTypeAdapter()
        results = _run(_check_arg_generation(SAMPLE_TOOLS[:1], adapter))
        checks = results[0].checks
        type_warns = [c for c in checks if c.status == Status.WARN and "limit" in c.message and "type" in c.check_id]
        assert len(type_warns) >= 1

    def test_arg_generation_ground_truth_validation(self):
        """Test arg generation ground truth validation."""
        class ArgGenAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {
                    "tool_name": "search_users",
                    "arguments": {"query": "alice", "limit": 5},
                }

            async def generate_answer(self, tool_result, prompt):
                return "scenario"

        adapter = ArgGenAdapter()
        gt = [{
            "expected_tool_selection": ["search_users"],
            "prompts": ["Find users named Alice"],
            "expected_args": {"query": "alice", "limit": 10}
        }]
        results = _run(_check_arg_generation(SAMPLE_TOOLS[:1], adapter, ground_truth=gt))
        checks = results[0].checks
        gt_warns = [c for c in checks if "ground_truth" in c.check_id]
        assert len(gt_warns) >= 1

    def test_disambiguation_seen_pairs_dedup_via_mock(self):
        """Test line 534: seen_pairs dedup by mocking detect_overlaps to return duplicate pairs."""
        import unittest.mock as mock
        from src.app.eval.models import CheckResult as CR

        duplicate_overlaps = [
            CR(check_id="overlap.tool_pair", status=Status.WARN, message="overlap",
               details={"tool_a": "searchCustomers", "tool_b": "findCustomers"}),
            CR(check_id="overlap.tool_pair", status=Status.WARN, message="overlap again",
               details={"tool_a": "findCustomers", "tool_b": "searchCustomers"}),
        ]
        tools = [
            {"name": "searchCustomers", "description": "Search for customers by name or email address",
             "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
            {"name": "findCustomers", "description": "Find customers by name or email address",
             "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
        ]

        class CorrectAdapter(MockAdapter):
            async def select_tool(self, tools, prompt):
                return {"tool_name": "searchCustomers", "arguments": {}}
            async def generate_answer(self, tool_result, prompt):
                return "Search for customers"

        adapter = CorrectAdapter()
        with mock.patch("src.app.eval.llm_eval.detect_overlaps", return_value=duplicate_overlaps):
            results = _run(_check_tool_disambiguation(tools, adapter))
        assert len(results) == 1

    def test_disambiguation_tool_not_found_via_mock(self):
        """Test line 540: tool_a or tool_b not in tools list."""
        import unittest.mock as mock
        from src.app.eval.models import CheckResult as CR

        overlaps_with_missing = [
            CR(check_id="overlap.tool_pair", status=Status.WARN, message="overlap",
               details={"tool_a": "nonexistent_tool", "tool_b": "also_missing"}),
        ]
        tools = [
            {"name": "existing_tool", "description": "An existing tool"},
        ]

        adapter = MockAdapter()
        with mock.patch("src.app.eval.llm_eval.detect_overlaps", return_value=overlaps_with_missing):
            results = _run(_check_tool_disambiguation(tools, adapter))
        assert len(results) == 0

    def test_check_llm_all_crash_handler_via_mock(self):
        """Test lines 733-734: check_llm_all exception handler when a check function crashes entirely."""
        import unittest.mock as mock

        adapter = MockAdapter()

        def crash(*args, **kwargs):
            raise RuntimeError("Check function crashed")

        async_crash = mock.AsyncMock(side_effect=RuntimeError("Check function crashed"))

        with mock.patch("src.app.eval.llm_eval._check_description_clarity", async_crash):
            layer = _run(check_llm_all(SAMPLE_TOOLS[:1], adapter))
            assert layer.layer == "llm"
