"""Run Fair Pilot: Executes a fair 3-condition comparison across SWE-bench tasks.

Uses the unified, line-aligned, AST-verified DemoPatchBuilder across all conditions:
- BASELINE (1 attempt, no recovery)
- RETRY_ONLY (up to 3 blind attempts)
- FULL_DDIV (up to 3 attempts with supervisor, RCA, critic, memory, and recovery)

Preserves frozen framework files while operating in dedicated task workspaces.
Enforces TPM pacing and cumulative token budget safeguards.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import core.experiment_worker as ew
from core.experiment_record import ExperimentCondition, ExperimentConditionRecord
from core.experiment_worker import ExperimentWorker
from scripts.demo_patch_builder import DemoPatchBuilder

# Monkeypatch patch builder in experiment worker for unified, syntax-verified patch building
ew.DeterministicPatchBuilder = DemoPatchBuilder

DEFAULT_TASKS = [
    "pylint-dev__pylint-4970",
    "sympy__sympy-23413",
    "pytest-dev__pytest-8399",
    "django__django-16429",
]

DEFAULT_CONDITIONS = ["baseline", "retry_only", "full_ddiv"]


def run_pilot(
    tasks: List[str],
    conditions: List[str],
    output_dir: str = "results/fair_pilot_v22",
    max_total_tokens: int = 150000,
    pacing_seconds: float = 8.0,
):
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    results_dir = out_path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    pilot_ws_base = Path("data/workspaces/fair_pilot")
    pilot_ws_base.mkdir(parents=True, exist_ok=True)

    cumulative_tokens = 0
    total_runs = len(tasks) * len(conditions)
    current_run = 0

    print("======================================================================")
    print(" DDIV FAIR MULTI-TASK PILOT RUNNER (v2.2)")
    print(f" Tasks:             {len(tasks)} ({', '.join(tasks)})")
    print(f" Conditions:        {len(conditions)} ({', '.join(conditions)})")
    print(f" Total Planned:     {total_runs} runs")
    print(f" Token Budget Max:  {max_total_tokens} tokens")
    print(f" Pacing Delay:      {pacing_seconds}s between runs")
    print(f" Output Directory:  {out_path.resolve()}")
    print("======================================================================")

    pilot_summary: Dict[str, Any] = {
        "experiment_id": "fair_pilot_v22",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_planned_runs": total_runs,
        "runs": [],
        "budget_limit": max_total_tokens,
        "stopped_early": False,
        "stop_reason": None,
    }

    for task_id in tasks:
        for cond_str in conditions:
            current_run += 1
            print(f"\n>>> [{current_run}/{total_runs}] Starting: {task_id} | Condition: {cond_str.upper()} <<<")

            # Check token budget safety guard
            if cumulative_tokens >= max_total_tokens:
                print(f"[QUOTA GUARD] Cumulative tokens ({cumulative_tokens}) reached budget ({max_total_tokens}). Stopping pilot gracefully.")
                pilot_summary["stopped_early"] = True
                pilot_summary["stop_reason"] = f"Token budget reached: {cumulative_tokens} >= {max_total_tokens}"
                break

            existing_result = results_dir / f"result_{task_id}__{cond_str}.json"
            if existing_result.exists():
                print(f"[Pilot] Result already exists at {existing_result}, loading and skipping execution.")
                try:
                    data = json.load(existing_result.open(encoding="utf-8"))
                    metrics = data.get("metrics") or {}
                    toks = metrics.get("total_tokens", 0) if isinstance(metrics, dict) else 0
                    cumulative_tokens += toks
                    pilot_summary["runs"].append({
                        "task_id": task_id,
                        "condition": cond_str,
                        "status": str(data.get("status")),
                        "resolved": data.get("resolved"),
                        "pass_at_1": data.get("pass_at_1"),
                        "attempts": data.get("attempts"),
                        "tokens": toks,
                        "duration_seconds": data.get("execution_duration_seconds", 0.0),
                        "verdict": data.get("internal_evaluation", {}).get("verdict", "N/A"),
                        "f2p_passed": data.get("internal_evaluation", {}).get("all_f2p_passed", False),
                        "p2p_passed": data.get("internal_evaluation", {}).get("all_p2p_passed", False),
                        "error_message": data.get("error_message"),
                    })
                    continue
                except Exception as e:
                    print(f"[Pilot] Failed to load existing result: {e}. Re-running.")

            cond_enum = ExperimentCondition.FULL_DDIV if cond_str == "full_ddiv" else (
                ExperimentCondition.RETRY_ONLY if cond_str == "retry_only" else ExperimentCondition.BASELINE
            )

            task_ws_root = pilot_ws_base / f"{task_id}__{cond_str}"
            task_ws_root.mkdir(parents=True, exist_ok=True)

            log_file = out_path / "logs" / f"{task_id}__{cond_str}.log"
            log_file.parent.mkdir(parents=True, exist_ok=True)

            worker = ExperimentWorker(
                experiment_id="fair_pilot_v22",
                task_id=task_id,
                condition=cond_enum,
                workspace_root=task_ws_root,
                provider="real",
                dataset="data/swebench/test-00000-of-00001.parquet",
                log_file=log_file,
            )

            start_t = time.time()
            try:
                record: Optional[ExperimentConditionRecord] = worker.run()
            except Exception as e:
                print(f"[ERROR] Worker exception for {task_id} ({cond_str}): {e}")
                record = None
            elapsed = time.time() - start_t

            if record:
                if isinstance(record.metrics, dict):
                    run_tokens = record.metrics.get("total_tokens", 0)
                elif record.metrics:
                    run_tokens = getattr(record.metrics, "total_tokens", 0)
                else:
                    run_tokens = 0
                cumulative_tokens += run_tokens

                print(f"--- [{task_id}][{cond_str.upper()}] Result Summary ---")
                print(f" Status:          {record.status}")
                print(f" Resolved:        {record.resolved}")
                print(f" Attempts:        {record.attempts}")
                print(f" Pass@1:          {record.pass_at_1}")
                print(f" Tokens Used:     {run_tokens} (Cumulative: {cumulative_tokens})")
                print(f" Duration:        {elapsed:.2f}s")
                int_eval = record.internal_evaluation or {}
                print(f" Internal Verdict:{int_eval.get('verdict', 'N/A')}")
                print(f" F2P Passed:      {int_eval.get('all_f2p_passed', False)}")
                print(f" P2P Passed:      {int_eval.get('all_p2p_passed', False)}")

                # Save record JSON
                result_json_path = results_dir / f"result_{task_id}__{cond_str}.json"
                result_json_path.write_text(json.dumps(record.model_dump(), indent=2), encoding="utf-8")

                # Save patch
                if record.candidate_patch:
                    patch_path = results_dir / f"{task_id}__{cond_str}.patch"
                    patch_path.write_text(record.candidate_patch, encoding="utf-8")

                # Save model invocations
                invocations = []
                for att in record.attempt_history:
                    invocations.extend(att.get("model_invocations", []))
                inv_path = results_dir / f"{task_id}__{cond_str}_model_invocations.json"
                inv_path.write_text(json.dumps(invocations, indent=2), encoding="utf-8")

                pilot_summary["runs"].append({
                    "task_id": task_id,
                    "condition": cond_str,
                    "status": str(record.status),
                    "resolved": record.resolved,
                    "pass_at_1": record.pass_at_1,
                    "attempts": record.attempts,
                    "tokens": run_tokens,
                    "duration_seconds": round(elapsed, 2),
                    "verdict": int_eval.get("verdict", "N/A"),
                    "f2p_passed": int_eval.get("all_f2p_passed", False),
                    "p2p_passed": int_eval.get("all_p2p_passed", False),
                    "error_message": record.error_message,
                })
            else:
                pilot_summary["runs"].append({
                    "task_id": task_id,
                    "condition": cond_str,
                    "status": "CRASHED",
                    "resolved": False,
                    "pass_at_1": False,
                    "attempts": 0,
                    "tokens": 0,
                    "duration_seconds": round(elapsed, 2),
                    "verdict": "EXCEPTION",
                    "f2p_passed": False,
                    "p2p_passed": False,
                    "error_message": "Worker process raised unhandled exception",
                })

            # Pacing delay between runs to prevent TPM bursts
            if current_run < total_runs and not pilot_summary.get("stopped_early"):
                print(f"[Pacing] Sleeping {pacing_seconds}s to stay under Groq 8000 TPM limit...")
                time.sleep(pacing_seconds)

        if pilot_summary.get("stopped_early"):
            break

    pilot_summary["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    pilot_summary["cumulative_tokens"] = cumulative_tokens

    summary_file = out_path / "pilot_summary.json"
    summary_file.write_text(json.dumps(pilot_summary, indent=2), encoding="utf-8")
    print(f"\n[Pilot Complete] Saved summary to {summary_file}")
    return pilot_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Fair Multi-Task Pilot")
    parser.add_argument("--tasks", nargs="+", default=DEFAULT_TASKS)
    parser.add_argument("--conditions", nargs="+", default=DEFAULT_CONDITIONS)
    parser.add_argument("--output-dir", default="results/fair_pilot_v22")
    parser.add_argument("--max-total-tokens", type=int, default=140000)
    parser.add_argument("--pacing-seconds", type=float, default=8.0)
    args = parser.parse_args()

    run_pilot(
        tasks=args.tasks,
        conditions=args.conditions,
        output_dir=args.output_dir,
        max_total_tokens=args.max_total_tokens,
        pacing_seconds=args.pacing_seconds,
    )
