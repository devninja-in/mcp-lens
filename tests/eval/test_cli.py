import json
from pathlib import Path
from textwrap import dedent

import pytest

from src.app.eval.cli import main


@pytest.fixture
def tools_yaml(tmp_path):
    f = tmp_path / "tools.yaml"
    f.write_text(
        dedent("""\
        tools:
          - name: search_users
            description: Search for users by name or email address
            inputSchema:
              type: object
              properties:
                name:
                  type: string
                  description: Name to search for
              required:
                - name
            annotations:
              readOnlyHint: true
              destructiveHint: false
    """)
    )
    return str(f)


@pytest.fixture
def bad_tools_yaml(tmp_path):
    f = tmp_path / "bad_tools.yaml"
    f.write_text(
        dedent("""\
        tools:
          - name: ""
            description: ""
    """)
    )
    return str(f)


class TestValidate:
    def test_good_tools_pass(self, tools_yaml, capsys):
        code = main(["validate", tools_yaml])
        assert code == 0
        out = capsys.readouterr().out
        assert "PASSED" in out

    def test_bad_tools_may_fail(self, bad_tools_yaml, capsys):
        main(["validate", bad_tools_yaml])
        out = capsys.readouterr().out
        assert "MCP Tool Evaluation Report" in out

    def test_nonexistent_file(self):
        with pytest.raises(SystemExit):
            main(["validate", "/nonexistent/path.yaml"])


class TestSecurity:
    def test_clean_tools(self, tools_yaml, capsys):
        code = main(["security", tools_yaml])
        assert code == 0

    def test_output_contains_security(self, tools_yaml, capsys):
        main(["security", tools_yaml])
        out = capsys.readouterr().out
        assert "SECURITY" in out


class TestReport:
    def test_text_format(self, tools_yaml, capsys):
        main(["report", tools_yaml, "--format", "text"])
        out = capsys.readouterr().out
        assert "MCP Tool Evaluation Report" in out

    def test_json_format(self, tools_yaml, capsys):
        main(["report", tools_yaml, "--format", "json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "overall_score" in data

    def test_output_to_file(self, tools_yaml, tmp_path):
        out_path = str(tmp_path / "report.json")
        main(["report", tools_yaml, "--format", "json", "--output", out_path])
        assert Path(out_path).exists()
        data = json.loads(Path(out_path).read_text())
        assert "overall_score" in data


class TestCompare:
    def test_compare_same(self, tmp_path):
        report = {
            "timestamp": "2026-09-10",
            "server_name": "test",
            "overall_score": 80.0,
            "gate_passed": True,
            "layers": {},
            "metadata": {},
        }
        baseline = tmp_path / "baseline.json"
        current = tmp_path / "current.json"
        baseline.write_text(json.dumps(report))
        current.write_text(json.dumps(report))
        code = main(["compare", str(baseline), str(current)])
        assert code == 0

    def test_regression(self, tmp_path, capsys):
        baseline = tmp_path / "baseline.json"
        current = tmp_path / "current.json"
        baseline.write_text(
            json.dumps(
                {
                    "timestamp": "",
                    "server_name": "test",
                    "overall_score": 90.0,
                    "gate_passed": True,
                    "layers": {},
                    "metadata": {},
                }
            )
        )
        current.write_text(
            json.dumps(
                {
                    "timestamp": "",
                    "server_name": "test",
                    "overall_score": 60.0,
                    "gate_passed": False,
                    "layers": {},
                    "metadata": {},
                }
            )
        )
        code = main(["compare", str(baseline), str(current)])
        assert code == 1
        out = capsys.readouterr().out
        assert "Regressed: True" in out


class TestNoCommand:
    def test_no_args_returns_2(self, capsys):
        code = main([])
        assert code == 2
