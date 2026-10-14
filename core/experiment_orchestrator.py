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

        if self.manifest_path.exists():
            if not self.force_rerun:
                raise RuntimeError(
                    f"Existing manifest found at '{self.manifest_path}'. "
                    "Cannot reset an existing experiment without --force-rerun. "
                    "Use --resume to continue or --force-rerun to explicitly overwrite."
                )
            else:
                # Backup existing manifest before overwrite
                bak_path = self.manifest_path.with_suffix(f".bak.{int(time.time())}.json")
                try:
                    import shutil
                    shutil.copy2(self.manifest_path, bak_path)
                    print(f"   [!] WARNING: Overwriting existing manifest with --force-rerun. Backed up to {bak_path.name}")
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

                # 1. Resumability & Consistency Check
                is_consistent_completed = False
                if self.manifest.is_job_completed(task_id, condition) and result_file.exists():
                    try:
                        rec_data = json.loads(result_file.read_text(encoding="utf-8"))
                        if rec_data.get("status") == ConditionJobStatus.COMPLETED.value:
                            is_consistent_completed = True
                    except Exception:
                        is_consistent_completed = False

                if self.resume and not self.force_rerun and is_consistent_completed:
                    print(f"[{job_idx}/{total_jobs}] SKIP (Already Completed & Consistent): {task_id} [{condition.value.upper()}]")
                    continue
                elif self.resume and not self.force_rerun and self.manifest.is_job_completed(task_id, condition) and not is_consistent_completed:
                    print(f"   [!] WARNING: Inconsistency detected for {task_id} [{condition.value.upper()}]. Manifest indicates COMPLETED, but result file is missing or invalid. Re-dispatching job.")

                # If a previous result file exists from a prior attempt, archive it to history before re-dispatching
                if result_file.exists() and (self.force_rerun or not is_consistent_completed):
                    history_dir = self.base_dir / "history"
                    history_dir.mkdir(parents=True, exist_ok=True)
                    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
                    archived_path = history_dir / f"{result_file.stem}.attempt_{timestamp}.json"
                    counter = 1
                    while archived_path.exists():
                        archived_path = history_dir / f"{result_file.stem}.attempt_{timestamp}_{counter}.json"
                        counter += 1
                    try:
                        import shutil
                        shutil.copy2(result_file, archived_path)
                        print(f"   [*] Preserved prior attempt output to history/{archived_path.name}")
                    except Exception as arch_err:
                        print(f"   [!] Failed to archive prior output: {arch_err}")

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
                    job_final_status = ConditionJobStatus.TIMEOUT
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
                        completed_at=datetime.timezone.utc if False else datetime.datetime.now(datetime.timezone.utc).isoformat(),
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

                elif result_file.exists():
                    # Worker produced a structured record file
                    rec_status = ConditionJobStatus.COMPLETED
                    resolved = False
                    error_text = error_msg or (f"Worker exited with code {proc.returncode}" if proc.returncode != 0 else None)
                    try:
                        record_data = json.loads(result_file.read_text(encoding="utf-8"))
                        status_str = record_data.get("status")
                        if status_str and status_str in ConditionJobStatus.__members__:
                            rec_status = ConditionJobStatus(status_str)
                        resolved = bool(record_data.get("resolved", False))
                        if record_data.get("error_message"):
                            error_text = record_data.get("error_message")
                    except Exception as parse_err:
                        print(f"   [!] Failed to parse worker result file: {parse_err}")

                    # If returncode indicates quota or provider error but status was not set
                    if proc.returncode == 3 and rec_status == ConditionJobStatus.COMPLETED:
                        rec_status = ConditionJobStatus.ABORTED_QUOTA_EXHAUSTED
                    elif proc.returncode == 2 and rec_status == ConditionJobStatus.COMPLETED:
                        rec_status = ConditionJobStatus.PROVIDER_ERROR
                    elif proc.returncode != 0 and rec_status == ConditionJobStatus.COMPLETED:
                        rec_status = ConditionJobStatus.FAILED

                    job_final_status = rec_status

                    self.manifest.update_job_status(
                        task_id=task_id,
                        condition=condition,
                        status=job_final_status,
                        result_file=str(result_file),
                        resolved=resolved,
                        error=error_text,
                        duration=job_duration,
                    )

                    if job_final_status == ConditionJobStatus.COMPLETED:
                        res_tag = "RESOLVED" if resolved else "UNRESOLVED"
                        print(f"   [+] RESULT: COMPLETED [{res_tag}] in {job_duration:.2f}s")
                    elif job_final_status == ConditionJobStatus.ABORTED_QUOTA_EXHAUSTED:
                        print(f"   [-] RESULT: ABORTED_QUOTA_EXHAUSTED (Exit Code: {proc.returncode}, {job_duration:.2f}s)")
                    elif job_final_status == ConditionJobStatus.PROVIDER_ERROR:
                        print(f"   [-] RESULT: PROVIDER_ERROR (Exit Code: {proc.returncode}, {job_duration:.2f}s)")
                    else:
                        print(f"   [-] RESULT: FAILED (Exit Code: {proc.returncode}, {job_duration:.2f}s)")

                else:
                    # Child crashed or exited without producing a result file
                    log_snippet = ""
                    if log_file.exists():
                        try:
                            log_snippet = "\n".join(log_file.read_text(encoding="utf-8").splitlines()[-20:])
                        except Exception:
                            pass

                    ret_code = proc.returncode if proc else 1
                    if ret_code == 3:
                        job_final_status = ConditionJobStatus.ABORTED_QUOTA_EXHAUSTED
                    elif ret_code == 2:
                        job_final_status = ConditionJobStatus.PROVIDER_ERROR
                    else:
                        job_final_status = ConditionJobStatus.FAILED

                    error_record = ExperimentConditionRecord(
                        experiment_id=self.experiment_id,
                        task_id=task_id,
                        condition=condition,
                        status=job_final_status,
                        resolved=False,
                        workflow_completed=False,
                        patch_generated=False,
                        patch_applied=False,
                        attempts=0,
                        candidate_patch="",
                        execution_duration_seconds=round(job_duration, 2),
                        worker_pid=proc.pid if proc else None,
                        worker_exit_code=ret_code,
                        log_file_path=str(log_file),
                        workspace_path=str(ws_root),
                        error_message=error_msg or f"Worker exited with code {ret_code}.\nLog snippet:\n{log_snippet}",
                        completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    )
                    error_record.save_to_file(result_file)

                    self.manifest.update_job_status(
                        task_id=task_id,
                        condition=condition,
                        status=job_final_status,
                        result_file=str(result_file),
                        resolved=False,
                        error=error_msg or f"Worker exit code {ret_code}",
                        duration=job_duration,
                    )
                    print(f"   [-] RESULT: {job_final_status.value} (Exit Code: {ret_code}, {job_duration:.2f}s)")

                self.manifest.save_to_file(self.manifest_path)
                print()

                # If quota exhaustion occurred, stop further jobs to prevent corrupted/incomplete condition comparisons
                if job_final_status == ConditionJobStatus.ABORTED_QUOTA_EXHAUSTED:
                    print("   [!] CRITICAL: Job aborted due to quota exhaustion. Halting further live jobs to preserve comparable experimental conditions.")
                    break

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
                "completed_runs": 0,
                "resolved_count": 0,
                "resolution_rate": 0.0,
                "total_attempts": 0,
                "avg_attempts": 0.0,
                "avg_duration_seconds": 0.0,
                "timeouts": 0,
                "failures": 0,
                "provider_errors": 0,
                "quota_exhausted": 0,
                "degraded_runs": 0,
                "patches_generated": 0,
                "patches_applied": 0,
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

                        if record.status == ConditionJobStatus.COMPLETED:
                            cond_stats["completed_runs"] += 1
                        elif record.status == ConditionJobStatus.TIMEOUT:
                            cond_stats["timeouts"] += 1
                        elif record.status == ConditionJobStatus.FAILED:
                            cond_stats["failures"] += 1
                        elif record.status == ConditionJobStatus.PROVIDER_ERROR:
                            cond_stats["provider_errors"] += 1
                        elif record.status == ConditionJobStatus.ABORTED_QUOTA_EXHAUSTED:
                            cond_stats["quota_exhausted"] += 1

                        if getattr(record, "degraded_execution", False):
                            cond_stats["degraded_runs"] += 1

                        if record.patch_generated:
                            cond_stats["patches_generated"] += 1
                        if record.patch_applied:
                            cond_stats["patches_applied"] += 1

                        summary["task_matrix"][task_id][c_val] = {
                            "status": record.status.value,
                            "resolved": record.resolved,
                            "workflow_completed": record.workflow_completed,
                            "degraded_execution": getattr(record, "degraded_execution", False),
                            "degraded_reason": getattr(record, "degraded_reason", None),
                            "patch_generated": record.patch_generated,
                            "patch_applied": record.patch_applied,
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
        print("=" * 96)
        print(f" DDIV COMPARATIVE BENCHMARK SUMMARY  Experiment: {self.experiment_id}")
        print("=" * 96)
        print()

        headers = ["Condition", "Total", "Done", "Resolved", "Res Rate", "Quota Exh", "Prov Err", "Avg Latency", "Timeouts"]
        row_fmt = "{:<12} | {:<5} | {:<5} | {:<9} | {:<8} | {:<9} | {:<8} | {:<11} | {:<8}"
        print(row_fmt.format(*headers))
        print("-" * 96)

        for cond_name, stats in summary.get("conditions", {}).items():
            res_str = f"{stats.get('resolved_count', 0)}/{stats.get('total_runs', 0)}"
            rate_str = f"{stats.get('resolution_rate', 0.0) * 100:.1f}%"
            lat_str = f"{stats.get('avg_duration_seconds', 0.0):.1f}s"
            print(
                row_fmt.format(
                    cond_name.upper(),
                    stats.get("total_runs", 0),
                    stats.get("completed_runs", 0),
                    res_str,
                    rate_str,
                    stats.get("quota_exhausted", 0),
                    stats.get("provider_errors", 0),
                    lat_str,
                    stats.get("timeouts", 0),
                )
            )

        print("-" * 96)
        print()
        print("Per-Task Comparative Outcomes:")
        print(f"{'Task ID':<25} | {'Baseline':<25} | {'Retry-Only':<25} | {'Full-DDIV':<25}")
        print("-" * 105)

        for task_id, c_data in summary.get("task_matrix", {}).items():
            b_str = "RESOLVED" if c_data.get("baseline", {}).get("resolved") else c_data.get("baseline", {}).get("status", "N/A")
            r_str = "RESOLVED" if c_data.get("retry_only", {}).get("resolved") else c_data.get("retry_only", {}).get("status", "N/A")
            d_res = c_data.get("full_ddiv", {})
            if d_res.get("resolved"):
                d_str = "RESOLVED" + (" (DEGRADED)" if d_res.get("degraded_execution") else "")
            else:
                st = d_res.get("status", "N/A")
                d_str = st + (" (DEGRADED)" if d_res.get("degraded_execution") and st == "COMPLETED" else "")
            print(f"{task_id:<25} | {b_str:<25} | {r_str:<25} | {d_str:<25}")

        print("=" * 96)
