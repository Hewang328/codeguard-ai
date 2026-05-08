#!/usr/bin/env python3
"""CodeGuard AI – CLI entry point.

Usage
-----
Review a single file::

    python main.py path/to/file.py

Review code passed via stdin::

    cat myfile.py | python main.py --stdin

Output the Markdown report to a file::

    python main.py path/to/file.py --output report.md

Print the raw report to stdout (default)::

    python main.py path/to/file.py --print
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.codeguard import run_review

# ---------------------------------------------------------------------------
# Language detection helpers
# ---------------------------------------------------------------------------

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
    ".cs": "csharp",
    ".php": "php",
}


def detect_language(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    return _EXT_TO_LANG.get(suffix, "unknown")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="codeguard",
        description="CodeGuard AI – multi-agent code review system",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Path to the source file to review",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read source code from stdin",
    )
    parser.add_argument(
        "--language",
        "-l",
        default=None,
        help="Override language detection (e.g. python, javascript)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Write Markdown report to this file path",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress stdout output (only write to --output file)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Determine source and file path
    if args.stdin:
        code = sys.stdin.read()
        file_path = "<stdin>"
        language = args.language or "python"
    elif args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"Error: file '{args.file}' not found.", file=sys.stderr)
            return 1
        code = path.read_text(encoding="utf-8")
        file_path = str(path)
        language = args.language or detect_language(file_path)
    else:
        print("Error: provide a file path or use --stdin.", file=sys.stderr)
        return 1

    if not code.strip():
        print("Error: input code is empty.", file=sys.stderr)
        return 1

    # Run the review pipeline
    print(f"🔍 CodeGuard AI – reviewing '{file_path}' ...", file=sys.stderr)
    result = run_review(code=code, file_path=file_path, language=language)

    report: str = result.get("final_report") or "_(no report generated)_"

    # Output
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(report, encoding="utf-8")
        print(f"✅ Report written to '{out_path}'", file=sys.stderr)

    if not args.quiet:
        print(report)

    # Return non-zero exit code if any security issues were found
    security_issues: str = result.get("security_issues") or ""
    if "🚨" in security_issues or "[CRITICAL]" in security_issues:
        return 2  # critical issues
    if "🔴" in security_issues or "[HIGH]" in security_issues:
        return 1  # high-severity issues
    return 0


if __name__ == "__main__":
    sys.exit(main())
