"""Agent 1.5 — Test Understanding & Root Cause Analysis Agent.

Performs behavioral contract deduction and root cause analysis prior to patch synthesis.
Informs the Coder agent without leaking evaluator ground truth.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agents.base import AgentInputMetadata, BaseAgent
from models.base import ModelProvider


class RootCauseAnalysis(BaseModel):
    """Structured behavioral contract and root cause analysis."""

    root_cause: str = Field(
        ...,
        description="Core technical reason for the issue in the codebase",
    )
    behavioral_contract: str = Field(
        ...,
        description="The behavioral contract that the software component must fulfill",
    )
    expected_behavior: str = Field(
        ...,
        description="Expected behavior as stated or implied by the issue specification",
    )
    current_behavior: str = Field(
        ...,
        description="Current incorrect behavior or failure mode",
    )
    relevant_symbols: List[str] = Field(
        default_factory=list,
        description="Symbols, classes, or functions directly related to the fix",
    )
    relevant_tests: List[str] = Field(
        default_factory=list,
        description="Repository test cases or test patterns that exercise this behavior",
    )
    required_change: str = Field(
        ...,
        description="Concise description of the semantic modification required",
    )
    regression_risks: List[str] = Field(
        default_factory=list,
        description="Potential regressions, caller side-effects, or edge cases to safeguard against",
    )


class TestUnderstandingAgent(BaseAgent[RootCauseAnalysis]):
    """Agent 1.5: Pre-repair behavioral analysis and contract formulation."""

    def __init__(self, provider: ModelProvider):
        super().__init__(
            agent_id="TestUnderstanding",
            provider=provider,
            output_schema=RootCauseAnalysis,
        )

    def build_system_prompt(self) -> str:
        return (
            "You are the Test Understanding & Root Cause Analysis Agent in the DDIV software repair framework.\n"
            "Your objective is to analyze the issue statement, located source code, and repository tests "
            "to deduce the exact behavioral contract and root cause BEFORE any code editing occurs.\n\n"
            "Rules:\n"
            "1. Focus on the behavioural contract: what is expected vs. what currently occurs.\n"
            "2. Identify specific functions, classes, and edge cases involved.\n"
            "3. Enumerate concrete regression risks: what existing behavior must not be broken?\n"
            "4. Base your analysis strictly on the provided issue and repository code.\n"
            "5. Respond with valid JSON matching the specified schema."
        )

    def build_prompt(self, input_data: Dict[str, Any], metadata: AgentInputMetadata) -> str:
        issue = input_data.get("issue", "")
        located_symbols = input_data.get("located_symbols", [])
        source_code = input_data.get("source_code", "")
        repo_tests = input_data.get("repo_tests", "")
        prior_failure_evidence = input_data.get("prior_failure_evidence", "")

        prompt_parts = [
            f"=== ISSUE STATEMENT ===\n{issue}\n",
        ]

        if located_symbols:
            prompt_parts.append(f"=== LOCATED SYMBOLS ===\n{', '.join(located_symbols)}\n")

        if source_code:
            prompt_parts.append(f"=== SOURCE CODE CONTEXT ===\n{source_code}\n")

        if repo_tests:
            prompt_parts.append(f"=== REPOSITORY TEST EXAMPLES ===\n{repo_tests}\n")

        if prior_failure_evidence:
            prompt_parts.append(f"=== PRIOR EXECUTION FAILURE EVIDENCE ===\n{prior_failure_evidence}\n")

        prompt_parts.append(
            "Perform root cause analysis and formulate the behavioral contract.\n"
            "Output JSON with keys: root_cause, behavioral_contract, expected_behavior, "
            "current_behavior, relevant_symbols, relevant_tests, required_change, regression_risks."
        )

        return "\n".join(prompt_parts)
