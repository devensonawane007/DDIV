"""Agent 2 — Coder: Code generation and patch synthesis agent."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agents.base import AgentInputMetadata, BaseAgent
from models.base import ModelProvider


from evaluation.patch_builder import CodeModification


class CoderOutput(BaseModel):
    # Behavioral reasoning contract fields
    behavioral_analysis: Optional[str] = Field(
        default=None,
        description="Reasoning on the required vs current behavioral contract",
    )
    existing_behavior: Optional[str] = Field(
        default=None,
        description="Existing implementation behavior and why it fails",
    )
    smallest_change_plan: Optional[str] = Field(
        default=None,
        description="Plan for the minimal correct code change to avoid regressions",
    )
    regression_risks: List[str] = Field(
        default_factory=list,
        description="Potential side-effects to existing callers or tests",
    )
    # Recovery-specific prior patch critique fields
    previous_patch_problem: Optional[str] = Field(
        default=None,
        description="Technical critique of what was wrong with the previous patch proposal",
    )
    why_it_failed: Optional[str] = Field(
        default=None,
        description="Explanation of why previous attempt failed based on test/supervisor evidence",
    )
    new_approach: Optional[str] = Field(
        default=None,
        description="Distinct new strategy being applied in this attempt",
    )
    # Core modification fields
    modifications: List[CodeModification] = Field(
        default_factory=list,
        description="Structured code modifications anchored on verbatim source code",
    )
    patch: str = Field(
        default="",
        description="Optional unified git diff patch addressing the issue",
    )
    modified_files: List[str] = Field(
        default_factory=list,
        description="List of files modified in the patch",
    )
    reasoning_summary: str = Field(
        default="",
        description="Technical explanation of the repair and changes",
    )
    confidence: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )


class CoderAgent(BaseAgent[CoderOutput]):
    """Agent 2: Analyzes the issue and implements candidate code modifications or patch."""

    def __init__(self, provider: ModelProvider):
        super().__init__(
            agent_id="Coder",
            provider=provider,
            output_schema=CoderOutput,
        )

    def build_system_prompt(self) -> str:
        return (
            "You are the Coder Agent in a multi-agent software repair framework.\n"
            "Your objective is to inspect the issue, behavioral contract, and source code, "
            "then synthesize the smallest correct code modification to resolve the issue.\n\n"
            "MANDATORY REASONING CONTRACT:\n"
            "Before synthesizing code, reason carefully about:\n"
            "1. What behavior does the issue require?\n"
            "2. What behavior currently exists?\n"
            "3. Where is the behavior implemented?\n"
            "4. What tests exercise it?\n"
            "5. What is the SMALLEST correct change?\n"
            "6. What existing behavior must remain unchanged?\n"
            "7. What regression risks exist?\n\n"
            "RECOVERY INSTRUCTIONS (when retrying after failure):\n"
            "- Critique the previous failed patch: do NOT blindly reproduce the same mistake.\n"
            "- Identify why it failed and explain how your new approach differs.\n\n"
            "RULES:\n"
            "1. Specify changes using 'modifications' where each modification has:\n"
            "   - 'path': relative path to target file (e.g. 'src/flask/blueprints.py')\n"
            "   - 'target_symbol': symbol or function name (e.g. 'Blueprint.__init__')\n"
            "   - 'operation': 'insert_after', 'insert_before', 'replace', or 'delete'\n"
            "   - 'anchor': exact unique snippet (2-4 lines) verbatim from the provided source code to anchor the change\n"
            "   - 'code': the code to insert or replace with (with exact Python indentation matching context)\n"
            "   - 'reason': explanation of the change\n"
            "2. Keep changes minimal: prefer exactly ONE structured modification unless multiple are genuinely required.\n"
            "3. Do NOT include markdown code fences within the code or anchor fields.\n"
            "4. Never hallucinate nonexistent APIs or functions.\n"
            "5. Respond with valid JSON matching the specified schema."
        )

    def build_prompt(self, input_data: Dict[str, Any], metadata: AgentInputMetadata) -> str:
        issue = input_data.get("issue", "")
        locator_result = input_data.get("locator_result", {})
        source_files = input_data.get("source_files", "")
        test_understanding = input_data.get("test_understanding", {})
        repo_tests = input_data.get("repo_tests", "")
        previous_attempts = input_data.get("previous_attempts", "")
        previous_patch = input_data.get("previous_patch", "")
        recovery_instructions = input_data.get("recovery_instructions", "")
        avoid_previous_mistake = input_data.get("avoid_previous_mistake", "")

        prompt_parts = [
            f"=== ISSUE DESCRIPTION ===\n{issue}\n",
        ]

        if test_understanding:
            prompt_parts.append(f"=== BEHAVIORAL CONTRACT & ROOT CAUSE ANALYSIS ===\n{json_dumps(test_understanding)}\n")

        if locator_result:
            prompt_parts.append(f"=== LOCATOR ANALYSIS ===\n{json_dumps(locator_result)}\n")

        if source_files:
            prompt_parts.append(f"=== SOURCE CODE IN RELEVANT FILES ===\n{source_files}\n")

        if repo_tests:
            prompt_parts.append(f"=== REPOSITORY TESTS CONTEXT ===\n{repo_tests}\n")

        if previous_patch:
            prompt_parts.append(f"=== PREVIOUS CANDIDATE PATCH (FAILED) ===\n{previous_patch}\n")

        if previous_attempts:
            prompt_parts.append(f"=== PREVIOUS FAILED ATTEMPTS & EVIDENCE ===\n{previous_attempts}\n")

        if recovery_instructions:
            prompt_parts.append(f"=== SUPERVISOR RECOVERY DIRECTIVE ===\n{recovery_instructions}\n")

        if avoid_previous_mistake:
            prompt_parts.append(f"=== WHAT NOT TO REPEAT ===\n{avoid_previous_mistake}\n")

        if metadata.attempt > 1:
            prompt_parts.append(
                "CRITICAL: This is a recovery attempt. Fill in 'previous_patch_problem', 'why_it_failed', "
                "and 'new_approach' before writing the replacement modification.\n"
            )

        prompt_parts.append(
            "Synthesize the smallest correct code modification resolving the issue.\n"
            "Output JSON with keys: behavioral_analysis, existing_behavior, smallest_change_plan, "
            "regression_risks, modifications, patch, modified_files, reasoning_summary, confidence.\n"
            "Under 'modifications', provide structured edits with: path, target_symbol, operation, anchor, code, reason.\n"
            "The 'anchor' MUST be an exact verbatim substring from the source code provided above."
        )

        return "\n".join(prompt_parts)


def json_dumps(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, indent=2)
    except Exception:
        return str(obj)
