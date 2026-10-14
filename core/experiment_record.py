"""Data models for experiment records, job status, and manifest state."""

from __future__ import annotations

import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.conditions import ExperimentCondition


class ConditionJobStatus(str, Enum):
    """Execution status of an experimental job (task + condition)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    ABORTED_QUOTA_EXHAUSTED = "ABORTED_QUOTA_EXHAUSTED"


class ExperimentConditionRecord(BaseModel):
    """Complete, self-contained record of an isolated worker execution."""

    experiment_id: str
    task_id: str
    condition: ExperimentCondition
    status: ConditionJobStatus
    resolved: bool = False
    workflow_completed: bool = False
    patch_generated: bool = False
    patch_applied: bool = False
    failed_stage: Optional[str] = None
    error_code: Optional[str] = None
    provider_failure: Optional[Dict[str, Any]] = None
    degraded_execution: bool = False
    degraded_reason: Optional[str] = None
    attempts: int = 0
    attempt_history: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_patch: str = ""
    candidate_patch_path: Optional[str] = None
    pass_at_1: Optional[bool] = None
    metrics: Optional[Dict[str, Any]] = None
    failure_detection: Optional[Dict[str, Any]] = None
    internal_evaluation: Optional[Dict[str, Any]] = None
    official_evaluation: Optional[Dict[str, Any]] = None
    trust_scores: Optional[Dict[str, float]] = None
    execution_duration_seconds: float = 0.0
    worker_pid: Optional[int] = None
    worker_exit_code: Optional[int] = None
    log_file_path: str = ""
    workspace_path: str = ""
    error_message: Optional[str] = None
    started_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    completed_at: Optional[str] = None

    def save_to_file(self, target_path: str | Path) -> None:
        """Atomic write to disk to prevent partial corruption."""
        path = Path(target_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        tmp_path.replace(path)

    @classmethod
    def load_from_file(cls, path: str | Path) -> ExperimentConditionRecord:
        """Load record from a JSON file."""
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class ExperimentManifest(BaseModel):
    """Manifest tracking state and progress across all tasks and conditions for an experiment."""

    experiment_id: str
    dataset: str = "swebench_verified"
    tasks: List[str] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list)
    jobs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    created_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    summary: Optional[Dict[str, Any]] = None

    @staticmethod
    def job_key(task_id: str, condition: str | ExperimentCondition) -> str:
        cond_str = condition.value if isinstance(condition, ExperimentCondition) else str(condition)
        return f"{task_id}__{cond_str}"

    def update_job_status(
        self,
        task_id: str,
        condition: str | ExperimentCondition,
        status: ConditionJobStatus,
        result_file: Optional[str] = None,
        resolved: bool = False,
        error: Optional[str] = None,
        duration: float = 0.0,
    ) -> None:
        key = self.job_key(task_id, condition)
        cond_str = condition.value if isinstance(condition, ExperimentCondition) else str(condition)
        self.jobs[key] = {
            "task_id": task_id,
            "condition": cond_str,
            "status": status.value,
            "resolved": resolved,
            "result_file": result_file,
            "error": error,
            "duration_seconds": duration,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def is_job_completed(self, task_id: str, condition: str | ExperimentCondition) -> bool:
        key = self.job_key(task_id, condition)
        if key not in self.jobs:
            return False
        return self.jobs[key].get("status") == ConditionJobStatus.COMPLETED.value

    def save_to_file(self, target_path: str | Path) -> None:
        path = Path(target_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        tmp_path.replace(path)

    @classmethod
    def load_from_file(cls, path: str | Path) -> ExperimentManifest:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
