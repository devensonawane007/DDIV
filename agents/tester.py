"""Agent 3 — Tester: Test review, regression analysis, and test recommendation agent."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agents.base import AgentInputMetadata, BaseAgent
from models.base import ModelProvider


class TesterOutput(BaseModel):
    assessment: str = Field(
        ...,
        description="Critical technical assessment of the candidate patch",
    )
    suspected_failures: List[str] = Field(
        default_factory=list,
        description="Potential regressions, unhandled edge cases, or suspected failure scenarios",
    )
    recommended_tests: List[str] = Field(
        default_factory=list,
        description="Recommended test cases, test functions, or validation commands to run",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )


class TesterAgent(BaseAgent[TesterOutput]):
    """Agent 3: Reviews candidate patch, identifies likely regressions, and recommends tests."""

    def __init__(self, provider: ModelProvider):
        super().__init__(
            agent_id="Tester",
            provider=provider,
            output_schema=TesterOutput,
        )

    def build_system_prompt(self) -> str:
        return (
            "You are the Tester Agent in a multi-agent software repair framework.\n"
            "Your objective is to critically review the candidate patch against the issue requirements.\n"
            "Identify likely regressions, unhandled edge cases, and recommend exact tests that should be executed.\n"
            "Be rigorous and adversarial to avoid false confidence.\n"
            "Respond with valid JSON matching the specified schema."
        )

    def build_prompt(self, input_data: Dict[str, Any], metadata: AgentInputMetadata) -> str:
        issue = input_data.get("issue", "")
        candidate_patch = input_data.get("candidate_patch", "")
        relevant_code = input_data.get("relevant_code", "")
        existing_tests = input_data.get("existing_tests", "")
        previous_execution = input_data.get("previous_execution", "")

        prompt_parts = [
            f"=== ISSUE DESCRIPTION ===\n{issue}\n",
            f"=== CANDIDATE PATCH ===\n{candidate_patch}\n",
        ]

        if relevant_code:
            prompt_parts.append(f"=== RELEVANT CODE CONTEXT ===\n{relevant_code}\n")

        if existing_tests:
            prompt_parts.append(f"=== REPOSITORY TESTS ===\n{existing_tests}\n")

        if previous_execution:
            prompt_parts.append(f"=== PREVIOUS EXECUTION RESULTS ===\n{previous_execution}\n")

        prompt_parts.append(
            "Review the patch carefully. Identify suspected regressions and recommend validation tests.\n"
            "Output JSON with keys: assessment, suspected_failures, recommended_tests, confidence."
        )

        return "\n".join(prompt_parts)
