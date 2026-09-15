"""Failure detection subsystem with deterministic and heuristic rule evaluators."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FailureType(str, Enum):
    F1 = "F1"  # Localization Failure
    F2 = "F2"  # Code/Reasoning Failure
    F3 = "F3"  # Tool/Patch/Execution Failure
    F4 = "F4"  # Coordination/Strategy Failure


class DetectionResult(BaseModel):
    is_failure: bool
    candidate_failure_type: Optional[FailureType] = None
    confidence: float = 0.0
    evidence_reasons: List[str] = Field(default_factory=list)
    deterministic: bool = False


class FailureDetector:
    """Evaluates multi-source evidence to detect and classify failures deterministically where possible."""

    @staticmethod
    def compute_patch_hash(patch: str) -> str:
        """Normalized hash of unified diff to detect repeated identical code proposals."""
        clean = "\n".join(line.strip() for line in patch.splitlines() if line.strip())
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()

    def evaluate(
        self,
        patch_valid: bool,
        patch_applied: bool,
        test_passed: bool,
        test_output: str,
        located_files: List[str],
        modified_files: List[str],
        current_patch: str,
        previous_attempts: List[Dict[str, Any]],
        syntax_error: bool = False,
    ) -> DetectionResult:
        """Run hierarchical deterministic rules to detect and classify failures."""
        evidence: List[str] = []

        # Rule 0: If all tests passed and patch is clean, no failure!
        if patch_valid and patch_applied and test_passed:
            return DetectionResult(
                is_failure=False,
                candidate_failure_type=None,
                confidence=1.0,
                evidence_reasons=["Patch applied cleanly and all tests verified successfully."],
                deterministic=True,
            )

        # Rule 1: F4 — Strategy / Coordination Failure (Thrashing or looping)
        # Check if current patch is identical to any previous attempt's patch
        current_hash = self.compute_patch_hash(current_patch) if current_patch else ""
        for prev in previous_attempts:
            prev_patch = prev.get("patch", "")
            if prev_patch and current_hash and self.compute_patch_hash(prev_patch) == current_hash:
                evidence.append(
                    f"Attempt repeated identical patch proposal to attempt {prev.get('attempt', '?')} (Hash: {current_hash[:8]})"
                )
                return DetectionResult(
                    is_failure=True,
                    candidate_failure_type=FailureType.F4,
                    confidence=0.98,
                    evidence_reasons=evidence,
                    deterministic=True,
                )

        # Rule 2: F3 — Tool / Patch / Execution Failure
        # Malformed diff, patch rejection, syntax errors, or runner crash
        if not patch_valid:
            evidence.append("Patch failed validation (malformed unified diff format or missing standard headers).")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F3,
                confidence=0.95,
                evidence_reasons=evidence,
                deterministic=True,
            )

        if not patch_applied:
            evidence.append("Git apply failed to cleanly apply the patch to the target files.")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F3,
                confidence=0.95,
                evidence_reasons=evidence,
                deterministic=True,
            )

        if syntax_error or "SyntaxError" in test_output or "IndentationError" in test_output:
            evidence.append("Patch introduced a syntax or indentation error.")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F3,
                confidence=0.90,
                evidence_reasons=evidence,
                deterministic=True,
            )

        # Rule 3: F1 — Localization Failure
        # Modified files are completely disjoint from located files or issue specification
        if modified_files and located_files:
            overlap = set(modified_files).intersection(set(located_files))
            if not overlap:
                evidence.append(
                    f"Coder modified {modified_files} which has zero overlap with located files {located_files}."
                )
                return DetectionResult(
                    is_failure=True,
                    candidate_failure_type=FailureType.F1,
                    confidence=0.88,
                    evidence_reasons=evidence,
                    deterministic=True,
                )

        # Rule 4: F2 — Code / Reasoning Failure
        # Patch applied cleanly, but assertion errors, unit test failures, or runtime exceptions occurred
        if patch_applied and not test_passed:
            evidence.append("Patch applied cleanly, but test suite reported assertion failures or regression.")
            if "AssertionError" in test_output or "FAILED" in test_output or "FAIL" in test_output:
                evidence.append("Test output contains explicit assertion failure traces.")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F2,
                confidence=0.92,
                evidence_reasons=evidence,
                deterministic=True,
            )

        # Fallback general failure
        evidence.append("Unclassified failure detected during execution pipeline.")
        return DetectionResult(
            is_failure=True,
            candidate_failure_type=FailureType.F2,
            confidence=0.50,
            evidence_reasons=evidence,
            deterministic=False,
        )
