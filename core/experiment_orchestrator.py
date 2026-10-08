"""Experiment orchestrator managing isolated child workers, timeouts, crashes, and resumability."""

from __future__ import annotations

import datetime
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.conditions import ExperimentCondition
from core.experiment_record import (
    ConditionJobStatus,
    ExperimentConditionRecord,
    ExperimentManifest,
)


class ExperimentOrchestrator:
    """Orchestrates an experimental benchmark matrix across tasks and conditions using isolated child workers."""

    def __init__(
        self,
        experiment_id: str,
        tasks: List[str],
        conditions: Optional[List[ExperimentCondition | str]] = None,
        provider: str = "mock",
        worker_timeout: int = 300,
        base_dir: str | Path = "data/experiments",
        workspace_base: str | Path = "data/workspaces/experiments",
        logs_base: str | Path = "logs/experiments",
        dataset: str = "swebench_verified",
        resume: bool = True,
        force_rerun: bool = False,
    ):
        self.experiment_id = experiment_id
        self.tasks = tasks
        raw_conditions = conditions or [
            ExperimentCondition.BASELINE,
            ExperimentCondition.RETRY_ONLY,
            ExperimentCondition.FULL_DDIV,
        ]
        self.conditions = [
            c if isinstance(c, ExperimentCondition) else ExperimentCondition.from_str(c)
            for c in raw_conditions
        ]
        self.provider = provider
        self.worker_timeout = worker_timeout
        self.dataset = dataset
        self.resume = resume
        self.force_rerun = force_rerun

        # Directories
        self.base_dir = Path(base_dir).resolve() / self.experiment_id
        self.results_dir = self.base_dir / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)

        self.workspace_base = Path(workspace_base).resolve() / self.experiment_id
        self.workspace_base.mkdir(parents=True, exist_ok=True)

        self.logs_base = Path(logs_base).resolve() / self.experiment_id
        self.logs_base.mkdir(parents=True, exist_ok=True)

        self.manifest_path = self.base_dir / "manifest.json"
        self.manifest = self._init_manifest()

    def _init_manifest(self) -> ExperimentManifest:
        """Load existing manifest if resuming, or initialize a fresh one."""
        if self.manifest_path.exists() and self.resume and not self.force_rerun:
            try:
                manifest = ExperimentManifest.load_from_file(self.manifest_path)
                # Ensure all current tasks/conditions are tracked
                for t in self.tasks:
                    if t not in manifest.tasks:
                        manifest.tasks.append(t)
                for c in [cond.value for cond in self.conditions]:
                    if c not in manifest.conditions:
                        manifest.conditions.append(c)
                return manifest
            except Exception:
                pass

        manifest = ExperimentManifest(
            experiment_id=self.experiment_id,
            dataset=self.dataset,
            tasks=self.tasks,
            conditions=[c.value for c in self.conditions],
        )
        manifest.save_to_file(self.manifest_path)
        return manifest

    def _terminate_process_tree(self, proc: subprocess.Popen) -> None:
        """Safely and forcefully terminate process and all child processes."""
        pid = proc.pid
        if os.name == "nt":
            # On Windows, kill entire process tree using taskkill
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except Exception:
                proc.kill()
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except Exception:
                proc.kill()

    def run_all(self) -> Dict[str, Any]:
        """Execute all task-condition jobs in the matrix sequentially with full isolation."""
        print("=" * 70)
        print(" DDIV EXPERIMENT ORCHESTRATOR")
        print(f" Experiment ID:   {self.experiment_id}")
        print(f" Tasks:           {len(self.tasks)} {self.tasks}")
        print(f" Conditions:      {[c.value for c in self.conditions]}")
        print(f" Provider:        {self.provider.upper()}")
        print(f" Worker Timeout:  {self.worker_timeout}s")
        print(f" Resumability:    {'ENABLED' if self.resume else 'DISABLED'}")
        print(f" Results Dir:     {self.results_dir}")
        print(f" Workspace Base:  {self.workspace_base}")
        print("=" * 70)
        print()

        total_jobs = len(self.tasks) * len(self.conditions)
        job_idx = 0

        for task_id in self.tasks:
            for condition in self.conditions:
                job_idx += 1
                job_key = ExperimentManifest.job_key(task_id, condition)

                result_file = self.results_dir / f"result_{task_id}__{condition.value}.json"
                log_file = self.logs_base / f"{task_id}__{condition.value}.log"
                ws_root = self.workspace_base / f"{task_id}__{condition.value}"

                # 1. Resumability Check
                if (
                    self.resume
                    and not self.force_rerun
                    and self.manifest.is_job_completed(task_id, condition)
                    and result_file.exists()
                ):
                    print(f"[{job_idx}/{total_jobs}] SKIP (Already Completed): {task_id} [{condition.value.upper()}]")
                    continue

                print(f"[{job_idx}/{total_jobs}] DISPATCHING: {task_id} [{condition.value.upper()}]...")
                self.manifest.update_job_status(task_id, condition, ConditionJobStatus.RUNNING)
                self.manifest.save_to_file(self.manifest_path)

                # 2. Launch Isolated Child Worker Subprocess
                cmd = [
                    sys.executable,
                    "-m",
                    "scripts.run_experiment_worker",
                    "--task-id",
                    task_id,
                    "--condition",
                    condition.value,
                    "--experiment-id",
                    self.experiment_id,
                    "--workspace-root",
                    str(ws_root),
                    "--output-file",
                    str(result_file),
                    "--log-file",
                    str(log_file),
                    "--provider",
                    self.provider,
                    "--dataset",
                    self.dataset,
                ]

                job_start = time.time()
                timed_out = False
                crashed = False
                error_msg = None

                try:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=str(Path.cwd()),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

                    try:
                        proc.wait(timeout=self.worker_timeout)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        print(f"   [!] TIMEOUT: Worker exceeded deadline of {self.worker_timeout}s. Terminating process tree...")
                        self._terminate_process_tree(proc)

                except Exception as dispatch_err:
                    crashed = True
                    error_msg = f"Failed to dispatch worker process: {dispatch_err}"

                job_duration = time.time() - job_start

                # 3. Process Execution Outcome & Record Handling
                if timed_out:
                    timeout_record = ExperimentConditionRecord(
                        experiment_id=self.experiment_id,
                        task_id=task_id,
                        condition=condition,
                        status=ConditionJobStatus.TIMEOUT,
                        resolved=False,
                        attempts=0,
                        candidate_patch="",
                        execution_duration_seconds=round(job_duration, 2),
                        worker_pid=proc.pid if proc else None,
                        worker_exit_code=-9,
                        log_file_path=str(log_file),
                        workspace_path=str(ws_root),
                        error_message=f"Execution timed out after {self.worker_timeout} seconds.",
                        completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    )
                    timeout_record.save_to_file(result_file)
                    self.manifest.update_job_status(
                        task_id=task_id,
                        condition=condition,
                        status=ConditionJobStatus.TIMEOUT,
                        result_file=str(result_file),
                        resolved=False,
                        error="Timeout expired",
                        duration=job_duration,
                    )
                    print(f"   [-] RESULT: TIMEOUT ({job_duration:.2f}s)")

                elif crashed or proc.returncode != 0:
                    # Child crashed or exited non-zero
                    if not result_file.exists():
                        # Extract last lines from log file for diagnostics
                        log_snippet = ""
                        if log_file.exists():
                            try:
                                log_snippet = "\n".join(log_file.read_text(encoding="utf-8").splitlines()[-20:])
                            except Exception:
                                pass
                        error_record = ExperimentConditionRecord(
                            experiment_id=self.experiment_id,
                            task_id=task_id,
                            condition=condition,
                            status=ConditionJobStatus.FAILED,
                            resolved=False,
                            attempts=0,
                            candidate_patch="",
                            execution_duration_seconds=round(job_duration, 2),
                            worker_pid=proc.pid if proc else None,
                            worker_exit_code=proc.returncode if proc else 1,
                            log_file_path=str(log_file),
                            workspace_path=str(ws_root),
                            error_message=error_msg or f"Worker exited with code {proc.returncode}.\nLog snippet:\n{log_snippet}",
                            completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        )
                        error_record.save_to_file(result_file)

                    self.manifest.update_job_status(
                        task_id=task_id,
                        condition=condition,
                        status=ConditionJobStatus.FAILED,
                        result_file=str(result_file),
                        resolved=False,
                        error=error_msg or f"Worker exit code {proc.returncode}",
                        duration=job_duration,
                    )
                    print(f"   [-] RESULT: FAILED (Exit Code: {proc.returncode}, {job_duration:.2f}s)")

                else:
                    # Successful worker execution (completed, regardless of whether patch resolved task)
                    resolved = False
                    if result_file.exists():
                        try:
                            rec_data = json.loads(result_file.read_text(encoding="utf-8"))
                            resolved = bool(rec_data.get("resolved", False))
                        except Exception:
                            pass

                    self.manifest.update_job_status(
                        task_id=task_id,
                        condition=condition,
                        status=ConditionJobStatus.COMPLETED,
                        result_file=str(result_file),
                        resolved=resolved,
                        duration=job_duration,
                    )
                    res_tag = "RESOLVED" if resolved else "UNRESOLVED"
                    print(f"   [+] RESULT: COMPLETED [{res_tag}] in {job_duration:.2f}s")

                self.manifest.save_to_file(self.manifest_path)
                print()

        # 4. Generate Comparative Summary
        summary = self.generate_summary()
        self.manifest.summary = summary
        self.manifest.save_to_file(self.manifest_path)
        self.print_summary_table(summary)

        return summary

    def generate_summary(self) -> Dict[str, Any]:
        """Aggregate all condition result records and compute comparative research metrics."""
        summary: Dict[str, Any] = {
            "experiment_id": self.experiment_id,
            "total_tasks": len(self.tasks),
            "conditions": {},
            "task_matrix": {},
        }

        for cond in self.conditions:
            summary["conditions"][cond.value] = {
                "total_runs": 0,
                "resolved_count": 0,
                "resolution_rate": 0.0,
                "total_attempts": 0,
                "avg_attempts": 0.0,
                "avg_duration_seconds": 0.0,
                "timeouts": 0,
                "failures": 0,
            }

        for task_id in self.tasks:
            summary["task_matrix"][task_id] = {}
            for cond in self.conditions:
                c_val = cond.value
                rec_path = self.results_dir / f"result_{task_id}__{c_val}.json"
                if rec_path.exists():
                    try:
                        record = ExperimentConditionRecord.load_from_file(rec_path)
                        cond_stats = summary["conditions"][c_val]
                        cond_stats["total_runs"] += 1
                        if record.resolved:
                            cond_stats["resolved_count"] += 1
                        cond_stats["total_attempts"] += record.attempts
                        cond_stats["avg_duration_seconds"] += record.execution_duration_seconds
                        if record.status == ConditionJobStatus.TIMEOUT:
                            cond_stats["timeouts"] += 1
                        elif record.status == ConditionJobStatus.FAILED:
                            cond_stats["failures"] += 1

                        summary["task_matrix"][task_id][c_val] = {
                            "status": record.status.value,
                            "resolved": record.resolved,
                            "attempts": record.attempts,
                            "duration_seconds": record.execution_duration_seconds,
                        }
                    except Exception as err:
                        summary["task_matrix"][task_id][c_val] = {"error": str(err)}
                else:
                    summary["task_matrix"][task_id][c_val] = {"status": "MISSING"}

        # Normalize averages
        for c_val, stats in summary["conditions"].items():
            total = stats["total_runs"]
            if total > 0:
                stats["resolution_rate"] = round(stats["resolved_count"] / total, 4)
                stats["avg_attempts"] = round(stats["total_attempts"] / total, 2)
                stats["avg_duration_seconds"] = round(stats["avg_duration_seconds"] / total, 2)

        # Save summary file
        summary_path = self.base_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    def print_summary_table(self, summary: Dict[str, Any]) -> None:
        """Render a comparative markdown table in the terminal."""
        print("=" * 80)
        print(f" DDIV COMPARATIVE BENCHMARK SUMMARY  Experiment: {self.experiment_id}")
        print("=" * 80)
        print()

        headers = ["Condition", "Total", "Resolved", "Res Rate", "Avg Attempts", "Avg Latency", "Timeouts"]
        row_fmt = "{:<14} | {:<7} | {:<10} | {:<10} | {:<14} | {:<13} | {:<8}"
        print(row_fmt.format(*headers))
        print("-" * 88)

        for cond_name, stats in summary.get("conditions", {}).items():
            res_str = f"{stats.get('resolved_count', 0)}/{stats.get('total_runs', 0)}"
            rate_str = f"{stats.get('resolution_rate', 0.0) * 100:.1f}%"
            lat_str = f"{stats.get('avg_duration_seconds', 0.0):.1f}s"
            print(
                row_fmt.format(
                    cond_name.upper(),
                    stats.get("total_runs", 0),
                    res_str,
                    rate_str,
                    stats.get("avg_attempts", 0.0),
                    lat_str,
                    stats.get("timeouts", 0),
                )
            )

        print("-" * 88)
        print()
        print("Per-Task Comparative Outcomes:")
        print(f"{'Task ID':<25} | {'Baseline':<12} | {'Retry-Only':<12} | {'Full-DDIV':<12}")
        print("-" * 70)

        for task_id, c_data in summary.get("task_matrix", {}).items():
            b_str = "RESOLVED" if c_data.get("baseline", {}).get("resolved") else c_data.get("baseline", {}).get("status", "N/A")
            r_str = "RESOLVED" if c_data.get("retry_only", {}).get("resolved") else c_data.get("retry_only", {}).get("status", "N/A")
            d_str = "RESOLVED" if c_data.get("full_ddiv", {}).get("resolved") else c_data.get("full_ddiv", {}).get("status", "N/A")
            print(f"{task_id:<25} | {b_str:<12} | {r_str:<12} | {d_str:<12}")

        print("=" * 80)
