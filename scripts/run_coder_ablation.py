"""Ablation orchestrator for DDIV Coder Model Ablation.

Executes a controlled comparison between Coder A (Groq GPT-OSS 120b) and
Coder B (Gemini 3.8 Flash) under FULL_DDIV on the 3 Batch 1 tasks.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(Path(project_root) / ".env", override=True)

from core.conditions import ExperimentCondition
from core.experiment_record import ConditionJobStatus


class CoderAblationOrchestrator:
    """Manages isolated sequential execution of coder ablation jobs."""

    def __init__(
        self,
        experiment_id: str = "coder_ablation_v21_20261012",
        tasks: Optional[List[str]] = None,
        coders: Optional[List[str]] = None,
        condition: str = "full_ddiv",
        provider: str = "mock",
        worker_timeout: int = 600,
        dataset: str = "data/swebench/test-00000-of-00001.parquet",
        resume: bool = True,
        force_rerun: bool = False,
        base_dir: str | Path = "data/experiments",
        workspace_base: str | Path = "data/workspaces/experiments",
        logs_base: str | Path = "logs/experiments",
    ):
        self.experiment_id = experiment_id
        self.tasks = tasks or [
            "pylint-dev__pylint-6903",
            "mwaskom__seaborn-3187",
            "pydata__xarray-7393",
        ]
        self.coders = coders or ["coder_a", "coder_b"]
        self.condition = condition
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

    def _init_manifest(self) -> Dict[str, Any]:
        """Load or create ablation manifest."""
        if self.manifest_path.exists() and self.resume and not self.force_rerun:
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        if self.manifest_path.exists() and self.force_rerun:
            bak_path = self.manifest_path.with_suffix(f".bak.{int(time.time())}.json")
            try:
                import shutil
                shutil.copy2(self.manifest_path, bak_path)
            except Exception:
                pass

        manifest = {
            "experiment_id": self.experiment_id,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tasks": self.tasks,
            "coders": self.coders,
            "condition": self.condition,
            "provider": self.provider,
            "jobs": {},
        }
        for t in self.tasks:
            for c in self.coders:
                job_key = f"{t}__{c}"
                manifest["jobs"][job_key] = {
                    "task_id": t,
                    "coder_variant": c,
                    "status": "PENDING",
                    "resolved": False,
                    "duration": 0.0,
                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }

        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        return manifest

    def save_manifest(self):
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2)

    def _kill_process_tree(self, proc: subprocess.Popen, pid: int) -> None:
        if sys.platform == "win32":
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            except Exception:
                proc.kill()
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except Exception:
                proc.kill()

    def run_all(self) -> Dict[str, Any]:
        print("=" * 80)
        print(" DDIV CODER MODEL ABLATION ORCHESTRATOR")
        print(f" Experiment ID:   {self.experiment_id}")
        print(f" Tasks ({len(self.tasks)}):     {self.tasks}")
        print(f" Coders:          {self.coders} (coder_a: GPT-OSS 120b | coder_b: Gemini 3.8 Flash)")
        print(f" Condition:       {self.condition.upper()}")
        print(f" Provider Mode:   {self.provider.upper()}")
        print(f" Worker Timeout:  {self.worker_timeout}s")
        print(f" Results Dir:     {self.results_dir}")
        print("=" * 80)
        print()

        total_jobs = len(self.tasks) * len(self.coders)
        job_idx = 0

        for task_id in self.tasks:
            for coder_var in self.coders:
                job_idx += 1
                job_key = f"{task_id}__{coder_var}"
                result_file = self.results_dir / f"result_{task_id}__{coder_var}.json"
                log_file = self.logs_base / f"{task_id}__{coder_var}.log"
                ws_root = self.workspace_base / f"{task_id}__{coder_var}"

                # 1. Resumability & Consistency Check
                is_consistent_completed = False
                job_entry = self.manifest["jobs"].get(job_key, {})
                if job_entry.get("status") == "COMPLETED" and result_file.exists():
                    try:
                        rec_data = json.loads(result_file.read_text(encoding="utf-8"))
                        if rec_data.get("status") == "COMPLETED":
                            is_consistent_completed = True
                    except Exception:
                        is_consistent_completed = False

                if self.resume and not self.force_rerun and is_consistent_completed:
                    print(f"[{job_idx}/{total_jobs}] SKIP (Already Completed): {task_id} [{coder_var.upper()}]")
                    continue
                elif self.resume and not self.force_rerun and job_entry.get("status") == "COMPLETED" and not is_consistent_completed:
                    print(f"   [!] WARNING: Inconsistency detected for {job_key}. Manifest indicates COMPLETED, but result file is missing/invalid. Re-dispatching.")

                # Archive previous output to history if re-dispatching
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

                print(f"[{job_idx}/{total_jobs}] DISPATCHING: {task_id} [{coder_var.upper()}]...")
                self.manifest["jobs"][job_key]["status"] = "RUNNING"
                self.manifest["jobs"][job_key]["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                self.save_manifest()

                cmd = [
                    sys.executable,
                    "-m",
                    "scripts.run_coder_ablation_worker",
                    "--task-id",
                    task_id,
                    "--coder-variant",
                    coder_var,
                    "--condition",
                    self.condition,
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
                proc = None
                ret_code = -1
                timed_out = False

                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                    )
                    ret_code = proc.wait(timeout=self.worker_timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    print(f"   [-] TIMEOUT: Worker exceeded timeout of {self.worker_timeout}s. Terminating process tree...")
                    if proc:
                        self._kill_process_tree(proc, proc.pid)
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                    ret_code = -1
                except Exception as exc:
                    print(f"   [-] ERROR: Failed to execute child worker: {exc}")
                    ret_code = -1

                job_duration = time.time() - job_start

                # Parse result
                job_final_status = "FAILED"
                resolved = False
                error_msg = None

                if timed_out:
                    job_final_status = "TIMEOUT"
                    error_msg = f"Worker process timed out after {self.worker_timeout}s."
                elif ret_code == 0 and result_file.exists():
                    try:
                        rec_data = json.loads(result_file.read_text(encoding="utf-8"))
                        st_val = rec_data.get("status", "COMPLETED")
                        job_final_status = st_val
                        resolved = bool(rec_data.get("resolved", False))
                        error_msg = rec_data.get("error_message")
                    except Exception as err:
                        job_final_status = "FAILED"
                        error_msg = f"Failed to parse result file: {err}"
                elif ret_code == 3:
                    job_final_status = "ABORTED_QUOTA_EXHAUSTED"
                    error_msg = "Child worker aborted due to API quota exhaustion."
                elif ret_code == 2:
                    job_final_status = "PROVIDER_ERROR"
                    error_msg = "Child worker encountered an unrecoverable provider error."
                else:
                    job_final_status = "FAILED"
                    error_msg = f"Child worker exited with nonzero code {ret_code}."

                self.manifest["jobs"][job_key] = {
                    "task_id": task_id,
                    "coder_variant": coder_var,
                    "status": job_final_status,
                    "resolved": resolved,
                    "duration": round(job_duration, 2),
                    "exit_code": ret_code,
                    "error": error_msg,
                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                self.save_manifest()

                res_tag = "RESOLVED" if resolved else "UNRESOLVED"
                print(f"   [+] RESULT: {job_final_status} [{res_tag}] in {job_duration:.2f}s (Exit Code: {ret_code})\n")

                if job_final_status == "ABORTED_QUOTA_EXHAUSTED":
                    print("   [!] CRITICAL: Ablation job aborted due to quota exhaustion. Halting further runs to preserve experimental comparability.")
                    break

        print("=" * 80)
        print(" ABLATION EXECUTION COMPLETED")
        print("=" * 80)
        return self.manifest


def main():
    parser = argparse.ArgumentParser(description="Run DDIV Coder Model Ablation.")
    parser.add_argument("--experiment-id", type=str, default="coder_ablation_v21_20261012")
    parser.add_argument("--tasks", nargs="+", default=["pylint-dev__pylint-6903", "mwaskom__seaborn-3187", "pydata__xarray-7393"])
    parser.add_argument("--coders", nargs="+", default=["coder_a", "coder_b"])
    parser.add_argument("--condition", type=str, default="full_ddiv")
    parser.add_argument("--provider", type=str, default="mock", choices=["mock", "real"])
    parser.add_argument("--worker-timeout", type=int, default=600)
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", action="store_false", dest="resume")
    parser.add_argument("--force-rerun", action="store_true", default=False)
    parser.add_argument("--dataset", type=str, default="data/swebench/test-00000-of-00001.parquet")
    parser.add_argument("--dry-run", action="store_true", help="Print matrix and exit without running jobs")

    args = parser.parse_args()

    if args.dry_run:
        print("DDIV CODER ABLATION DRY RUN:")
        print(f"Experiment ID: {args.experiment_id}")
        print(f"Tasks:         {args.tasks}")
        print(f"Coders:        {args.coders}")
        print(f"Condition:     {args.condition}")
        print(f"Provider:      {args.provider}")
        print(f"Timeout:       {args.worker_timeout}s")
        print(f"Total jobs:    {len(args.tasks) * len(args.coders)}")
        sys.exit(0)

    orch = CoderAblationOrchestrator(
        experiment_id=args.experiment_id,
        tasks=args.tasks,
        coders=args.coders,
        condition=args.condition,
        provider=args.provider,
        worker_timeout=args.worker_timeout,
        dataset=args.dataset,
        resume=args.resume,
        force_rerun=args.force_rerun,
    )
    orch.run_all()


if __name__ == "__main__":
    main()
