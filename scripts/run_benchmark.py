"""CLI entrypoint to run benchmark evaluations."""

from __future__ import annotations

import argparse
import sys
from core.config import DDIVConfig, ExecutionMode
from evaluation.benchmark import BenchmarkRunner
from evaluation.swebench_loader import SWEBenchLoader


def main():
    parser = argparse.ArgumentParser(description="Run benchmark experiments across tasks.")
    parser.add_argument("--dataset", type=str, default="swebench_verified", help="Dataset name or path")
    parser.add_argument("--limit", type=int, default=1, help="Max number of tasks to run")
    parser.add_argument(
        "--mode",
        type=str,
        default="ddiv",
        choices=["mock", "baseline", "ddiv", "recovery_only", "memory_only", "trust_only", "full_ddiv"],
        help="Experiment execution mode",
    )
    args = parser.parse_args()

    config = DDIVConfig.load_from_env()
    config.mode = ExecutionMode(args.mode)

    runner = BenchmarkRunner(config)
    loader = SWEBenchLoader()

    tasks = [loader.get_mock_task(f"mock-task-{i+1}") for i in range(args.limit)]

    print(f"Executing Benchmark: {args.dataset} (Limit: {args.limit}, Mode: {args.mode.upper()})")
    summary = runner.run_benchmark(tasks=tasks, limit=args.limit)

    print("\n" + "=" * 60)
    print(" BENCHMARK EVALUATION SUMMARY")
    print("=" * 60)
    print(f" Total Tasks:             {summary.total_tasks}")
    print(f" Resolved Tasks:          {summary.resolved_tasks}")
    print(f" Resolved Rate:           {summary.resolved_rate * 100:.1f}%")
    print(f" Recovery Success Rate:   {summary.recovery_success_rate * 100:.1f}%")
    print(f" Avg Attempts / Task:     {summary.avg_attempts_per_task}")
    print(f" Avg Latency / Task:      {summary.avg_latency_seconds:.2f}s")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
