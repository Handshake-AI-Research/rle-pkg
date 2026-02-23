import fcntl
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

mcp = FastMCP("mcp-server")

# Private data (read/write), not exposed directly to the agent user (only through MCP tools).
DATA_DIR = Path(__file__).resolve().parent / "data"

# The setuid wrapper preserves the real UID of the caller, so we can use it
# to determine who launched this MCP server process.
AGENT_UID = 10001
VERIFIER_UID = 10002
SANDBOX_UID = 10003
_caller_uid = os.getuid()

WORKSPACE = Path("/home/agent/workspace")


def write_tool[F: Callable[..., Any]](func: F) -> F:
    """Register a tool that is only visible to the agent (not verifier/sandbox).

    Write tools perform mutations and should not be accessible during
    verification, so they are hidden from verifier and sandbox users.
    """
    if _caller_uid not in (VERIFIER_UID, SANDBOX_UID):
        return mcp.tool()(func)  # type: ignore[return-value]
    return func


def verifier_tool[F: Callable[..., Any]](func: F) -> F:
    """Register a tool that is only visible to verifier/sandbox users.

    These tools let the verifier query internal environment state that the
    agent should not be able to observe directly.
    """
    if _caller_uid in (VERIFIER_UID, SANDBOX_UID):
        return mcp.tool()(func)  # type: ignore[return-value]
    return func


@write_tool
def magic(download_path: str) -> str:
    """Download a magic word to the given path.

    Args:
        download_path: Path to write the magic word to. Can be an absolute path
            or a path relative to the workspace. Must be within the workspace.
    """
    target = Path(download_path)
    if not target.is_absolute():
        target = WORKSPACE / target
    target = target.resolve()
    if not str(target).startswith(str(WORKSPACE) + "/") and target != WORKSPACE:
        raise ToolError("Path must be within the workspace")
    target.parent.mkdir(parents=True, exist_ok=True)
    # agent user cannot access this data directly
    secret = (DATA_DIR / "secret.txt").read_text().splitlines()[0]
    target.write_text(secret + "\n")
    return f"downloaded to {target}"


LOCK_FILE = DATA_DIR / ".poke.lock"


# This tool demonstrates how MCP tools can use locking to be logically atomic
@write_tool
def poke() -> str:
    """Poke the environment."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            (DATA_DIR / "poke_called").write_text("1")
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
    return "poked"


@verifier_tool
def check_poke_called() -> bool:
    """Check whether the poke tool was called."""
    return (DATA_DIR / "poke_called").exists()


if __name__ == "__main__":
    mcp.run(transport="stdio")
