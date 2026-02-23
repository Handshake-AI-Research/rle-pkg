"""Outer verifier orchestrator.

Runs as the verifier user. For each rubric item, spawns the inner judge as the
sandbox user to evaluate the criteria using an OpenHands agent-as-judge.

Produces:
    - /logs/verifier/reward.txt   - Harbor-format reward
    - /logs/verifier/info.json    - Per-criteria results
"""

import argparse
import contextlib
import os
import shutil
import subprocess
import tempfile

from pydantic import ValidationError

from verifier.config import (
    CriteriaResult,
    EvaluationInfo,
    JudgeInput,
    Verdict,
    load_config,
    load_rubric,
)
from verifier.trajectory import load_trajectory_final_output


def _clone_workspace(src: str) -> str:
    """Clone the workspace into a temp directory accessible to the sandbox user.

    This isolates individual criteria evaluations from each other.

    Returns the path to the cloned directory.
    """
    clone_dir = tempfile.mkdtemp(prefix="judge_workspace_", dir="/tmp")
    shutil.copytree(src, clone_dir, dirs_exist_ok=True)
    # Group-writable so the sandbox user can use this copy
    for dirpath, _, filenames in os.walk(clone_dir):
        os.chmod(dirpath, os.stat(dirpath).st_mode | 0o070)
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            os.chmod(fpath, os.stat(fpath).st_mode | 0o060)
    return clone_dir


def evaluate_criteria(
    judge_input: JudgeInput,
    sandbox_user: str,
    trace_path: str,
    timeout: int = 300,
) -> Verdict:
    """Run the inner judge as the sandbox user for a single criteria.

    Args:
        judge_input: All context needed by the judge.
        sandbox_user: Username to run the judge process as.
        trace_path: Path to write the judge's stdout/stderr trace.
        timeout: Max seconds to wait for the judge to complete.

    Returns:
        Verdict with 'passed' and 'reasoning'.
    """
    # Clone the workspace so the sandbox user operates on an isolated,
    # read-only copy rather than the agent's original workspace.
    try:
        clone_dir = _clone_workspace(judge_input.workdir)
    except Exception as e:
        return Verdict(passed=False, reasoning=f"Failed to clone workspace: {e}")

    judge_input = judge_input.model_copy(update={"workdir": clone_dir})

    # Write judge input to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="judge_input_",
        dir="/tmp",
        delete=False,
    ) as input_f:
        input_f.write(judge_input.model_dump_json())
        input_path = input_f.name

    output_path = tempfile.mktemp(suffix=".json", prefix="judge_output_", dir="/tmp")

    try:
        # Make input file readable by sandbox user
        os.chmod(input_path, 0o644)

        # Pass all environment variables through sudo (except HOME)
        env_vars = [f"{k}={v}" for k, v in os.environ.items() if k != "HOME"]

        cmd = [
            "sudo",
            "-u",
            sandbox_user,
            "env",
            *env_vars,
            "verifier-judge",
            "--input",
            input_path,
            "--output",
            output_path,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=clone_dir,
        )

        # Save the judge trace (stdout + stderr)
        _save_trace(trace_path, result.stdout, result.stderr, result.returncode)

        if result.returncode != 0:
            return Verdict(
                passed=False,
                reasoning=(f"Judge process failed (exit {result.returncode}): {result.stderr[:500]}"),
            )

        # Read judge output
        with open(output_path) as f:
            return Verdict.model_validate_json(f.read())

    except subprocess.TimeoutExpired:
        _save_trace(trace_path, "", "Judge execution timed out.", -1)
        return Verdict(passed=False, reasoning="Judge execution timed out.")
    except (FileNotFoundError, ValidationError) as e:
        return Verdict(passed=False, reasoning=f"Failed to read judge output: {e}")
    finally:
        shutil.rmtree(clone_dir, ignore_errors=True)
        for path in (input_path, output_path):
            with contextlib.suppress(OSError):
                os.unlink(path)


def _save_trace(trace_path: str, stdout: str, stderr: str, returncode: int) -> None:
    """Write the judge's stdout/stderr to a trace file."""
    try:
        with open(trace_path, "w") as f:
            f.write(f"exit_code: {returncode}\n")
            f.write("=== stdout ===\n")
            f.write(stdout)
            f.write("\n=== stderr ===\n")
            f.write(stderr)
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifier: evaluate agent output via agent-as-judge")
    parser.add_argument("--config", required=True, help="Path to verifier config TOML file")
    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)
    rubric = load_rubric(config.rubric)
    final_output = load_trajectory_final_output(config.trajectory)

    os.makedirs(config.output_dir, exist_ok=True)

    # Evaluate each rubric item sequentially
    results = []
    for i, item in enumerate(rubric):
        print(f"[{i + 1}/{len(rubric)}] Evaluating: {item.criteria[:80]}...")

        judge_input = JudgeInput(
            model=config.model,
            instructions=config.instructions,
            final_output=final_output,
            criteria=item.criteria,
            workdir=config.workdir,
            mcp_servers=config.mcp_servers,
        )

        trace_path = os.path.join(config.output_dir, f"judge_trace_{i}.txt")
        verdict = evaluate_criteria(
            judge_input,
            sandbox_user=config.sandbox_user,
            trace_path=trace_path,
            timeout=config.judge_timeout,
        )

        result = CriteriaResult(
            criteria=item.criteria,
            weight=item.weight,
            passed=verdict.passed,
            reasoning=verdict.reasoning,
        )
        results.append(result)

        status = "PASS" if result.passed else "FAIL"
        print(f"  -> {status}: {result.reasoning[:120]}")

    # Compute weighted score (normalized so 1.0 = all criteria pass)
    total_weight = sum(r.weight for r in results)
    score = sum(r.weight * (1.0 if r.passed else 0.0) for r in results) / total_weight if total_weight > 0 else 0.0
    score = round(score, 4)

    # Write reward.txt (Harbor format: single float)
    with open(os.path.join(config.output_dir, "reward.txt"), "w") as f:
        f.write(str(score))

    # Write info.json (detailed per-criteria results)
    info = EvaluationInfo(score=score, criteria_results=results)
    with open(os.path.join(config.output_dir, "info.json"), "w") as f:
        f.write(info.model_dump_json(indent=2))

    print(f"\nScore: {score}")
    print(f"Results written to {config.output_dir}/")


if __name__ == "__main__":
    main()
