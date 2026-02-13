"""Inner judge: evaluates a single rubric criteria using an OpenHands agent.

This script is invoked as the sandbox user from the outer verifier orchestrator.
It receives all context via an input JSON file and writes its verdict to an
output JSON file.
"""

import argparse
import contextlib
import os
import tempfile
from typing import Any

from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool
from pydantic import ValidationError

from verifier.config import JudgeInput, Verdict


def build_judge_prompt(
    instructions: str,
    final_output: str,
    criteria: str,
    verdict_path: str,
) -> str:
    """Build the full prompt for the judge agent."""
    return f"""\
You are an expert judge evaluating whether an AI agent successfully completed a task \
according to a specific evaluation criteria. You have access to the agent's working \
directory and can inspect files, run commands, and use tools to investigate.

## Task Instructions (given to the agent)
{instructions}

## Agent's Final Output
{final_output}

## Evaluation Criteria
{criteria}

## Your Task
Investigate the current state of the environment to determine whether the above \
criteria is satisfied. Use the available tools to read files, run commands, and \
inspect the environment as needed.

After your investigation, you MUST write your verdict as a JSON object to:
  {verdict_path}

The JSON object must have exactly two fields:
- "passed": true if the criteria is satisfied, false otherwise
- "reasoning": a brief explanation of your judgment

Example:
```json
{{"passed": true, "reasoning": "The file foo.txt exists and contains the expected content."}}
```

Write ONLY valid JSON to that file, with no additional text."""


def _read_verdict(verdict_path: str) -> Verdict:
    """Read and validate the verdict file written by the judge agent."""
    try:
        with open(verdict_path) as f:
            content = f.read().strip()
    except FileNotFoundError:
        return Verdict(passed=False, reasoning="Judge agent did not write a verdict file.")
    if not content:
        return Verdict(passed=False, reasoning="Judge agent wrote an empty verdict file.")
    try:
        return Verdict.model_validate_json(content)
    except ValidationError as e:
        return Verdict(passed=False, reasoning=f"Invalid verdict: {e}")


def run_judge(input_path: str, output_path: str) -> None:
    """Run the agent-as-judge for a single rubric criteria."""
    with open(input_path) as f:
        judge_input = JudgeInput.model_validate_json(f.read())

    model = judge_input.model
    instructions = judge_input.instructions
    final_output = judge_input.final_output
    criteria = judge_input.criteria
    workdir = judge_input.workdir
    mcp_servers = judge_input.mcp_servers

    # Temp path for the agent to create and write its verdict
    verdict_path = tempfile.mktemp(suffix=".json", prefix="verdict_", dir="/tmp")

    prompt = build_judge_prompt(
        instructions=instructions,
        final_output=final_output,
        criteria=criteria,
        verdict_path=verdict_path,
    )

    try:
        llm = LLM(
            model=model,
            api_key=os.environ.get("LLM_API_KEY"),
            base_url=os.environ.get("LLM_BASE_URL"),
        )

        tools = [
            Tool(name=TerminalTool.name),
            Tool(name=FileEditorTool.name),
        ]

        # Build MCP config if servers are configured
        mcp_config: dict[str, Any] = {"mcpServers": {}}
        for mcp in mcp_servers:
            server_name = mcp.name
            server_cfg: dict[str, Any] = {"command": mcp.command}
            if mcp.args:
                server_cfg["args"] = mcp.args
            mcp_config["mcpServers"][server_name] = server_cfg

        agent = Agent(llm=llm, tools=tools, mcp_config=mcp_config or {})
        conversation = Conversation(agent=agent, workspace=workdir)
        conversation.send_message(prompt)  # type: ignore[attr-defined]
        conversation.run()  # type: ignore[attr-defined]

        # Read the verdict file the agent should have written
        verdict = _read_verdict(verdict_path)

    except Exception as e:
        verdict = Verdict(passed=False, reasoning=f"Judge execution error: {e}")
    finally:
        with contextlib.suppress(OSError):
            os.unlink(verdict_path)

    # Write the final output
    with open(output_path, "w") as f:
        f.write(verdict.model_dump_json())


def main() -> None:
    parser = argparse.ArgumentParser(description="Judge a single rubric criteria")
    parser.add_argument("--input", required=True, help="Path to judge input JSON")
    parser.add_argument("--output", required=True, help="Path to write judge output JSON")
    args = parser.parse_args()

    run_judge(args.input, args.output)


if __name__ == "__main__":
    main()
