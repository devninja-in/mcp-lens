import pytest

from src.app.eval.runner import run_single_test, run_test_suite
from src.app.eval.models import Assertion, Status, TestCase, TestSuite


async def _ok_call_fn(tool_name, arguments):
    return {"results": [1, 2, 3], "count": 3}, 50.0


async def _error_call_fn(tool_name, arguments):
    raise ValueError("missing required parameter")


class TestRunSingleTest:
    @pytest.mark.asyncio
    async def test_pass(self):
        tc = TestCase(
            id="basic",
            tool_name="search",
            input={"q": "test"},
            assertions=[
                Assertion(type="is_array", path="results"),
                Assertion(type="not_empty", path="results"),
            ],
        )
        result = await run_single_test(tc, _ok_call_fn)
        assert result.tool_name == "search"
        assert len(result.checks) == 2
        assert all(c.status == Status.PASS for c in result.checks)

    @pytest.mark.asyncio
    async def test_fail_assertion(self):
        tc = TestCase(
            id="fail_check",
            tool_name="search",
            input={"q": "test"},
            assertions=[
                Assertion(type="equals", path="count", expected=999),
            ],
        )
        result = await run_single_test(tc, _ok_call_fn)
        assert len(result.checks) == 1
        assert result.checks[0].status == Status.FAIL

    @pytest.mark.asyncio
    async def test_expected_error(self):
        tc = TestCase(
            id="neg",
            tool_name="search",
            input={},
            expect_error=True,
        )
        result = await run_single_test(tc, _error_call_fn)
        assert len(result.checks) == 1
        assert result.checks[0].status == Status.PASS
        assert "correctly rejected" in result.checks[0].message

    @pytest.mark.asyncio
    async def test_unexpected_error(self):
        tc = TestCase(
            id="err",
            tool_name="search",
            input={},
            expect_error=False,
        )
        result = await run_single_test(tc, _error_call_fn)
        assert len(result.checks) == 1
        assert result.checks[0].status == Status.FAIL
        assert "Unexpected error" in result.checks[0].message

    @pytest.mark.asyncio
    async def test_expected_error_but_got_success(self):
        tc = TestCase(
            id="should_fail",
            tool_name="search",
            input={"q": "test"},
            expect_error=True,
        )
        result = await run_single_test(tc, _ok_call_fn)
        assert len(result.checks) == 1
        assert result.checks[0].status == Status.FAIL
        assert "Expected error but call succeeded" in result.checks[0].message


class TestRunTestSuite:
    @pytest.mark.asyncio
    async def test_multiple_tests(self):
        suite = TestSuite(
            server_name="test-srv",
            test_cases=[
                TestCase(
                    id="t1",
                    tool_name="search",
                    input={"q": "a"},
                    assertions=[Assertion(type="is_array", path="results")],
                ),
                TestCase(
                    id="t2",
                    tool_name="search",
                    input={},
                    expect_error=True,
                ),
                TestCase(
                    id="t3",
                    tool_name="search",
                    input={"q": "b"},
                    assertions=[Assertion(type="equals", path="count", expected=3)],
                ),
            ],
        )
        layer = await run_test_suite(suite, _ok_call_fn)
        assert layer.layer == "functional"
        assert len(layer.tools) == 3

        assert layer.tools[0].checks[0].status == Status.PASS
        assert layer.tools[1].checks[0].status == Status.FAIL  # expect_error but _ok_call_fn succeeds
        assert layer.tools[2].checks[0].status == Status.PASS
