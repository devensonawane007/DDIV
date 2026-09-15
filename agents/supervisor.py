"""Agent 4 — Recovery Supervisor: Workflow supervision, failure classification, and recovery selection."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agents.base import AgentInputMetadata, BaseAgent
from models.base import ModelProvider


class SupervisorDecision(BaseModel):
    should_retry: bool = Field(
        ...,
        description="Whether to attempt a recovery intervention and retry",
    )
    detected_failure: Optional[str] = Field(
        None,
        description="Classified failure code: F1 (Localization), F2 (Code/Reasoning), F3 (Tool/Execution), F4 (Coordination/Strategy)",
    )
    diagnosis: str = Field(
        ...,
        description="Root cause diagnosis explaining why the attempt succeeded or failed",
    )
    recovery_strategy: Optional[str] = Field(
        None,
        description="Selected recovery strategy: A1 (Localization), A2 (Code/Reasoning), A3 (Execution), A4 (Strategy)",
    )
    intervention_instructions: str = Field(
        ...,
        description="Specific instructions provided to targeted agent(s) for the next attempt",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Supervisor confidence in diagnosis and intervention",
    )


class SupervisorAgent(BaseAgent[SupervisorDecision]):
    """Agent 4: Supervise the repair process, detect/classify failures, select recovery, and prevent cycles."""

    def __init__(self, provider: ModelProvider):
        super().__init__(
            agent_id="Supervisor",
            provider=provider,
            output_schema=SupervisorDecision,
        )

    def build_system_prompt(self) -> str:
        return (
            "You are the Recovery Supervisor in the DDIV framework.\n"
            "You supervise Locator, Coder, and Tester. You must NEVER blindly trust any agent.\n"
            "You examine execution traces, test outcomes, patch syntax, and agent outputs.\n\n"
            "FAILURE TAXONOMY:\n"
            "- F1 (Localization Failure): Wrong file, function, class, or symbol selected.\n"
            "- F2 (Code/Reasoning Failure): Correct area identified, but patch logic, API usage, or edge-case handling is wrong.\n"
            "- F3 (Tool/Patch/Execution Failure): Malformed patch diff, apply failure, syntax error, or environment crash.\n"
            "- F4 (Coordination/Strategy Failure): Agents repeating the same failed strategy, looping, or reinforcing wrong assumptions.\n\n"
            "TARGETED RECOVERY STRATEGIES:\n"
            "- A1 (Localization Recovery): Broaden search, inspect call sites, re-run Locator with failure context.\n"
            "- A2 (Code/Reasoning Recovery): Pass exact test failure trace to Coder, inspect APIs, request alternative logic.\n"
            "- A3 (Execution Recovery): Validate/clean unified diff format, retry application, fix tool invocations.\n"
            "- A4 (Strategy/Coordination Recovery): Ban the repeated strategy, inject anti-examples, force alternative approach.\n\n"
            "RULES:\n"
            "1. Ground your diagnosis in objective execution and test evidence.\n"
            "2. Trust scores are decision-support only; test results always take precedence.\n"
            "3. If maximum attempts reached or tests pass, set should_retry to false.\n"
            "4. Respond with valid JSON matching the specified schema."
        )

    def build_prompt(self, input_data: Dict[str, Any], metadata: AgentInputMetadata) -> str:
        task_id = input_data.get("task_id", "")
        attempt = metadata.attempt
        max_attempts = input_data.get("max_attempts", 4)
        issue = input_data.get("issue", "")
        locator_summary = input_data.get("locator_summary", "")
        patch_summary = input_data.get("patch_summary", "")
        patch_applied = input_data.get("patch_applied", True)
        test_results = input_data.get("test_results", {})
        deterministic_hints = input_data.get("deterministic_hints", [])
        trust_scores = input_data.get("trust_scores", {})
        memory_matches = input_data.get("memory_matches", [])
        attempt_history = input_data.get("attempt_history", [])

        prompt_parts = [
            f"=== TASK: {task_id} (Attempt {attempt} of {max_attempts}) ===",
            f"=== ISSUE ===\n{issue}\n",
            f"=== LOCATOR SUMMARY ===\n{locator_summary}\n",
            f"=== CANDIDATE PATCH (Applied: {patch_applied}) ===\n{patch_summary}\n",
            f"=== TEST / HARNESS EXECUTION RESULTS ===\n{json.dumps(test_results, indent=2)}\n",
            f"=== DETERMINISTIC FAILURE HINTS ===\n{json.dumps(deterministic_hints, indent=2)}\n",
            f"=== CURRENT AGENT TRUST SCORES ===\n{json.dumps(trust_scores, indent=2)}\n",
        ]

        if memory_matches:
            prompt_parts.append(f"=== RELEVANT MEMORY MATCHES ===\n{json.dumps(memory_matches, indent=2)}\n")

        if attempt_history:
            prompt_parts.append(f"=== ATTEMPT HISTORY ===\n{json.dumps(attempt_history, indent=2)}\n")

        prompt_parts.append(
            "Diagnose the outcome. If tests passed completely, set should_retry=false, detected_failure=null, recovery_strategy=null.\n"
            "If failed and attempt < max_attempts, classify failure (F1, F2, F3, F4), choose strategy (A1, A2, A3, A4), and write specific intervention instructions.\n"
            "Output JSON with keys: should_retry, detected_failure, diagnosis, recovery_strategy, intervention_instructions, confidence."
        )

        return "\n".join(prompt_parts)
