"""CLI process entrypoint for isolated child worker execution."""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import traceback
from pathlib import Path

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
from core.experiment_record import ConditionJobStatus, ExperimentConditionRecord
from core.experiment_worker import ExperimentWorker


class LoggerWriter:
    """Tee writer sending output to both original stream and a log file."""

    def __init__(self, original_stream, log_file_path: Path):
        self.original_stream = original_stream
        self.log_file_path = log_file_path
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file = open(self.log_file_path, "a", encoding="utf-8", buffering=1)

    def write(self, message):
        self.original_stream.write(message)
        self.log_file.write(message)

    def flush(self):
        self.original_stream.flush()
        self.log_file.flush()

    def close(self):
        try:
            self.log_file.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Isolated child worker for DDIV experiment condition.")
    parser.add_argument("--task-id", type=str, required=True, help="Task / instance ID")
    parser.add_argument("--condition", type=str, required=True, help="Experiment condition (baseline, retry_only, full_ddiv)")
    parser.add_argument("--experiment-id", type=str, required=True, help="Parent experiment ID")
    parser.add_argument("--workspace-root", type=str, required=True, help="Isolated workspace root directory")
    parser.add_argument("--output-file", type=str, required=True, help="Target JSON path for the independent result record")
    parser.add_argument("--log-file", type=str, required=True, help="Target log file for worker stdout/stderr")
    parser.add_argument("--provider", type=str, default="mock", choices=["mock", "real"], help="Model provider mode")
    parser.add_argument("--dataset", type=str, default="swebench_verified", help="Dataset name")

    args = parser.parse_args()

    log_path = Path(args.log_file).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Redirect stdout and stderr through LoggerWriter
    sys.stdout = LoggerWriter(sys.__stdout__, log_path)
    sys.stderr = LoggerWriter(sys.__stderr__, log_path)

    start_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cond = ExperimentCondition.from_str(args.condition)

    print("=" * 70)
    print(f" DDIV CHILD WORKER PROCESS [PID: {os.getpid()}]")
    print(f" Experiment ID: {args.experiment_id}")
    print(f" Task ID:       {args.task_id}")
    print(f" Condition:     {cond.value.upper()}")
    print(f" Workspace:     {args.workspace_root}")
    print(f" Provider:      {args.provider.upper()}")
    print(f" Output File:   {args.output_file}")
    print(f" Log File:      {args.log_file}")
    print("=" * 70)
    print()

    try:
        worker = ExperimentWorker(
            task_id=args.task_id,
            condition=cond,
            experiment_id=args.experiment_id,
            workspace_root=args.workspace_root,
            provider=args.provider,
            dataset=args.dataset,
            log_file=args.log_file,
        )

        record = worker.run()
        record.save_to_file(args.output_file)

        print("\n" + "=" * 70)
        print(f" CHILD WORKER FINISHED: {args.task_id} [{cond.value.upper()}]")
        print(f" Resolved: {record.resolved}")
        print(f" Attempts: {record.attempts}")
        print(f" Duration: {record.execution_duration_seconds:.2f}s")
        print("=" * 70)
        sys.exit(0)

    except Exception as exc:
        err_msg = f"Worker unhandled exception: {exc}\n{traceback.format_exc()}"
        print(f"\n[ERROR] {err_msg}", file=sys.stderr)

        # Write error record so orchestrator has an independent structured record
        error_record = ExperimentConditionRecord(
            experiment_id=args.experiment_id,
            task_id=args.task_id,
            condition=cond,
            status=ConditionJobStatus.FAILED,
            resolved=False,
            attempts=0,
            attempt_history=[],
            candidate_patch="",
            execution_duration_seconds=0.0,
            worker_pid=os.getpid(),
            worker_exit_code=1,
            log_file_path=str(args.log_file),
            workspace_path=str(args.workspace_root),
            error_message=err_msg,
            started_at=start_iso,
            completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        try:
            error_record.save_to_file(args.output_file)
        except Exception as save_err:
            print(f"[FATAL] Failed to save error record: {save_err}", file=sys.stderr)

        sys.exit(1)


if __name__ == "__main__":
    main()
