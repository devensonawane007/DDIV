"""Agent: Non-blocking Patch Critic Agent.

Evaluates patch plausibility, regression risk, scope, and semantic alignment
before objective execution. Records diagnostic advisory data without blocking
or short-circuiting real SWE-bench evaluation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agents.base import AgentInputMetadata, BaseAgent
from models.base import ModelProvider


class PatchCriticOutput(BaseModel):
    """Structured evaluation from the Patch Critic."""

    approved: bool = Field(
        ...,
        description="Whether the patch appears plausible, safe, and aligned with the problem",
    )
    risk_level: str = Field(
        ...,
        description="Risk level: 'LOW', 'MEDIUM', or 'HIGH'",
    )
    concerns: List[str] = Field(
        default_factory=list,
        description="Identified risks, regressions, potential side-effects, or incomplete logic",
    )
    recommended_changes: List[str] = Field(
        default_factory=list,
        description="Concrete advisory suggestions for improving the patch if needed",
    )
    reasoning: str = Field(
        ...,
        description="Detailed explanation of the critique and assessment",
    )


class PatchCriticAgent(BaseAgent[PatchCriticOutput]):
    """Non-blocking Patch Critic Agent."""

    def __init__(self, provider: ModelProvider):
        super().__init__(
            agent_id="PatchCritic",
            provider=provider,
            output_schema=PatchCriticOutput,
        )

    def build_system_prompt(self) -> str:
        return (
            "You are the Patch Critic Agent in the DDIV software repair framework.\n"
            "Your role is to inspect candidate patches BEFORE they are tested, evaluating:\n"
            "1. Problem alignment: Does the patch address the actual issue described?\n"
            "2. Scope & cleanliness: Does it make unnecessary changes or touch unrelated files?\n"
            "3. Regression risk: Could this break existing callers, type assumptions, or API contracts?\n"
            "4. Plausibility: Is it a genuine semantic fix or a superficial band-aid/hack?\n\n"
            "IMPORTANT: Your evaluation is advisory. Be rigorous, honest, and constructive.\n"
            "Respond strictly in valid JSON matching the schema."
        )

    def build_prompt(self, input_data: Dict[str, Any], metadata: AgentInputMetadata) -> str:
        issue = input_data.get("issue", "")
        patch_text = input_data.get("patch_text", "")
        changed_files = input_data.get("changed_files", [])
        rca = input_data.get("root_cause_analysis", "")
        prior_failure = input_data.get("prior_failure", "")

        parts = [
            f"=== ISSUE STATEMENT ===\n{issue}\n",
        ]

        if rca:
            parts.append(f"=== ROOT CAUSE / BEHAVIORAL CONTRACT ===\n{rca}\n")

        if changed_files:
            parts.append(f"=== CHANGED FILES ===\n{', '.join(changed_files)}\n")

        parts.append(f"=== CANDIDATE PATCH ===\n{patch_text}\n")

        if prior_failure:
            parts.append(f"=== PREVIOUS ATTEMPT FAILURE (IF ANY) ===\n{prior_failure}\n")

        parts.append(
            "Critique this candidate patch.\n"
            "Output JSON with keys: approved (bool), risk_level ('LOW'/'MEDIUM'/'HIGH'), "
            "concerns (list of str), recommended_changes (list of str), reasoning (str)."
        )

        return "\n".join(parts)
