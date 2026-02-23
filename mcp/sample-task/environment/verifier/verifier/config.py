import tomllib

from pydantic import BaseModel, Field, TypeAdapter


class MCPServer(BaseModel):
    """Configuration for an MCP server."""

    name: str
    transport: str = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)


class VerifierConfig(BaseModel):
    """Top-level verifier configuration."""

    model: str
    instructions: str
    rubric: str
    workdir: str
    trajectory: str
    sandbox_user: str
    mcp_servers: list[MCPServer] = Field(default_factory=list)
    output_dir: str = "/logs/verifier"
    judge_timeout: int = 300


class RubricItem(BaseModel):
    """A single rubric item with evaluation criteria and weight."""

    criteria: str
    weight: float


class JudgeInput(BaseModel):
    """Input passed to the inner judge."""

    model: str
    instructions: str
    final_output: str
    criteria: str
    workdir: str
    mcp_servers: list[MCPServer]


class Verdict(BaseModel):
    """Judge output."""

    passed: bool
    reasoning: str


class CriteriaResult(BaseModel):
    """Evaluation result for a single criteria."""

    criteria: str
    weight: float
    passed: bool
    reasoning: str


class EvaluationInfo(BaseModel):
    """Evaluation info."""

    score: float
    criteria_results: list[CriteriaResult]


def load_config(path: str) -> VerifierConfig:
    """Load verifier configuration from a TOML file."""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return VerifierConfig.model_validate(data)


def load_rubric(path: str) -> list[RubricItem]:
    """Load rubric items from a JSON file."""
    with open(path) as f:
        return TypeAdapter(list[RubricItem]).validate_json(f.read())
