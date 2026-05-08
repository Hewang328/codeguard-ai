"""Security Scan Agent.

Responsibilities
----------------
* Detect hardcoded secrets / passwords / API keys via regex patterns.
* Detect dangerous built-ins: eval, exec, __import__.
* Detect SQL injection risks (string-formatted queries).
* Detect insecure deserialization (pickle.loads).
* Detect unsafe use of ``subprocess`` with shell=True.
* Detect insecure random number generation (random instead of secrets).
* Detect path traversal patterns.
* Optionally call an LLM for deeper vulnerability analysis.
"""

from __future__ import annotations

import ast
import os
import re
import textwrap
from typing import Any, Dict, List

from ..state import CodeReviewState

# ---------------------------------------------------------------------------
# Regex-based secret detection
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: List[tuple[str, re.Pattern[str]]] = [
    (
        "Hardcoded password assignment",
        re.compile(
            r'(?i)(password|passwd|pwd|secret|api_key|apikey|token|auth_token)'
            r'\s*=\s*["\'][^"\']{4,}["\']',
        ),
    ),
    (
        "AWS Access Key",
        re.compile(r"(?<![A-Z0-9])[A-Z0-9]{20}(?![A-Z0-9])"),
    ),
    (
        "Private key header",
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "Generic bearer token",
        re.compile(r'(?i)bearer\s+[a-zA-Z0-9\-_\.]{20,}'),
    ),
]

# ---------------------------------------------------------------------------
# AST-based checks
# ---------------------------------------------------------------------------


def _check_dangerous_builtins(tree: ast.AST) -> List[Dict[str, Any]]:
    """Flag direct calls to eval/exec/__import__."""
    dangerous = {"eval", "exec", "__import__"}
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in dangerous:
                issues.append(
                    {
                        "severity": "critical",
                        "line": node.lineno,
                        "message": (
                            f"Use of '{name}' is dangerous and can lead to "
                            "arbitrary code execution. Avoid if possible; "
                            "validate and sanitize all inputs if unavoidable."
                        ),
                    }
                )
    return issues


def _check_sql_injection(tree: ast.AST, code: str) -> List[Dict[str, Any]]:
    """Detect f-string / %-format / .format() SQL query construction."""
    issues = []
    sql_keywords = re.compile(
        r"(?i)\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC)\b"
    )
    lines = code.splitlines()
    for lineno, line in enumerate(lines, 1):
        if sql_keywords.search(line) and (
            "%" in line or ".format(" in line or "f'" in line or 'f"' in line
        ):
            issues.append(
                {
                    "severity": "critical",
                    "line": lineno,
                    "message": (
                        "Possible SQL injection: SQL query appears to be built "
                        "with string formatting. Use parameterized queries / "
                        "prepared statements instead."
                    ),
                }
            )
    return issues


def _check_insecure_deserialization(tree: ast.AST) -> List[Dict[str, Any]]:
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in {"loads", "load"}
                and isinstance(func.value, ast.Name)
                and func.value.id == "pickle"
            ):
                issues.append(
                    {
                        "severity": "critical",
                        "line": node.lineno,
                        "message": (
                            "pickle.loads / pickle.load can execute arbitrary "
                            "code when deserializing untrusted data. "
                            "Use a safe format such as JSON."
                        ),
                    }
                )
    return issues


def _check_subprocess_shell(tree: ast.AST) -> List[Dict[str, Any]]:
    """Flag subprocess calls with shell=True."""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Look for keyword argument shell=True
            for kw in node.keywords:
                if (
                    kw.arg == "shell"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    issues.append(
                        {
                            "severity": "high",
                            "line": node.lineno,
                            "message": (
                                "subprocess called with shell=True. "
                                "This can lead to shell injection attacks. "
                                "Pass a list of arguments and set shell=False."
                            ),
                        }
                    )
    return issues


def _check_insecure_random(tree: ast.AST) -> List[Dict[str, Any]]:
    """Flag use of random module for security-sensitive operations."""
    issues = []
    security_contexts = re.compile(
        r"(?i)(token|password|secret|key|salt|nonce|csrf|otp|pin)"
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "random"
            ):
                # Only flag if used in an assignment with a security-sounding name
                issues.append(
                    {
                        "severity": "high",
                        "line": node.lineno,
                        "message": (
                            "Use of 'random' module detected. "
                            "The 'random' module is not cryptographically secure. "
                            "Use the 'secrets' module for security-sensitive values."
                        ),
                    }
                )
    return issues


def _deduplicate(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []
    for issue in issues:
        key = (issue["line"], issue["message"])
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def _check_secrets_in_source(code: str) -> List[Dict[str, Any]]:
    issues = []
    for label, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(code):
            lineno = code[: match.start()].count("\n") + 1
            issues.append(
                {
                    "severity": "critical",
                    "line": lineno,
                    "message": (
                        f"Possible secret detected ({label}). "
                        "Do not hardcode credentials; use environment variables "
                        "or a secrets manager."
                    ),
                }
            )
    return issues


def _check_path_traversal(code: str) -> List[Dict[str, Any]]:
    issues = []
    # Flag lines that contain a file operation AND a path-traversal sequence
    file_ops = re.compile(r'(open|read|write|os\.path)')
    traversal = re.compile(r'(\.\./|\.\.\\)')
    for lineno, line in enumerate(code.splitlines(), 1):
        if file_ops.search(line) and traversal.search(line):
            issues.append(
                {
                    "severity": "high",
                    "line": lineno,
                    "message": (
                        "Possible path traversal vulnerability. "
                        "Validate and sanitize file paths before use."
                    ),
                }
            )
    return issues


def scan_security(code: str) -> List[Dict[str, Any]]:
    """Run all security checks on *code* and return an issue list."""
    issues: List[Dict[str, Any]] = []
    issues.extend(_check_secrets_in_source(code))
    issues.extend(_check_path_traversal(code))

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    issues.extend(_check_dangerous_builtins(tree))
    issues.extend(_check_sql_injection(tree, code))
    issues.extend(_check_insecure_deserialization(tree))
    issues.extend(_check_subprocess_shell(tree))
    issues.extend(_check_insecure_random(tree))
    return _deduplicate(issues)


def _format_issues(issues: List[Dict[str, Any]]) -> str:
    if not issues:
        return "No security issues detected."
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_issues = sorted(
        issues,
        key=lambda i: (severity_order.get(i["severity"], 99), i["line"]),
    )
    lines = []
    for issue in sorted_issues:
        icon = {
            "critical": "🚨",
            "high": "🔴",
            "medium": "🟡",
            "low": "🔵",
        }.get(issue["severity"], "⚪")
        lines.append(f"{icon} [{issue['severity'].upper()}] Line {issue['line']}: {issue['message']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM-assisted deep analysis (optional)
# ---------------------------------------------------------------------------


def _llm_security_analysis(code: str, rule_summary: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return ""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        system = SystemMessage(
            content=(
                "You are a security engineer performing a code security review. "
                "Identify vulnerabilities including but not limited to: "
                "injection attacks, authentication bypass, insecure data handling, "
                "cryptographic weaknesses, and input validation issues. "
                "Reference relevant CWE or OWASP categories where applicable. "
                "Be concise and actionable."
            )
        )
        human = HumanMessage(
            content=(
                f"Rule-based security findings:\n{rule_summary}\n\n"
                f"Source code:\n```python\n{textwrap.shorten(code, 3000)}\n```\n\n"
                "Provide additional security analysis and recommendations."
            )
        )
        response = llm.invoke([system, human])
        return response.content
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------


def security_agent(state: CodeReviewState) -> dict:
    """LangGraph node: performs security scanning of the code."""
    code = state["code"]

    issues = scan_security(code)
    rule_summary = _format_issues(issues)

    llm_commentary = _llm_security_analysis(code, rule_summary)
    if llm_commentary:
        full = f"{rule_summary}\n\n**Security Commentary (LLM):**\n{llm_commentary}"
    else:
        full = rule_summary

    critical_count = sum(1 for i in issues if i.get("severity") == "critical")
    return {
        "security_issues": full,
        "messages": [
            {
                "role": "assistant",
                "content": (
                    f"[SecurityAgent] Found {len(issues)} security issue(s) "
                    f"({critical_count} critical)."
                ),
            }
        ],
    }
