import asyncio
from textwrap import dedent

from src.app.eval.benchmark import load_benchmark, run_benchmark
from src.app.eval.model_adapter import MockAdapter
from src.app.eval.models import Status


class TestLoadBenchmark:
    def test_load_valid(self, tmp_path):
        f = tmp_path / "bench.yaml"
        f.write_text(
            dedent("""\
            benchmark:
              name: test-bench
              server_name: svc
              version: "1.0"
            tasks:
              - id: t1
                prompt: "Find user"
                expected_tools: [search_users]
                expected_args:
                  search_users:
                    name: "Alice"
        """)
        )
        suite = load_benchmark(f)
        assert suite.name == "test-bench"
        assert len(suite.scenarios) == 1
        assert suite.scenarios[0].prompt == "Find user"
        assert suite.scenarios[0].expected_tools == ["search_users"]
        assert suite.scenarios[0].expected_args["search_users"]["name"] == "Alice"

    def test_load_multiple_tasks(self, tmp_path):
        f = tmp_path / "bench.yaml"
        f.write_text(
            dedent("""\
            benchmark:
              name: multi
            tasks:
              - id: t1
                prompt: "A"
                expected_tools: [a]
              - id: t2
                prompt: "B"
                expected_tools: [b]
                tags: [smoke]
        """)
        )
        suite = load_benchmark(f)
        assert len(suite.scenarios) == 2
        assert suite.scenarios[1].tags == ["smoke"]

    def test_load_defaults(self, tmp_path):
        f = tmp_path / "bench.yaml"
        f.write_text(
            dedent("""\
            benchmark: {}
            tasks:
              - id: t1
                prompt: "X"
        """)
        )
        suite = load_benchmark(f)
        assert suite.name == ""
        assert suite.scenarios[0].expected_tools == []
        assert suite.scenarios[0].expected_args == {}


class TestRunBenchmark:
    def test_correct_selection(self):
        from src.app.eval.models import BenchmarkScenario, BenchmarkSuite

        suite = BenchmarkSuite(
            name="test",
            scenarios=[
                BenchmarkScenario(
                    id="s1",
                    prompt="Find user",
                    expected_tools=["search_users"],
                    expected_args={"search_users": {"name": "Alice"}},
                )
            ],
        )
        tools = [{"name": "search_users"}, {"name": "delete_users"}]
        adapter = MockAdapter(
            responses={
                "Find user": {"tool_name": "search_users", "arguments": {"name": "Alice"}},
            }
        )
        result = asyncio.get_event_loop().run_until_complete(run_benchmark(suite, tools, adapter))
        assert result.layer == "benchmark"
        assert len(result.tools) == 2
        selection = result.tools[0]
        assert any(c.status == Status.PASS for c in selection.checks)

    def test_wrong_selection(self):
        from src.app.eval.models import BenchmarkScenario, BenchmarkSuite

        suite = BenchmarkSuite(
            name="test",
            scenarios=[
                BenchmarkScenario(
                    id="s1",
                    prompt="Find user",
                    expected_tools=["search_users"],
                )
            ],
        )
        tools = [{"name": "search_users"}, {"name": "delete_users"}]
        adapter = MockAdapter(
            responses={
                "Find user": {"tool_name": "delete_users", "arguments": {}},
            }
        )
        result = asyncio.get_event_loop().run_until_complete(run_benchmark(suite, tools, adapter))
        selection = result.tools[0]
        assert any(c.status == Status.FAIL for c in selection.checks)
