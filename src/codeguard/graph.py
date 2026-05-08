"""LangGraph workflow for CodeGuard AI.

Pipeline (sequential long-chain reasoning):

    START
      │
      ▼
  structure_agent      ← AST + LLM structural analysis
      │
      ▼
  style_agent          ← Rule-based + LLM style check
      │
      ▼
  security_agent       ← Pattern-based + LLM security scan
      │
      ▼
  summary_agent        ← Markdown report generation
      │
      ▼
    END
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from langgraph.graph import END, START, StateGraph

from .agents import security_agent, structure_agent, style_agent, summary_agent
from .state import CodeReviewState


def build_graph() -> Any:
    """Build and compile the CodeGuard AI review graph."""
    builder = StateGraph(CodeReviewState)

    # Register nodes
    builder.add_node("structure_agent", structure_agent)
    builder.add_node("style_agent", style_agent)
    builder.add_node("security_agent", security_agent)
    builder.add_node("summary_agent", summary_agent)

    # Define sequential edges
    builder.add_edge(START, "structure_agent")
    builder.add_edge("structure_agent", "style_agent")
    builder.add_edge("style_agent", "security_agent")
    builder.add_edge("security_agent", "summary_agent")
    builder.add_edge("summary_agent", END)

    return builder.compile()


def run_review(
    code: str,
    file_path: str = "unknown",
    language: str = "python",
) -> Dict[str, Any]:
    """Run the full CodeGuard AI review pipeline.

    Parameters
    ----------
    code:
        Source code string to review.
    file_path:
        Original file path (used in the report header).
    language:
        Programming language identifier (default: ``"python"``).

    Returns
    -------
    dict
        The final :class:`CodeReviewState` after all agents have run.
        The Markdown report is under the ``"final_report"`` key.
    """
    graph = build_graph()

    initial_state: CodeReviewState = {
        "code": code,
        "file_path": file_path,
        "language": language,
        "structure_analysis": None,
        "style_issues": None,
        "security_issues": None,
        "final_report": None,
        "messages": [],
    }

    result = graph.invoke(initial_state)
    return result
