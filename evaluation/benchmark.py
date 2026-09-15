"""Benchmark orchestration for multi-task evaluation suites."""

from __future__ import annotations

from typing import List, Optional
from core.config import DDIVConfig, ExecutionMode
from core.orchestrator import DDIVOrchestrator
from evaluation.metrics import EvaluationSummary, MetricCollector, TaskEvaluationResult
from evaluation.swebench_loader import SWEBenchLoader, SWEBenchTask


class BenchmarkRunner:
    """Executes experiments across task sets and aggregates comparative metrics."""

    def __init__(self, config: DDIVConfig):
        self.config = config
        self.collector = MetricCollector()
        self.loader = SWEBenchLoader()

    def run_benchmark(
        self,
        tasks: Optional[List[SWEBenchTask]] = None,
        limit: Optional[int] = None,
        mode: Optional[ExecutionMode] = None,
    ) -> EvaluationSummary:
        """Run evaluation across loaded benchmark tasks."""
        if mode:
            self.config.mode = mode

        if not tasks:
            # Fallback to mock task if no task list given
            tasks = [self.loader.get_mock_task()]

        if limit and limit > 0:
            tasks = tasks[:limit]

        orchestrator = DDIVOrchestrator(self.config)

        for task in tasks:
            run_state = orchestrator.run_task(
                task_id=task.instance_id,
                issue_description=task.problem_statement,
                repository=task.repo,
                base_commit=task.base_commit,
            )

            # Extract metrics from run_state
            initial_failure = None
            if run_state.attempt_history and not run_state.attempt_history[0].test_passed:
                initial_failure = run_state.attempt_history[0].failure_type

            all_failures = [
                h.failure_type for h in run_state.attempt_history if h.failure_type
            ]

            recovered = (
                run_state.is_resolved
                and len(run_state.attempt_history) > 1
                and not run_state.attempt_history[0].test_passed
            )

            rec_strategy = None
            if len(run_state.attempt_history) > 1:
                rec_strategy = run_state.attempt_history[0].recovery_action

            eval_res = TaskEvaluationResult(
                task_id=task.instance_id,
                mode=self.config.mode.value,
                resolved=run_state.is_resolved,
                total_attempts=len(run_state.attempt_history) or 1,
                total_latency_seconds=(run_state.end_time or 0) - run_state.start_time,
                total_tokens=run_state.total_tokens_used,
                initial_failure_type=initial_failure,
                recovered=recovered,
                recovery_strategy_used=rec_strategy,
                detected_failures=all_failures,
                patch_applied_first_try=(
                    bool(run_state.attempt_history)
                    and bool(run_state.attempt_history[0].patch)
                ),
            )
            self.collector.add_result(eval_res)

        return self.collector.compute_summary()
