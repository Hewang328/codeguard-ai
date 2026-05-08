"""Structure Analysis Agent.

Responsibilities
----------------
* Parse Python source with the built-in ``ast`` module.
* Detect structural issues: overly long functions, excessive nesting,
  God-classes, missing docstrings, excessive function arguments.
* Optionally call an LLM for deeper architectural commentary when
  the OPENAI_API_KEY environment variable is present.
"""

from __future__ import annotations

import ast
import os
import textwrap
from typing import Any, Dict, List

from ..state import CodeReviewState

# ---------------------------------------------------------------------------
# AST-based structural checks
# ---------------------------------------------------------------------------

MAX_FUNCTION_LINES = 50
MAX_NESTING_DEPTH = 4
MAX_FUNCTION_ARGS = 7
MAX_CLASS_METHODS = 20


def _nesting_depth(node: ast.AST, current: int = 0) -> int:
    """Return the maximum nesting depth of control-flow constructs."""
    control_nodes = (
        ast.If,
        ast.For,
        ast.While,
        ast.With,
        ast.Try,
        ast.ExceptHandler,
    )
    depths = [current]
    for child in ast.iter_child_nodes(node):
        if isinstance(child, control_nodes):
            depths.append(_nesting_depth(child, current + 1))
        else:
            depths.append(_nesting_depth(child, current))
    return max(depths)


def _function_line_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Return the approximate number of lines in a function body."""
    if not node.body:
        return 0
    first = node.body[0]
    last = node.body[-1]
    return getattr(last, "end_lineno", last.lineno) - first.lineno + 1


def analyze_structure(code: str) -> List[Dict[str, Any]]:
    """Return a list of structural issue dicts found in *code*."""
    issues: List[Dict[str, Any]] = []

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        issues.append(
            {
                "severity": "error",
                "line": exc.lineno or 0,
                "message": f"Syntax error: {exc.msg}",
            }
        )
        return issues

    for node in ast.walk(tree):
        # ── Function / method checks ──────────────────────────────────────
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Long function
            lines = _function_line_count(node)
            if lines > MAX_FUNCTION_LINES:
                issues.append(
                    {
                        "severity": "warning",
                        "line": node.lineno,
                        "message": (
                            f"Function '{node.name}' is {lines} lines long "
                            f"(max {MAX_FUNCTION_LINES}). "
                            "Consider breaking it into smaller units."
                        ),
                    }
                )

            # Too many arguments
            n_args = len(node.args.args)
            if n_args > MAX_FUNCTION_ARGS:
                issues.append(
                    {
                        "severity": "warning",
                        "line": node.lineno,
                        "message": (
                            f"Function '{node.name}' has {n_args} parameters "
                            f"(max {MAX_FUNCTION_ARGS}). "
                            "Consider using a dataclass or config object."
                        ),
                    }
                )

            # Deep nesting
            depth = _nesting_depth(node)
            if depth > MAX_NESTING_DEPTH:
                issues.append(
                    {
                        "severity": "warning",
                        "line": node.lineno,
                        "message": (
                            f"Function '{node.name}' has nesting depth {depth} "
                            f"(max {MAX_NESTING_DEPTH}). "
                            "Reduce nesting with early returns or helper functions."
                        ),
                    }
                )

            # Missing docstring
            if not (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                issues.append(
                    {
                        "severity": "info",
                        "line": node.lineno,
                        "message": (
                            f"Function '{node.name}' is missing a docstring."
                        ),
                    }
                )

        # ── Class checks ─────────────────────────────────────────────────
        if isinstance(node, ast.ClassDef):
            methods = [
                n
                for n in ast.walk(node)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            if len(methods) > MAX_CLASS_METHODS:
                issues.append(
                    {
                        "severity": "warning",
                        "line": node.lineno,
                        "message": (
                            f"Class '{node.name}' has {len(methods)} methods "
                            f"(max {MAX_CLASS_METHODS}). "
                            "Consider splitting into multiple classes (SRP)."
                        ),
                    }
                )

            # Missing class docstring
            if not (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                issues.append(
                    {
                        "severity": "info",
                        "line": node.lineno,
                        "message": (
                            f"Class '{node.name}' is missing a docstring."
                        ),
                    }
                )

    return issues


def _format_issues(issues: List[Dict[str, Any]]) -> str:
    if not issues:
        return "No structural issues detected."
    lines = []
    for issue in issues:
        icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(
            issue["severity"], "⚪"
        )
        lines.append(f"{icon} Line {issue['line']}: {issue['message']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM-assisted deep analysis (optional)
# ---------------------------------------------------------------------------


def _llm_structure_analysis(code: str, ast_summary: str) -> str:
    """Call the LLM for architectural commentary if API key is available."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return ""

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        system = SystemMessage(
            content=(
                "You are an expert software architect performing a code review. "
                "Analyze the structure and architecture of the provided code. "
                "Focus on: modularity, separation of concerns, cohesion, coupling, "
                "adherence to SOLID principles, and overall design quality. "
                "Be concise and actionable. Respond in English."
            )
        )
        human = HumanMessage(
            content=(
                f"AST analysis summary:\n{ast_summary}\n\n"
                f"Source code:\n```\n{textwrap.shorten(code, 3000)}\n```\n\n"
                "Provide a brief architectural review with specific recommendations."
            )
        )
        response = llm.invoke([system, human])
        return response.content
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------


def structure_agent(state: CodeReviewState) -> dict:
    """LangGraph node: performs structural analysis of the code."""
    code = state["code"]
    language = state.get("language", "python")

    if language.lower() != "python":
        analysis = (
            f"⚠️ AST-based structural analysis is currently supported for Python only. "
            f"Detected language: {language}."
        )
        return {
            "structure_analysis": analysis,
            "messages": [
                {"role": "assistant", "content": f"[StructureAgent] {analysis}"}
            ],
        }

    issues = analyze_structure(code)
    ast_summary = _format_issues(issues)

    # Optionally enrich with LLM commentary
    llm_commentary = _llm_structure_analysis(code, ast_summary)

    if llm_commentary:
        full_analysis = f"{ast_summary}\n\n**Architectural Commentary (LLM):**\n{llm_commentary}"
    else:
        full_analysis = ast_summary

    return {
        "structure_analysis": full_analysis,
        "messages": [
            {
                "role": "assistant",
                "content": f"[StructureAgent] Found {len(issues)} structural issue(s).",
            }
        ],
    }
