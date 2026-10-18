"""Experiment conditions for DDIV comparative benchmarking."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict
from core.config import ExecutionMode


class ExperimentCondition(str, Enum):
    """The experimental conditions evaluated in DDIV research."""

    BASELINE = "baseline"
    RETRY_ONLY = "retry_only"
    FULL_DDIV = "full_ddiv"
    FULL_DDIV_MEMORY_OFF = "full_ddiv_memory_off"
    FULL_DDIV_MEMORY_ON = "full_ddiv_memory_on"

    @classmethod
    def from_str(cls, val: str) -> ExperimentCondition:
        """Parse condition string flexibly (case-insensitive, underscores or hyphens)."""
        clean = val.strip().lower().replace("-", "_")
        for member in cls:
            if member.value == clean or member.name.lower() == clean:
                return member
        raise ValueError(
            f"Unknown experiment condition: '{val}'. "
            f"Supported conditions: {[m.value for m in cls]}"
        )

    def to_execution_mode(self) -> ExecutionMode:
        """Map experimental condition to corresponding DDIV ExecutionMode."""
        if self == ExperimentCondition.BASELINE:
            return ExecutionMode.BASELINE
        elif self == ExperimentCondition.RETRY_ONLY:
            return ExecutionMode.RECOVERY_ONLY
        elif self in (
            ExperimentCondition.FULL_DDIV,
            ExperimentCondition.FULL_DDIV_MEMORY_OFF,
            ExperimentCondition.FULL_DDIV_MEMORY_ON,
        ):
            return ExecutionMode.FULL_DDIV
        raise ValueError(f"Unmapped condition: {self}")

    @property
    def max_attempts(self) -> int:
        """Number of allowed attempts."""
        if self == ExperimentCondition.BASELINE:
            return 1
        return 3

    @property
    def is_supervisor_enabled(self) -> bool:
        """Whether Supervisor agent is active for failure diagnosis and intervention."""
        return self in (
            ExperimentCondition.FULL_DDIV,
            ExperimentCondition.FULL_DDIV_MEMORY_OFF,
            ExperimentCondition.FULL_DDIV_MEMORY_ON,
        )

    @property
    def is_diagnosis_enabled(self) -> bool:
        """Whether failure diagnosis (F1-F4) is active."""
        return self in (
            ExperimentCondition.FULL_DDIV,
            ExperimentCondition.FULL_DDIV_MEMORY_OFF,
            ExperimentCondition.FULL_DDIV_MEMORY_ON,
        )

    @property
    def is_intervention_enabled(self) -> bool:
        """Whether targeted A1-A4 recovery interventions are active."""
        return self in (
            ExperimentCondition.FULL_DDIV,
            ExperimentCondition.FULL_DDIV_MEMORY_OFF,
            ExperimentCondition.FULL_DDIV_MEMORY_ON,
        )

    @property
    def is_memory_enabled(self) -> bool:
        """Whether historical experience memory is enabled."""
        return self in (
            ExperimentCondition.FULL_DDIV,
            ExperimentCondition.FULL_DDIV_MEMORY_ON,
        )

    @property
    def is_trust_enabled(self) -> bool:
        """Whether dynamic trust ledger tracking is enabled."""
        return self in (
            ExperimentCondition.FULL_DDIV,
            ExperimentCondition.FULL_DDIV_MEMORY_OFF,
            ExperimentCondition.FULL_DDIV_MEMORY_ON,
        )

    def get_summary_description(self) -> str:
        """Human-readable description of this condition's intervention mechanism."""
        if self == ExperimentCondition.BASELINE:
            return "Single-pass feedforward execution (Locator -> Coder -> PatchBuilder -> Verify), no retries."
        elif self == ExperimentCondition.RETRY_ONLY:
            return "Blind multi-attempt retry (up to 3 attempts) from clean state; Supervisor, Diagnosis, Intervention, Memory, and Trust all disabled."
        elif self == ExperimentCondition.FULL_DDIV:
            return "Full DDIV loop: Multi-attempt recovery, Failure Diagnosis, Targeted A1-A4 Interventions, Memory Store, and Trust Ledger."
        elif self == ExperimentCondition.FULL_DDIV_MEMORY_OFF:
            return "Full DDIV loop without episodic memory: Multi-attempt recovery, Failure Diagnosis, Targeted Interventions, Trust Ledger; zero episodic memory retrieval, injection, or storage."
        elif self == ExperimentCondition.FULL_DDIV_MEMORY_ON:
            return "Full DDIV loop with episodic memory: Multi-attempt recovery, Failure Diagnosis, Targeted Interventions, Trust Ledger, and conditioned-scoped episodic memory retrieval, advisory prompt injection, and persistence."
        return ""
