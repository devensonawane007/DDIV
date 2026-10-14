"""CLI entrypoint to execute multi-condition DDIV experiment matrices."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Ensure child worker subprocesses default to UTF-8 standard streams on Windows
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Add project root to sys.path for direct CLI invocation
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(project_root) / ".env", override=True)
except ImportError:
    pass

from core.conditions import ExperimentCondition
from core.experiment_orchestrator import ExperimentOrchestrator


def main():
    parser = argparse.ArgumentParser(
        description="Run DDIV comparative experiment matrix (BASELINE, RETRY_ONLY, FULL_DDIV) across tasks."
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        default=["pallets__flask-5014"],
        help="List of SWE-bench instance IDs to evaluate",
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=["baseline", "retry_only", "full_ddiv"],
        help="Experiment conditions to run: baseline, retry_only, full_ddiv",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="mock",
        choices=["mock", "real"],
        help="Model provider mode ('mock' for testing, 'real' for live API models)",
    )
    parser.add_argument(
        "--experiment-id",
        type=str,
        default=f"exp_{int(time.time())}",
        help="Experiment run identifier",
    )
    parser.add_argument(
        "--worker-timeout",
        type=int,
        default=300,
        help="Timeout in seconds for each child worker process",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume previously interrupted run (skip completed jobs)",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Do not resume; start fresh",
    )
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        default=False,
        help="Force re-running jobs even if marked completed in manifest",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="swebench_verified",
        help="Dataset name or local path",
    )

    args = parser.parse_args()

    # Parse and validate conditions
    conditions = [ExperimentCondition.from_str(c) for c in args.conditions]

    orchestrator = ExperimentOrchestrator(
        experiment_id=args.experiment_id,
        tasks=args.tasks,
        conditions=conditions,
        provider=args.provider,
        worker_timeout=args.worker_timeout,
        dataset=args.dataset,
        resume=args.resume,
        force_rerun=args.force_rerun,
    )

    summary = orchestrator.run_all()
    sys.exit(0)


if __name__ == "__main__":
    main()
