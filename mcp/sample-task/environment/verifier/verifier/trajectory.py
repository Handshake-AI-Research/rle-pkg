"""Trajectory parsing utilities for ATIF (Agent Trajectory Interchange Format)."""

from typing import Any

from pydantic import TypeAdapter


def load_trajectory_final_output(path: str) -> str:
    """Load an ATIF trajectory file and extract the final agent message."""
    with open(path) as f:
        data = TypeAdapter(dict[str, Any]).validate_json(f.read())

    steps = data.get("steps", [])

    # Extract final agent message (last agent message without tool calls)
    final_output = ""
    for step in reversed(steps):
        if step.get("source") == "agent" and not step.get("tool_calls"):
            final_output = step.get("message", "")
            break

    return final_output
