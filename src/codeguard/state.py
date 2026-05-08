"""Shared state model for the CodeGuard AI review pipeline."""

from typing import Annotated, List, Optional
from typing_extensions import TypedDict
import operator


class CodeReviewState(TypedDict):
    """State that flows through every node in the LangGraph pipeline."""

    # ── Input ──────────────────────────────────────────────────────────────
    code: str                          # Raw source code to review
    file_path: str                     # Original file path (for context)
    language: str                      # e.g. "python", "javascript"

    # ── Agent outputs ──────────────────────────────────────────────────────
    structure_analysis: Optional[str]  # Findings from StructureAgent
    style_issues: Optional[str]        # Findings from StyleAgent
    security_issues: Optional[str]     # Findings from SecurityAgent
    final_report: Optional[str]        # Markdown report from SummaryAgent

    # ── Accumulated chat messages (for long-chain reasoning) ───────────────
    messages: Annotated[List[dict], operator.add]
