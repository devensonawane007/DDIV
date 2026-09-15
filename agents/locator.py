"""Agent 1 — Locator: Fault localization agent."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agents.base import AgentInputMetadata, BaseAgent
from models.base import ModelProvider


class LocatorOutput(BaseModel):
    relevant_files: List[str] = Field(
        default_factory=list,
        description="List of relevant repository files for the issue",
    )
    relevant_symbols: List[str] = Field(
        default_factory=list,
        description="List of relevant functions, classes, or symbols",
    )
    reasoning_summary: str = Field(
        ...,
        description="Summary of why these locations and symbols are relevant",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )


class LocatorAgent(BaseAgent[LocatorOutput]):
    """Agent 1: Identifies the most relevant repository files, classes, functions, and symbols."""

    def __init__(self, provider: ModelProvider):
        super().__init__(
            agent_id="Locator",
            provider=provider,
            output_schema=LocatorOutput,
        )

    def build_system_prompt(self) -> str:
        return (
            "You are the Locator Agent in a multi-agent software repair framework.\n"
            "Your objective is to accurately identify the repository files, classes, functions, "
            "and symbols directly related to the reported issue.\n"
            "Be precise and avoid nominating unrelated files. "
            "You must respond with valid JSON matching the specified schema."
        )

    def build_prompt(self, input_data: Dict[str, Any], metadata: AgentInputMetadata) -> str:
        issue = input_data.get("issue", "")
        repo_structure = input_data.get("repo_structure", "")
        source_context = input_data.get("source_context", "")
        memory_context = input_data.get("memory_context", "")
        recovery_guidance = input_data.get("recovery_guidance", "")

        prompt_parts = [
            f"=== ISSUE DESCRIPTION ===\n{issue}\n",
        ]

        if repo_structure:
            prompt_parts.append(f"=== REPOSITORY STRUCTURE ===\n{repo_structure}\n")

        if source_context:
            prompt_parts.append(f"=== SOURCE CODE CONTEXT ===\n{source_context}\n")

        if memory_context:
            prompt_parts.append(f"=== HISTORICAL MEMORY (PRIOR SIMILAR ISSUES) ===\n{memory_context}\n")

        if recovery_guidance:
            prompt_parts.append(f"=== RECOVERY INTERVENTION GUIDANCE (A1) ===\n{recovery_guidance}\n")

        prompt_parts.append(
            "Identify the relevant files and symbols that require modification or investigation to resolve the issue.\n"
            "Output JSON with keys: relevant_files, relevant_symbols, reasoning_summary, confidence."
        )

        return "\n".join(prompt_parts)
