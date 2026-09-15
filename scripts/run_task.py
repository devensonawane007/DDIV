"""CLI entrypoint to execute a single task in Mock, Baseline, or DDIV mode."""

from __future__ import annotations

import argparse
import sys
from core.config import DDIVConfig, ExecutionMode
from core.orchestrator import DDIVOrchestrator
from evaluation.swebench_loader import SWEBenchLoader


def main():
    parser = argparse.ArgumentParser(description="Run DDIV code repair pipeline on a single task.")
    parser.add_argument("--task-id", type=str, default="mock-task-1", help="Task / instance ID to run")
    parser.add_argument(
        "--mode",
        type=str,
        default="ddiv",
        choices=["mock", "baseline", "ddiv", "recovery_only", "memory_only", "trust_only", "full_ddiv"],
        help="Workflow execution mode",
    )
    parser.add_argument("--repo", type=str, default="mock-repo", help="Target repository identifier")
    parser.add_argument("--issue", type=str, default="", help="Optional issue description text")

    args = parser.parse_args()

    config = DDIVConfig.load_from_env()
    config.mode = ExecutionMode(args.mode)

    loader = SWEBenchLoader()
    if not args.issue:
        task_data = loader.get_mock_task(args.task_id)
        issue_text = task_data.problem_statement
        repo_name = task_data.repo
        base_commit = task_data.base_commit
    else:
        issue_text = args.issue
        repo_name = args.repo
        base_commit = "HEAD"

    orchestrator = DDIVOrchestrator(config)
    print(f"Starting task: {args.task_id} in {args.mode.upper()} mode...")
    state = orchestrator.run_task(
        task_id=args.task_id,
        issue_description=issue_text,
        repository=repo_name,
        base_commit=base_commit,
    )

    if state.is_resolved:
        print(f"Result: SUCCESS (Resolved in {len(state.attempt_history)} attempt(s))")
        sys.exit(0)
    else:
        print(f"Result: FAILED (Unresolved after {len(state.attempt_history)} attempt(s))")
        sys.exit(1)


if __name__ == "__main__":
    main()
