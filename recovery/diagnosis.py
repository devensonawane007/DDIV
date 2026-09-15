"""Diagnosis engine synthesizing deterministic detector output with Supervisor reasoning."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from recovery.failure_detector import DetectionResult, FailureType


class DiagnosisReport(BaseModel):
    is_failure: bool
    final_failure_type: Optional[FailureType] = None
    diagnosis_summary: str
    confidence: float
    deterministic_evidence: List[str] = Field(default_factory=list)
    supervisor_assessment: Optional[str] = None
    recommended_recovery: Optional[str] = None


class DiagnosisEngine:
    """Combines deterministic failure indicators with Supervisor model reasoning."""

    @staticmethod
    def synthesize(
        detection: DetectionResult,
        supervisor_failure: Optional[str],
        supervisor_diagnosis: str,
        supervisor_recovery: Optional[str],
        supervisor_confidence: float,
    ) -> DiagnosisReport:
        if not detection.is_failure:
            return DiagnosisReport(
                is_failure=False,
                final_failure_type=None,
                diagnosis_summary="Verification succeeded. No failure detected.",
                confidence=1.0,
                deterministic_evidence=detection.evidence_reasons,
                supervisor_assessment=supervisor_diagnosis,
            )

        # If detection was deterministic with high confidence (>0.85), deterministic rule takes precedence
        if detection.deterministic and detection.confidence >= 0.85 and detection.candidate_failure_type:
            final_type = detection.candidate_failure_type
            combined_summary = (
                f"Deterministic Classification [{final_type.value}]: "
                f"{'; '.join(detection.evidence_reasons)}. "
                f"Supervisor note: {supervisor_diagnosis}"
            )
            return DiagnosisReport(
                is_failure=True,
                final_failure_type=final_type,
                diagnosis_summary=combined_summary,
                confidence=detection.confidence,
                deterministic_evidence=detection.evidence_reasons,
                supervisor_assessment=supervisor_diagnosis,
                recommended_recovery=supervisor_recovery,
            )

        # Otherwise integrate Supervisor's classification
        chosen_type = None
        if supervisor_failure in [f.value for f in FailureType]:
            chosen_type = FailureType(supervisor_failure)
        elif detection.candidate_failure_type:
            chosen_type = detection.candidate_failure_type

        return DiagnosisReport(
            is_failure=True,
            final_failure_type=chosen_type,
            diagnosis_summary=supervisor_diagnosis or "; ".join(detection.evidence_reasons),
            confidence=max(detection.confidence, supervisor_confidence),
            deterministic_evidence=detection.evidence_reasons,
            supervisor_assessment=supervisor_diagnosis,
            recommended_recovery=supervisor_recovery,
        )
