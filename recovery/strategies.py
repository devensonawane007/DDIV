"""Targeted recovery intervention strategies (A1, A2, A3, A4)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from recovery.failure_detector import FailureType


class RecoveryStrategy(str, Enum):
    A1 = "A1"  # Localization Recovery
    A2 = "A2"  # Code/Reasoning Recovery
    A3 = "A3"  # Execution Recovery
    A4 = "A4"  # Strategy/Coordination Recovery


class RecoveryAction(BaseModel):
    strategy: RecoveryStrategy
    target_agent: str  # "Locator", "Coder", "PatchManager", etc.
    rerun_locator: bool = False
    rerun_coder: bool = True
    guidance_for_coder: str = ""
    guidance_for_locator: str = ""
    extra_context: Dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class StrategySelector:
    """Selects and parameterizes targeted recovery interventions based on diagnosis."""

    @staticmethod
    def map_failure_to_strategy(failure_type: FailureType) -> RecoveryStrategy:
        mapping = {
            FailureType.F1: RecoveryStrategy.A1,
            FailureType.F2: RecoveryStrategy.A2,
            FailureType.F3: RecoveryStrategy.A3,
            FailureType.F4: RecoveryStrategy.A4,
        }
        return mapping.get(failure_type, RecoveryStrategy.A2)

    @classmethod
    def build_action(
        cls,
        strategy: RecoveryStrategy,
        diagnosis_text: str,
        test_output: str = "",
        previous_patch: str = "",
        located_files: Optional[List[str]] = None,
        supervisor_instructions: str = "",
    ) -> RecoveryAction:
        located_files = located_files or []

        if strategy == RecoveryStrategy.A1:
            # A1: Localization Recovery
            guidance_loc = (
                f"Previous localization failed: {diagnosis_text}\n"
                "BROADEN SEARCH: Inspect call sites, import dependencies, and neighboring modules. "
                f"Do not restrict attention only to {located_files}."
            )
            return RecoveryAction(
                strategy=RecoveryStrategy.A1,
                target_agent="Locator",
                rerun_locator=True,
                rerun_coder=True,
                guidance_for_locator=guidance_loc,
                guidance_for_coder="Wait for updated localization context before generating new patch.",
                rationale="F1 detected: fault localization was inaccurate or incomplete.",
            )

        elif strategy == RecoveryStrategy.A2:
            # A2: Code/Reasoning Recovery
            trace_snippet = test_output[-1200:] if len(test_output) > 1200 else test_output
            guidance_coder = (
                f"TARGETED REPAIR DIRECTIVE (A2):\n"
                f"Diagnosis: {diagnosis_text}\n"
                f"Supervisor instructions: {supervisor_instructions}\n"
                f"Failed Test Traceback:\n{trace_snippet}\n"
                "Review the implementation logic, verify API contracts, and provide an alternative fix."
            )
            return RecoveryAction(
                strategy=RecoveryStrategy.A2,
                target_agent="Coder",
                rerun_locator=False,
                rerun_coder=True,
                guidance_for_coder=guidance_coder,
                rationale="F2 detected: correct files targeted, but logic or edge case failed tests.",
            )

        elif strategy == RecoveryStrategy.A3:
            # A3: Execution Recovery
            guidance_coder = (
                "PATCH SYNTAX / EXECUTION RECOVERY (A3):\n"
                "Your previous patch failed during patch application or execution.\n"
                "Ensure standard unified diff format:\n"
                "--- a/path/to/file.py\n"
                "+++ b/path/to/file.py\n"
                "@@ -old_start,old_count +new_start,new_count @@\n"
                "NEVER emit a bare '@@'. Every hunk header MUST have valid line numbers.\n"
                "Check for proper line endings and do not wrap patch in markdown text fences."
            )
            return RecoveryAction(
                strategy=RecoveryStrategy.A3,
                target_agent="Coder",
                rerun_locator=False,
                rerun_coder=True,
                guidance_for_coder=guidance_coder,
                rationale="F3 detected: patch was malformed, failed to apply, or crashed execution tool.",
            )

        elif strategy == RecoveryStrategy.A4:
            # A4: Strategy/Coordination Recovery
            prev_snippet = previous_patch[:400] if previous_patch else ""
            guidance_coder = (
                "COORDINATION / STRATEGY RESET (A4):\n"
                "Repeated failure detected. You are trapped in an ineffective local loop.\n"
                f"THE FOLLOWING APPROACH IS EXPLICITLY BANNED:\n{prev_snippet}\n"
                "You MUST pursue an entirely different algorithmic or structural design path."
            )
            return RecoveryAction(
                strategy=RecoveryStrategy.A4,
                target_agent="Coder",
                rerun_locator=True,  # Refresh perspective
                rerun_coder=True,
                guidance_for_locator="Re-examine issue with fresh perspective. Avoid repeating prior candidate symbols.",
                guidance_for_coder=guidance_coder,
                rationale="F4 detected: looping, thrashing, or repeated ineffective strategies.",
            )

        # Default fallback
        return RecoveryAction(
            strategy=RecoveryStrategy.A2,
            target_agent="Coder",
            rerun_coder=True,
            guidance_for_coder=diagnosis_text,
            rationale="Fallback intervention.",
        )
