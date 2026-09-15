"""Agent 2 — Coder: Code generation and patch synthesis agent."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agents.base import AgentInputMetadata, BaseAgent
from models.base import ModelProvider


class CoderOutput(BaseModel):
    patch: str = Field(
        ...,
        description="Unified git diff patch addressing the issue",
    )
    modified_files: List[str] = Field(
        default_factory=list,
        description="List of files modified in the patch",
    )
    reasoning_summary: str = Field(
        ...,
        description="Technical explanation of the repair and changes",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )


class CoderAgent(BaseAgent[CoderOutput]):
    """Agent 2: Analyzes the issue and implements candidate unified diff patch."""

    def __init__(self, provider: ModelProvider):
        super().__init__(
            agent_id="Coder",
            provider=provider,
            output_schema=CoderOutput,
        )

    def build_system_prompt() -> str:
        return (
            "You are the Coder Agent in a multi-agent software repair framework.\n"
            "Your objective is to inspect the issue, localized files, and source code, "
            "then generate a clean, precise unified diff patch (git diff format) to resolve the issue.\n"
            "Rules:\n"
            "1. Generate a valid unified diff with standard headers (--- a/path +++ b/path @@ ... @@).\n"
            "2. Only modify files identified as relevant.\n"
            "3. Do NOT include extraneous markdown fences inside the 'patch' field itself.\n"
            "4. Never hallucinate nonexistent APIs or functions.\n"
            "5. Respond with valid JSON matching the specified schema."
        )

    def build_system_prompt(self) -> str:
        return (
            "You are the Coder Agent in a multi-agent software repair framework.\n"
            "Your objective is to inspect the issue, localized files, and source code, "
            "then generate a clean, precise unified diff patch (git diff format) to resolve the issue.\n"
            "Rules:\n"
            "1. Generate a valid unified diff with standard headers (--- a/path +++ b/path @@ ... @@).\n"
            "2. Only modify files identified as relevant.\n"
            "3. Do NOT include extraneous markdown fences inside the 'patch' field itself.\n"
            "4. Never hallucinate nonexistent APIs or functions.\n"
            "5. Respond with valid JSON matching the specified schema."
        )

    def build_prompt(self, input_data: Dict[str, Any], metadata: AgentInputMetadata) -> str:
        issue = input_data.get("issue", "")
        locator_result = input_data.get("locator_result", {})
        source_files = input_data.get("source_files", "")
        previous_attempts = input_data.get("previous_attempts", "")
        recovery_instructions = input_data.get("recovery_instructions", "")

        prompt_parts = [
            f"=== ISSUE DESCRIPTION ===\n{issue}\n",
            f"=== LOCATOR ANALYSIS ===\n{json_dumps(locator_result)}\n",
        ]

        if source_files:
            prompt_parts.append(f"=== SOURCE CODE IN RELEVANT FILES ===\n{source_files}\n")

        if previous_attempts:
            prompt_parts.append(f"=== PREVIOUS FAILED ATTEMPTS & FEEDBACK ===\n{previous_attempts}\n")

        if recovery_instructions:
            prompt_parts.append(f"=== RECOVERY INSTRUCTIONS (SUPERVISOR DIRECTIVE) ===\n{recovery_instructions}\n")

        prompt_parts.append(
            "Synthesize a complete unified diff patch resolving the issue.\n"
            "Output JSON with keys: patch, modified_files, reasoning_summary, confidence."
        )

        return "\n".join(prompt_parts)


def json_dumps(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, indent=2)
    except Exception:
        return str(obj)
