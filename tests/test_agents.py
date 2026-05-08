"""Tests for individual agents (no OpenAI key required)."""

from __future__ import annotations

import pytest

from src.codeguard.agents.structure_agent import analyze_structure, structure_agent
from src.codeguard.agents.style_agent import check_style, style_agent
from src.codeguard.agents.security_agent import scan_security, security_agent
from src.codeguard.agents.summary_agent import build_markdown_report, summary_agent
from src.codeguard.state import CodeReviewState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(code: str, language: str = "python") -> CodeReviewState:
    return {
        "code": code,
        "file_path": "test.py",
        "language": language,
        "structure_analysis": None,
        "style_issues": None,
        "security_issues": None,
        "final_report": None,
        "messages": [],
    }


# ---------------------------------------------------------------------------
# Structure agent tests
# ---------------------------------------------------------------------------


class TestStructureAgent:
    def test_clean_code_no_issues(self):
        code = '''
def greet(name: str) -> str:
    """Return a greeting string."""
    return f"Hello, {name}"
'''
        issues = analyze_structure(code)
        # Only docstring-missing issues at most; clean function should be minimal
        non_docstring = [i for i in issues if "docstring" not in i["message"]]
        assert len(non_docstring) == 0

    def test_detects_long_function(self):
        body = "\n".join(f"    x_{i} = {i}" for i in range(60))
        code = f'def long_func():\n    """doc"""\n{body}\n    return 1\n'
        issues = analyze_structure(code)
        messages = [i["message"] for i in issues]
        assert any("lines long" in m for m in messages)

    def test_detects_too_many_args(self):
        code = "def f(a, b, c, d, e, f, g, h):\n    pass\n"
        issues = analyze_structure(code)
        messages = [i["message"] for i in issues]
        assert any("parameters" in m for m in messages)

    def test_detects_deep_nesting(self):
        code = (
            "def f():\n"
            "    if True:\n"
            "        if True:\n"
            "            if True:\n"
            "                if True:\n"
            "                    if True:\n"
            "                        pass\n"
        )
        issues = analyze_structure(code)
        messages = [i["message"] for i in issues]
        assert any("nesting depth" in m for m in messages)

    def test_detects_missing_docstring(self):
        code = "def f():\n    pass\n"
        issues = analyze_structure(code)
        messages = [i["message"] for i in issues]
        assert any("docstring" in m for m in messages)

    def test_syntax_error_reported(self):
        code = "def f(\n    pass\n"
        issues = analyze_structure(code)
        assert len(issues) == 1
        assert issues[0]["severity"] == "error"
        assert "Syntax error" in issues[0]["message"]

    def test_god_class_detected(self):
        methods = "\n".join(
            f"    def method_{i}(self):\n        pass\n" for i in range(25)
        )
        code = f"class BigClass:\n{methods}\n"
        issues = analyze_structure(code)
        messages = [i["message"] for i in issues]
        assert any("methods" in m for m in messages)

    def test_non_python_language(self):
        state = _make_state("function hello() { return 42; }", language="javascript")
        result = structure_agent(state)
        assert "Python only" in result["structure_analysis"]

    def test_node_returns_state_keys(self):
        state = _make_state("def f():\n    pass\n")
        result = structure_agent(state)
        assert "structure_analysis" in result
        assert "messages" in result
        assert result["messages"]


# ---------------------------------------------------------------------------
# Style agent tests
# ---------------------------------------------------------------------------


class TestStyleAgent:
    def test_clean_code_no_issues(self):
        code = "def my_function():\n    pass\n"
        issues = check_style(code)
        assert len(issues) == 0

    def test_detects_long_line(self):
        long_line = "x = " + "a" * 100
        issues = check_style(long_line)
        messages = [i["message"] for i in issues]
        assert any("characters long" in m for m in messages)

    def test_detects_bad_class_name(self):
        code = "class myClass:\n    pass\n"
        issues = check_style(code)
        messages = [i["message"] for i in issues]
        assert any("PascalCase" in m for m in messages)

    def test_detects_bad_function_name(self):
        code = "def MyFunction():\n    pass\n"
        issues = check_style(code)
        messages = [i["message"] for i in issues]
        assert any("snake_case" in m for m in messages)

    def test_allows_dunder_methods(self):
        code = "class Foo:\n    def __init__(self):\n        pass\n"
        issues = check_style(code)
        # Should not flag __init__ as a naming violation
        naming_issues = [i for i in issues if "__init__" in i["message"]]
        assert len(naming_issues) == 0

    def test_detects_bare_except(self):
        code = "try:\n    pass\nexcept:\n    pass\n"
        issues = check_style(code)
        messages = [i["message"] for i in issues]
        assert any("Bare" in m or "bare" in m for m in messages)

    def test_detects_mutable_default(self):
        code = "def f(items=[]):\n    return items\n"
        issues = check_style(code)
        messages = [i["message"] for i in issues]
        assert any("mutable default" in m for m in messages)

    def test_detects_wildcard_import(self):
        code = "from os import *\n"
        issues = check_style(code)
        messages = [i["message"] for i in issues]
        assert any("Wildcard" in m or "wildcard" in m for m in messages)

    def test_non_python_language(self):
        state = _make_state("const x = 1;", language="javascript")
        result = style_agent(state)
        assert "Python only" in result["style_issues"]


# ---------------------------------------------------------------------------
# Security agent tests
# ---------------------------------------------------------------------------


class TestSecurityAgent:
    def test_detects_hardcoded_password(self):
        code = 'password = "super_secret_123"\n'
        issues = scan_security(code)
        messages = [i["message"] for i in issues]
        assert any("secret" in m.lower() or "credential" in m.lower() for m in messages)

    def test_detects_eval(self):
        code = "result = eval(user_input)\n"
        issues = scan_security(code)
        messages = [i["message"] for i in issues]
        assert any("eval" in m for m in messages)

    def test_detects_exec(self):
        code = "exec(user_code)\n"
        issues = scan_security(code)
        messages = [i["message"] for i in issues]
        assert any("exec" in m for m in messages)

    def test_detects_pickle(self):
        code = "import pickle\ndata = pickle.loads(raw_bytes)\n"
        issues = scan_security(code)
        messages = [i["message"] for i in issues]
        assert any("pickle" in m for m in messages)

    def test_detects_subprocess_shell(self):
        code = "import subprocess\nsubprocess.run(cmd, shell=True)\n"
        issues = scan_security(code)
        messages = [i["message"] for i in issues]
        assert any("shell=True" in m or "shell injection" in m for m in messages)

    def test_detects_sql_injection(self):
        code = 'query = f"SELECT * FROM users WHERE id = {user_id}"\n'
        issues = scan_security(code)
        messages = [i["message"] for i in issues]
        assert any("SQL" in m or "injection" in m.lower() for m in messages)

    def test_detects_sql_injection_percent_format(self):
        code = 'query = "SELECT * FROM users WHERE id = %s" % user_id\n'
        issues = scan_security(code)
        messages = [i["message"] for i in issues]
        assert any("SQL" in m or "injection" in m.lower() for m in messages)

    def test_detects_sql_injection_str_format(self):
        code = 'query = "SELECT * FROM users WHERE id = {}".format(user_id)\n'
        issues = scan_security(code)
        messages = [i["message"] for i in issues]
        assert any("SQL" in m or "injection" in m.lower() for m in messages)

    def test_clean_code_no_issues(self):
        code = 'def greet(name: str) -> str:\n    """Greet."""\n    return f"Hi {name}"\n'
        issues = scan_security(code)
        assert len(issues) == 0

    def test_node_returns_state_keys(self):
        state = _make_state("eval('x')")
        result = security_agent(state)
        assert "security_issues" in result
        assert "messages" in result


# ---------------------------------------------------------------------------
# Summary agent tests
# ---------------------------------------------------------------------------


class TestSummaryAgent:
    def test_build_report_structure(self):
        report = build_markdown_report(
            file_path="src/app.py",
            language="python",
            structure_analysis="🟡 Line 5: some structural issue",
            style_issues="🔵 Line 10: some style issue",
            security_issues="No security issues detected.",
        )
        assert "# 🛡️ CodeGuard AI" in report
        assert "src/app.py" in report
        assert "Structure Analysis" in report
        assert "Style & Convention Check" in report
        assert "Security Scan" in report
        assert "Summary" in report

    def test_overall_critical_when_security_critical(self):
        report = build_markdown_report(
            file_path="x.py",
            language="python",
            structure_analysis=None,
            style_issues=None,
            security_issues="🚨 [CRITICAL] Line 1: eval usage",
        )
        assert "Critical issues found" in report

    def test_overall_ok_when_no_issues(self):
        report = build_markdown_report(
            file_path="x.py",
            language="python",
            structure_analysis="No structural issues detected.",
            style_issues="No style issues detected.",
            security_issues="No security issues detected.",
        )
        assert "No issues found" in report

    def test_node_produces_final_report(self):
        state: CodeReviewState = {
            "code": "x = 1",
            "file_path": "test.py",
            "language": "python",
            "structure_analysis": "No issues.",
            "style_issues": "No issues.",
            "security_issues": "No issues.",
            "final_report": None,
            "messages": [],
        }
        result = summary_agent(state)
        assert "final_report" in result
        assert result["final_report"] is not None
        assert "CodeGuard AI" in result["final_report"]

    def test_report_includes_executive_summary_when_provided(self):
        report = build_markdown_report(
            file_path="x.py",
            language="python",
            structure_analysis=None,
            style_issues=None,
            security_issues=None,
            executive_summary="This is the exec summary.",
        )
        assert "Executive Summary" in report
        assert "This is the exec summary." in report
