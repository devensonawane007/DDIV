"""Comprehensive research evaluation metrics for DDIV vs. Baseline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskEvaluationResult(BaseModel):
    task_id: str
    mode: str
    resolved: bool
    total_attempts: int
    total_latency_seconds: float
    total_tokens: int
    initial_failure_type: Optional[str] = None
    recovered: bool = False
    recovery_strategy_used: Optional[str] = None
    detected_failures: List[str] = Field(default_factory=list)
    trust_trajectory: Dict[str, List[float]] = Field(default_factory=dict)
    memory_matches_count: int = 0
    patch_applied_first_try: bool = False


class EvaluationSummary(BaseModel):
    total_tasks: int = 0
    resolved_tasks: int = 0
    resolved_rate: float = 0.0

    # Recovery metrics
    recovery_attempts_total: int = 0
    recovery_successes_total: int = 0
    recovery_success_rate: float = 0.0
    recovery_by_failure_type: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    repeated_failure_count: int = 0
    repeated_failure_rate: float = 0.0

    # Efficiency
    avg_attempts_per_task: float = 0.0
    avg_latency_seconds: float = 0.0
    total_tokens: int = 0
    avg_tokens_per_task: float = 0.0

    # Task results
    task_results: List[TaskEvaluationResult] = Field(default_factory=list)


class MetricCollector:
    """Aggregates and computes statistical metrics across task runs."""

    def __init__(self):
        self.records: List[TaskEvaluationResult] = []

    def add_result(self, res: TaskEvaluationResult) -> None:
        self.records.append(res)

    def compute_summary(self) -> EvaluationSummary:
        total = len(self.records)
        if total == 0:
            return EvaluationSummary()

        resolved = sum(1 for r in self.records if r.resolved)
        resolved_rate = round(resolved / total, 4)

        # Recovery metrics
        recovery_tasks = [r for r in self.records if r.total_attempts > 1]
        rec_attempts = len(recovery_tasks)
        rec_success = sum(1 for r in recovery_tasks if r.recovered)
        rec_rate = round(rec_success / rec_attempts, 4) if rec_attempts > 0 else 0.0

        # Break down by failure type
        by_ftype: Dict[str, Dict[str, int]] = {
            "F1": {"total": 0, "recovered": 0},
            "F2": {"total": 0, "recovered": 0},
            "F3": {"total": 0, "recovered": 0},
            "F4": {"total": 0, "recovered": 0},
        }

        repeated_count = 0
        for r in self.records:
            if r.initial_failure_type in by_ftype:
                by_ftype[r.initial_failure_type]["total"] += 1
                if r.recovered:
                    by_ftype[r.initial_failure_type]["recovered"] += 1
            if "F4" in r.detected_failures:
                repeated_count += 1

        avg_attempts = round(sum(r.total_attempts for r in self.records) / total, 2)
        avg_latency = round(sum(r.total_latency_seconds for r in self.records) / total, 2)
        total_tok = sum(r.total_tokens for r in self.records)
        avg_tokens = round(total_tok / total, 1)

        return EvaluationSummary(
            total_tasks=total,
            resolved_tasks=resolved,
            resolved_rate=resolved_rate,
            recovery_attempts_total=rec_attempts,
            recovery_successes_total=rec_success,
            recovery_success_rate=rec_rate,
            recovery_by_failure_type=by_ftype,
            repeated_failure_count=repeated_count,
            repeated_failure_rate=round(repeated_count / total, 4),
            avg_attempts_per_task=avg_attempts,
            avg_latency_seconds=avg_latency,
            total_tokens=total_tok,
            avg_tokens_per_task=avg_tokens,
            task_results=self.records,
        )
