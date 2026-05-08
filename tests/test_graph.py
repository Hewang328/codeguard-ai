"""Tests for the LangGraph review pipeline (no OpenAI key required)."""

from __future__ import annotations

import pytest

from src.codeguard.graph import build_graph, run_review


class TestGraph:
    def test_build_graph_compiles(self):
        graph = build_graph()
        assert graph is not None

    def test_run_review_returns_all_keys(self):
        code = 'def hello():\n    """Greet."""\n    return "hi"\n'
        result = run_review(code=code, file_path="hello.py", language="python")
        assert "structure_analysis" in result
        assert "style_issues" in result
        assert "security_issues" in result
        assert "final_report" in result
        assert "messages" in result

    def test_run_review_final_report_is_markdown(self):
        code = 'def greet(name: str) -> str:\n    """Return greeting."""\n    return f"Hi {name}"\n'
        result = run_review(code=code, file_path="greet.py")
        report = result["final_report"]
        assert report is not None
        assert "# 🛡️ CodeGuard AI" in report
        assert "greet.py" in report

    def test_run_review_detects_security_issue(self):
        code = 'secret_key = "abc123secret"\neval(user_input)\n'
        result = run_review(code=code, file_path="bad.py")
        assert result["security_issues"] is not None
        assert "eval" in result["security_issues"] or "secret" in result["security_issues"].lower()

    def test_run_review_detects_style_issue(self):
        code = "def BadName():\n    pass\n"
        result = run_review(code=code, file_path="style.py")
        assert result["style_issues"] is not None
        # Should flag bad naming
        has_naming_issue = (
            "snake_case" in result["style_issues"]
            or "PascalCase" in result["style_issues"]
        )
        assert has_naming_issue

    def test_run_review_messages_populated(self):
        code = "x = 1\n"
        result = run_review(code=code, file_path="x.py")
        messages = result["messages"]
        # Expect one message per agent (4 agents)
        assert len(messages) >= 4

    def test_run_review_non_python_language(self):
        code = "function hello() { return 42; }"
        result = run_review(code=code, file_path="hello.js", language="javascript")
        assert result["structure_analysis"] is not None
        assert "Python only" in result["structure_analysis"]

    def test_run_review_empty_code_returns_report(self):
        """Even empty code should produce a report (may have syntax error)."""
        result = run_review(code="", file_path="empty.py")
        assert result["final_report"] is not None

    def test_sequential_pipeline_order(self):
        """Verify agents run in the correct order by checking message roles."""
        code = "x = 1\n"
        result = run_review(code=code, file_path="x.py")
        contents = [m["content"] for m in result["messages"]]
        structure_idx = next(
            (i for i, c in enumerate(contents) if "[StructureAgent]" in c), None
        )
        style_idx = next(
            (i for i, c in enumerate(contents) if "[StyleAgent]" in c), None
        )
        security_idx = next(
            (i for i, c in enumerate(contents) if "[SecurityAgent]" in c), None
        )
        summary_idx = next(
            (i for i, c in enumerate(contents) if "[SummaryAgent]" in c), None
        )
        assert structure_idx is not None
        assert style_idx is not None
        assert security_idx is not None
        assert summary_idx is not None
        assert structure_idx < style_idx < security_idx < summary_idx
