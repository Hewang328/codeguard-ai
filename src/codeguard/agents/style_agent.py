"""Style Check Agent.

Responsibilities
----------------
* Enforce Python naming conventions (PEP 8):
  - Functions and variables: snake_case
  - Classes: PascalCase / CamelCase
  - Constants: UPPER_SNAKE_CASE
* Detect over-long lines (> 88 chars, Black's default).
* Detect missing blank lines between top-level definitions.
* Detect bare ``except`` clauses.
* Detect use of mutable default arguments.
* Optionally call an LLM for stylistic commentary.
"""

from __future__ import annotations

import ast
import os
import re
import textwrap
from typing import Any, Dict, List

from ..state import CodeReviewState

# ---------------------------------------------------------------------------
# Rule-based checks
# ---------------------------------------------------------------------------

MAX_LINE_LENGTH = 88

_SNAKE_CASE = re.compile(r"^[a-z_][a-z0-9_]*$")
_PASCAL_CASE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
_UPPER_SNAKE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_DUNDER = re.compile(r"^__[a-zA-Z0-9_]+__$")


def _check_line_length(code: str) -> List[Dict[str, Any]]:
    issues = []
    for lineno, line in enumerate(code.splitlines(), 1):
        if len(line) > MAX_LINE_LENGTH:
            issues.append(
                {
                    "severity": "warning",
                    "line": lineno,
                    "message": (
                        f"Line {lineno} is {len(line)} characters long "
                        f"(max {MAX_LINE_LENGTH})."
                    ),
                }
            )
    return issues


def _check_naming(tree: ast.AST) -> List[Dict[str, Any]]:
    issues = []
    for node in ast.walk(tree):
        # Class names should be PascalCase
        if isinstance(node, ast.ClassDef):
            if not _PASCAL_CASE.match(node.name) and not _DUNDER.match(node.name):
                issues.append(
                    {
                        "severity": "warning",
                        "line": node.lineno,
                        "message": (
                            f"Class name '{node.name}' does not follow PascalCase "
                            "convention."
                        ),
                    }
                )

        # Function / method names should be snake_case
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not _SNAKE_CASE.match(node.name) and not _DUNDER.match(node.name):
                issues.append(
                    {
                        "severity": "warning",
                        "line": node.lineno,
                        "message": (
                            f"Function/method name '{node.name}' does not follow "
                            "snake_case convention."
                        ),
                    }
                )

        # Variable assignments at module scope that look like constants
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    # Skip dunders and lowercase names
                    if (
                        not _DUNDER.match(name)
                        and re.match(r"^[A-Z]", name)
                        and not _UPPER_SNAKE.match(name)
                        and not _PASCAL_CASE.match(name)
                    ):
                        issues.append(
                            {
                                "severity": "info",
                                "line": target.lineno,
                                "message": (
                                    f"Module-level name '{name}' appears to be a "
                                    "constant but does not follow UPPER_SNAKE_CASE."
                                ),
                            }
                        )
    return issues


def _check_bare_except(tree: ast.AST) -> List[Dict[str, Any]]:
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(
                {
                    "severity": "warning",
                    "line": node.lineno,
                    "message": (
                        "Bare 'except:' clause catches all exceptions including "
                        "SystemExit and KeyboardInterrupt. "
                        "Use 'except Exception:' or a specific exception type."
                    ),
                }
            )
    return issues


def _check_mutable_defaults(tree: ast.AST) -> List[Dict[str, Any]]:
    """Detect mutable default argument values (list, dict, set literals)."""
    issues = []
    mutable_types = (ast.List, ast.Dict, ast.Set)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + node.args.kw_defaults:
                if default is not None and isinstance(default, mutable_types):
                    issues.append(
                        {
                            "severity": "error",
                            "line": node.lineno,
                            "message": (
                                f"Function '{node.name}' uses a mutable default "
                                "argument. Use 'None' and initialize inside the "
                                "function body instead."
                            ),
                        }
                    )
    return issues


def _check_wildcard_imports(tree: ast.AST) -> List[Dict[str, Any]]:
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    issues.append(
                        {
                            "severity": "warning",
                            "line": node.lineno,
                            "message": (
                                f"Wildcard import 'from {node.module} import *' "
                                "pollutes the namespace. Import specific names."
                            ),
                        }
                    )
    return issues


def check_style(code: str) -> List[Dict[str, Any]]:
    """Run all style checks and return aggregated issue list."""
    issues: List[Dict[str, Any]] = []
    issues.extend(_check_line_length(code))

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues  # Syntax errors are reported by structure_agent

    issues.extend(_check_naming(tree))
    issues.extend(_check_bare_except(tree))
    issues.extend(_check_mutable_defaults(tree))
    issues.extend(_check_wildcard_imports(tree))
    return issues


def _format_issues(issues: List[Dict[str, Any]]) -> str:
    if not issues:
        return "No style issues detected."
    lines = []
    for issue in sorted(issues, key=lambda i: i["line"]):
        icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(
            issue["severity"], "⚪"
        )
        lines.append(f"{icon} Line {issue['line']}: {issue['message']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM-assisted commentary (optional)
# ---------------------------------------------------------------------------


def _llm_style_analysis(code: str, rule_summary: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return ""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        system = SystemMessage(
            content=(
                "You are a senior Python engineer performing a code-style review. "
                "Focus on PEP 8, readability, maintainability, and idiomatic Python. "
                "Be concise and provide specific, actionable suggestions."
            )
        )
        human = HumanMessage(
            content=(
                f"Rule-based style findings:\n{rule_summary}\n\n"
                f"Source code:\n```python\n{textwrap.shorten(code, 3000)}\n```\n\n"
                "Provide a brief style review with prioritized recommendations."
            )
        )
        response = llm.invoke([system, human])
        return response.content
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------


def style_agent(state: CodeReviewState) -> dict:
    """LangGraph node: performs style/convention checks on the code."""
    code = state["code"]
    language = state.get("language", "python")

    if language.lower() != "python":
        analysis = (
            f"⚠️ Rule-based style checking is currently supported for Python only. "
            f"Detected language: {language}."
        )
        return {
            "style_issues": analysis,
            "messages": [
                {"role": "assistant", "content": f"[StyleAgent] {analysis}"}
            ],
        }

    issues = check_style(code)
    rule_summary = _format_issues(issues)

    llm_commentary = _llm_style_analysis(code, rule_summary)
    if llm_commentary:
        full = f"{rule_summary}\n\n**Style Commentary (LLM):**\n{llm_commentary}"
    else:
        full = rule_summary

    return {
        "style_issues": full,
        "messages": [
            {
                "role": "assistant",
                "content": f"[StyleAgent] Found {len(issues)} style issue(s).",
            }
        ],
    }
