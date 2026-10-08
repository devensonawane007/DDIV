"""Agent 4 — Recovery Supervisor: Workflow supervision, failure classification, and recovery selection."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

from agents.base import AgentInputMetadata, BaseAgent
from models.base import ModelProvider


class SupervisorDecision(BaseModel):
    should_retry: bool = Field(
        ...,
        description="Whether to attempt a recovery intervention and retry",
    )
    failure_category: Optional[str] = Field(
        default=None,
        description="Classified failure code: F1 (Localization), F2 (Code/Reasoning), F3 (Tool/Execution), F4 (Coordination/Strategy)",
    )
    detected_failure: Optional[str] = Field(
        default=None,
        description="Backward-compatible alias for failure_category",
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="List of specific execution or test evidence supporting this diagnosis",
    )
    root_cause: str = Field(
        default="",
        description="Root cause explaining why the attempt succeeded or failed",
    )
    diagnosis: str = Field(
        default="",
        description="Backward-compatible alias for root_cause",
    )
    intervention: Optional[str] = Field(
        default=None,
        description="Selected recovery strategy: A1 (Localization), A2 (Code/Reasoning), A3 (Execution), A4 (Strategy)",
    )
    recovery_strategy: Optional[str] = Field(
        default=None,
        description="Backward-compatible alias for intervention",
    )
    instructions: str = Field(
        default="",
        description="Specific instructions provided to targeted agent(s) for the next attempt",
    )
    intervention_instructions: str = Field(
        default="",
        description="Backward-compatible alias for instructions",
    )
    avoid_previous_mistake: str = Field(
        default="",
        description="Explicit directive on what mistake or approach must NOT be repeated",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Supervisor confidence in diagnosis and intervention",
    )

    @model_validator(mode="after")
    def enforce_strict_recovery_mapping(self) -> SupervisorDecision:
        """Enforce strict 1-to-1 recovery mapping: F1->A1, F2->A2, F3->A3, F4->A4."""
        # Sync field aliases
        f_cat = self.failure_category or self.detected_failure
        rec_strat = self.intervention or self.recovery_strategy
        diag = self.root_cause or self.diagnosis
        instr = self.instructions or self.intervention_instructions

        mapping = {
            "F1": "A1",
            "F2": "A2",
            "F3": "A3",
            "F4": "A4",
        }

        if f_cat in mapping:
            rec_strat = mapping[f_cat]
        elif rec_strat:
            reverse_map = {v: k for k, v in mapping.items()}
            if rec_strat in reverse_map:
                f_cat = reverse_map[rec_strat]

        self.failure_category = f_cat
        self.detected_failure = f_cat
        self.intervention = rec_strat
        self.recovery_strategy = rec_strat
        self.root_cause = diag
        self.diagnosis = diag
        self.instructions = instr
        self.intervention_instructions = instr
        return self


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
            "FAILURE TAXONOMY & STRICT 1-TO-1 RECOVERY MAPPINGS:\n"
            "- F1 (Localization Failure) -> ALWAYS A1 (Localization Recovery): Wrong file, function, class, or symbol selected. Action: Broaden search, inspect call sites, re-run Locator with failure context.\n"
            "- F2 (Code/Reasoning Failure) -> ALWAYS A2 (Code/Reasoning Recovery): Correct area identified, but patch logic, API usage, edge cases, or arithmetic is wrong; or Coder produced no usable modifications. Action: Pass exact test/failure trace to Coder, inspect APIs, request alternative logic.\n"
            "- F3 (Tool/Patch/Execution Failure) -> ALWAYS A3 (Execution Recovery): Malformed patch diff, apply failure, syntax error, JSON formatting error, or environment crash. Action: Validate/clean unified diff format, retry application, fix tool invocations.\n"
            "- F4 (Coordination/Strategy Failure) -> ALWAYS A4 (Strategy Recovery): Agents repeating the same failed strategy, looping, or reinforcing wrong assumptions. Action: Ban the repeated strategy, inject anti-examples, force alternative approach.\n\n"
            "CRITICAL RULES:\n"
            "1. Ground your diagnosis in objective execution and test evidence.\n"
            "2. NEVER mix failure and strategy codes: F1 MUST ALWAYS map to A1, F2 to A2, F3 to A3, F4 to A4.\n"
            "3. If Objective Failure Detector identified a category, respect that objective finding unless conclusive evidence contradicts it.\n"
            "4. Always specify 'avoid_previous_mistake': a concrete instruction telling the Coder what NOT to repeat.\n"
            "5. If maximum attempts reached or tests pass, set should_retry to false.\n"
            "6. Respond with valid JSON matching the specified schema."
        )

    def build_prompt(self, input_data: Dict[str, Any], metadata: AgentInputMetadata) -> str:
        task_id = input_data.get("task_id", "")
        attempt = metadata.attempt
        max_attempts = input_data.get("max_attempts", 3)
        issue = input_data.get("issue", "")
        locator_summary = input_data.get("locator_summary", "")
        patch_summary = input_data.get("patch_summary", "")
        patch_applied = input_data.get("patch_applied", True)
        test_results = input_data.get("test_results", {})
        objective_detector_result = input_data.get("objective_detector_result", {})
        trust_scores = input_data.get("trust_scores", {})
        memory_matches = input_data.get("memory_matches", [])
        attempt_history = input_data.get("attempt_history", [])

        prompt_parts = [
            f"=== TASK: {task_id} (Attempt {attempt} of {max_attempts}) ===",
            f"=== ISSUE ===\n{issue}\n",
            f"=== LOCATOR SUMMARY ===\n{locator_summary}\n",
            f"=== CANDIDATE PATCH (Applied: {patch_applied}) ===\n{patch_summary}\n",
            f"=== OBJECTIVE FAILURE DETECTOR FINDINGS ===\n{json.dumps(objective_detector_result, indent=2)}\n",
            f"=== TEST / HARNESS EXECUTION RESULTS ===\n{json.dumps(test_results, indent=2)}\n",
            f"=== CURRENT AGENT TRUST SCORES ===\n{json.dumps(trust_scores, indent=2)}\n",
        ]

        if memory_matches:
            prompt_parts.append(f"=== RELEVANT MEMORY MATCHES ===\n{json.dumps(memory_matches, indent=2)}\n")

        if attempt_history:
            prompt_parts.append(f"=== ATTEMPT HISTORY ===\n{json.dumps(attempt_history, indent=2)}\n")

        prompt_parts.append(
            "Diagnose the failure and formulate the recovery intervention.\n"
            "If tests passed completely, set should_retry=false, failure_category=null, intervention=null.\n"
            "If failed and attempt < max_attempts, classify failure (F1, F2, F3, F4), map to intervention (A1, A2, A3, A4), "
            "provide evidence, instructions, and specify avoid_previous_mistake.\n"
            "Output JSON with keys: should_retry, failure_category, evidence, root_cause, intervention, "
            "instructions, avoid_previous_mistake, confidence."
        )

        return "\n".join(prompt_parts)
