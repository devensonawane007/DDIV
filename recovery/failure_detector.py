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


class GranularFailureType(str, Enum):
    """Fine-grained objective failure classifications observed during execution."""

    CODER_EMPTY_RESPONSE = "CODER_EMPTY_RESPONSE"
    CODER_INVALID_JSON = "CODER_INVALID_JSON"
    CODER_SCHEMA_FAILURE = "CODER_SCHEMA_FAILURE"
    CODER_API_ERROR = "CODER_API_ERROR"
    CODER_RATE_LIMITED = "CODER_RATE_LIMITED"
    CODER_NO_VALID_MODIFICATION = "CODER_NO_VALID_MODIFICATION"
    PATCH_INVALID = "PATCH_INVALID"
    PATCH_APPLICATION_FAILED = "PATCH_APPLICATION_FAILED"
    ANCHOR_NOT_FOUND = "ANCHOR_NOT_FOUND"
    F2P_FAILURE = "F2P_FAILURE"
    P2P_REGRESSION = "P2P_REGRESSION"
    TEST_INFRASTRUCTURE_FAILURE = "TEST_INFRASTRUCTURE_FAILURE"
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
    EVALUATOR_UNAVAILABLE = "EVALUATOR_UNAVAILABLE"
    REPEATED_PATCH_CYCLE = "REPEATED_PATCH_CYCLE"
    TIMEOUT = "TIMEOUT"
    LOCATOR_FAILURE = "LOCATOR_FAILURE"


GRANULAR_TO_TAXONOMY: Dict[GranularFailureType, FailureType] = {
    GranularFailureType.LOCATOR_FAILURE: FailureType.F1,
    GranularFailureType.F2P_FAILURE: FailureType.F2,
    GranularFailureType.P2P_REGRESSION: FailureType.F2,
    GranularFailureType.CODER_NO_VALID_MODIFICATION: FailureType.F2,
    GranularFailureType.CODER_EMPTY_RESPONSE: FailureType.F3,
    GranularFailureType.CODER_INVALID_JSON: FailureType.F3,
    GranularFailureType.CODER_SCHEMA_FAILURE: FailureType.F3,
    GranularFailureType.CODER_API_ERROR: FailureType.F3,
    GranularFailureType.CODER_RATE_LIMITED: FailureType.F3,
    GranularFailureType.PATCH_INVALID: FailureType.F3,
    GranularFailureType.PATCH_APPLICATION_FAILED: FailureType.F3,
    GranularFailureType.ANCHOR_NOT_FOUND: FailureType.F3,
    GranularFailureType.TEST_INFRASTRUCTURE_FAILURE: FailureType.F4,
    GranularFailureType.ENVIRONMENT_FAILURE: FailureType.F4,
    GranularFailureType.EVALUATOR_UNAVAILABLE: FailureType.F4,
    GranularFailureType.REPEATED_PATCH_CYCLE: FailureType.F4,
    GranularFailureType.TIMEOUT: FailureType.F4,
}


class DetectionResult(BaseModel):
    is_failure: bool
    candidate_failure_type: Optional[FailureType] = None
    granular_failure_type: Optional[GranularFailureType] = None
    confidence: float = 0.0
    evidence_reasons: List[str] = Field(default_factory=list)
    deterministic: bool = False
    objective_failure_evidence: Dict[str, Any] = Field(default_factory=dict)


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
        test_output: str = "",
        located_files: Optional[List[str]] = None,
        modified_files: Optional[List[str]] = None,
        current_patch: str = "",
        previous_attempts: Optional[List[Dict[str, Any]]] = None,
        syntax_error: bool = False,
        coder_error_code: Optional[str] = None,
        coder_error_detail: Optional[str] = None,
        clean_base_passed: bool = True,
        f2p_passed: Optional[bool] = None,
        p2p_passed: Optional[bool] = None,
        failed_f2p_tests: Optional[List[str]] = None,
        failed_p2p_tests: Optional[List[str]] = None,
        timed_out: bool = False,
    ) -> DetectionResult:
        """Run hierarchical deterministic rules to detect and classify failures."""
        evidence: List[str] = []
        located_files = located_files or []
        modified_files = modified_files or []
        previous_attempts = previous_attempts or []
        failed_f2p_tests = failed_f2p_tests or []
        failed_p2p_tests = failed_p2p_tests or []

        obj_evidence: Dict[str, Any] = {
            "patch_valid": patch_valid,
            "patch_applied": patch_applied,
            "test_passed": test_passed,
            "coder_error_code": coder_error_code,
            "clean_base_passed": clean_base_passed,
            "f2p_passed": f2p_passed,
            "p2p_passed": p2p_passed,
            "failed_f2p_tests": failed_f2p_tests,
            "failed_p2p_tests": failed_p2p_tests,
            "timed_out": timed_out,
        }

        # Rule 0: Clean verification
        all_ok = patch_valid and patch_applied and test_passed
        if f2p_passed is not None:
            all_ok = all_ok and (f2p_passed is True)
        if p2p_passed is not None:
            all_ok = all_ok and (p2p_passed is True)

        if all_ok:
            return DetectionResult(
                is_failure=False,
                candidate_failure_type=None,
                granular_failure_type=None,
                confidence=1.0,
                evidence_reasons=["Patch applied cleanly and all test requirements verified successfully."],
                deterministic=True,
                objective_failure_evidence=obj_evidence,
            )

        # Rule 1: Timeout (F4)
        if timed_out or "timed out" in test_output.lower():
            evidence.append("Execution timed out before tests completed.")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F4,
                granular_failure_type=GranularFailureType.TIMEOUT,
                confidence=0.99,
                evidence_reasons=evidence,
                deterministic=True,
                objective_failure_evidence=obj_evidence,
            )

        # Rule 2: Clean Base / Environment Failure (F4)
        if not clean_base_passed:
            evidence.append("Pristine repository base failed pre-existing PASS_TO_PASS tests (environment failure).")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F4,
                granular_failure_type=GranularFailureType.ENVIRONMENT_FAILURE,
                confidence=0.98,
                evidence_reasons=evidence,
                deterministic=True,
                objective_failure_evidence=obj_evidence,
            )

        # Rule 3: Repeated identical patch cycle / looping (F4)
        current_hash = self.compute_patch_hash(current_patch) if current_patch else ""
        for prev in previous_attempts:
            prev_patch = prev.get("generated_patch") or prev.get("patch", "")
            if prev_patch and current_hash and self.compute_patch_hash(prev_patch) == current_hash:
                evidence.append(
                    f"Attempt repeated identical patch proposal to attempt {prev.get('attempt', '?')} (Hash: {current_hash[:8]})"
                )
                return DetectionResult(
                    is_failure=True,
                    candidate_failure_type=FailureType.F4,
                    granular_failure_type=GranularFailureType.REPEATED_PATCH_CYCLE,
                    confidence=0.98,
                    evidence_reasons=evidence,
                    deterministic=True,
                    objective_failure_evidence=obj_evidence,
                )

        # Rule 4: Coder Generation & Tooling Errors (F3 vs F2)
        if coder_error_code:
            code_upper = coder_error_code.upper()
            if code_upper == "CODER_EMPTY_RESPONSE":
                evidence.append("Coder model returned empty response.")
                return DetectionResult(
                    is_failure=True,
                    candidate_failure_type=FailureType.F3,
                    granular_failure_type=GranularFailureType.CODER_EMPTY_RESPONSE,
                    confidence=0.95,
                    evidence_reasons=evidence,
                    deterministic=True,
                    objective_failure_evidence=obj_evidence,
                )
            elif code_upper in ("CODER_INVALID_JSON", "JSON_DECODE_ERROR"):
                evidence.append("Coder output could not be parsed as valid JSON.")
                return DetectionResult(
                    is_failure=True,
                    candidate_failure_type=FailureType.F3,
                    granular_failure_type=GranularFailureType.CODER_INVALID_JSON,
                    confidence=0.95,
                    evidence_reasons=evidence,
                    deterministic=True,
                    objective_failure_evidence=obj_evidence,
                )
            elif code_upper == "CODER_SCHEMA_FAILURE":
                evidence.append("Coder output violated the required modification schema.")
                return DetectionResult(
                    is_failure=True,
                    candidate_failure_type=FailureType.F3,
                    granular_failure_type=GranularFailureType.CODER_SCHEMA_FAILURE,
                    confidence=0.95,
                    evidence_reasons=evidence,
                    deterministic=True,
                    objective_failure_evidence=obj_evidence,
                )
            elif "RATE_LIMIT" in code_upper:
                evidence.append("Coder API endpoint rate limited.")
                return DetectionResult(
                    is_failure=True,
                    candidate_failure_type=FailureType.F3,
                    granular_failure_type=GranularFailureType.CODER_RATE_LIMITED,
                    confidence=0.95,
                    evidence_reasons=evidence,
                    deterministic=True,
                    objective_failure_evidence=obj_evidence,
                )
            elif code_upper in ("PATCH_BUILDER_FAILED", "ANCHOR_NOT_FOUND"):
                evidence.append(f"PatchBuilder anchor matching failed: {coder_error_detail or 'anchor not found in source'}.")
                return DetectionResult(
                    is_failure=True,
                    candidate_failure_type=FailureType.F3,
                    granular_failure_type=GranularFailureType.ANCHOR_NOT_FOUND,
                    confidence=0.95,
                    evidence_reasons=evidence,
                    deterministic=True,
                    objective_failure_evidence=obj_evidence,
                )
            elif code_upper == "CODER_NO_VALID_MODIFICATION":
                evidence.append("Coder could not formulate a concrete code change for the issue.")
                return DetectionResult(
                    is_failure=True,
                    candidate_failure_type=FailureType.F2,
                    granular_failure_type=GranularFailureType.CODER_NO_VALID_MODIFICATION,
                    confidence=0.90,
                    evidence_reasons=evidence,
                    deterministic=True,
                    objective_failure_evidence=obj_evidence,
                )

        # Rule 5: Patch Structure & Git Apply Failures (F3)
        if not patch_valid:
            evidence.append("Patch failed validation (missing @@ hunk headers, malformed diff, or empty diff).")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F3,
                granular_failure_type=GranularFailureType.PATCH_INVALID,
                confidence=0.95,
                evidence_reasons=evidence,
                deterministic=True,
                objective_failure_evidence=obj_evidence,
            )

        if not patch_applied:
            evidence.append("Git apply rejected the patch.")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F3,
                granular_failure_type=GranularFailureType.PATCH_APPLICATION_FAILED,
                confidence=0.95,
                evidence_reasons=evidence,
                deterministic=True,
                objective_failure_evidence=obj_evidence,
            )

        if syntax_error or "SyntaxError" in test_output or "IndentationError" in test_output:
            evidence.append("Patch introduced syntax or indentation errors into the codebase.")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F3,
                granular_failure_type=GranularFailureType.PATCH_INVALID,
                confidence=0.92,
                evidence_reasons=evidence,
                deterministic=True,
                objective_failure_evidence=obj_evidence,
            )

        # Rule 6: Fault Localization Disjointness (F1)
        if modified_files and located_files:
            overlap = set(modified_files).intersection(set(located_files))
            if not overlap:
                evidence.append(
                    f"Coder modified {modified_files} which has zero overlap with located files {located_files}."
                )
                return DetectionResult(
                    is_failure=True,
                    candidate_failure_type=FailureType.F1,
                    granular_failure_type=GranularFailureType.LOCATOR_FAILURE,
                    confidence=0.90,
                    evidence_reasons=evidence,
                    deterministic=True,
                    objective_failure_evidence=obj_evidence,
                )
        if not located_files:
            evidence.append("Locator returned empty list of candidate files.")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F1,
                granular_failure_type=GranularFailureType.LOCATOR_FAILURE,
                confidence=0.90,
                evidence_reasons=evidence,
                deterministic=True,
                objective_failure_evidence=obj_evidence,
            )

        # Rule 7: Test Regression & Logic Failure (F2)
        if p2p_passed is False or failed_p2p_tests:
            evidence.append(f"Candidate patch broke existing behavior (PASS_TO_PASS regression: {failed_p2p_tests}).")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F2,
                granular_failure_type=GranularFailureType.P2P_REGRESSION,
                confidence=0.95,
                evidence_reasons=evidence,
                deterministic=True,
                objective_failure_evidence=obj_evidence,
            )

        if f2p_passed is False or failed_f2p_tests:
            evidence.append(f"Candidate patch failed to resolve the reported issue (FAIL_TO_PASS failed: {failed_f2p_tests}).")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F2,
                granular_failure_type=GranularFailureType.F2P_FAILURE,
                confidence=0.95,
                evidence_reasons=evidence,
                deterministic=True,
                objective_failure_evidence=obj_evidence,
            )

        # Rule 8: General test failure (F2)
        if not test_passed:
            evidence.append("Tests failed after clean patch application.")
            return DetectionResult(
                is_failure=True,
                candidate_failure_type=FailureType.F2,
                granular_failure_type=GranularFailureType.F2P_FAILURE,
                confidence=0.90,
                evidence_reasons=evidence,
                deterministic=True,
                objective_failure_evidence=obj_evidence,
            )

        # Fallback
        evidence.append("Unclassified failure detected during execution pipeline.")
        return DetectionResult(
            is_failure=True,
            candidate_failure_type=FailureType.F2,
            granular_failure_type=GranularFailureType.F2P_FAILURE,
            confidence=0.50,
            evidence_reasons=evidence,
            deterministic=False,
            objective_failure_evidence=obj_evidence,
        )
