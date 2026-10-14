"""Run Local Ollama Comparison Benchmark.

Executes a controlled comparison across selected SWE-bench tasks (pylint-6903,
pylint-4970, sympy-23413) using local Ollama (qwen2.5-coder:7b) as the Coder
agent under BASELINE, RETRY_ONLY, and FULL_DDIV.

Preserves all frozen framework files, historical results, and checkpoints.
Outputs results strictly under results/local_ollama_coder/.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Force DDIV_CODER_PROVIDER=ollama for this runner
os.environ["DDIV_CODER_PROVIDER"] = "ollama"

from dotenv import load_dotenv
load_dotenv(Path(project_root) / ".env", override=False)

import core.experiment_worker as ew
from core.experiment_record import ExperimentCondition, ExperimentConditionRecord
from core.experiment_worker import ExperimentWorker
from evaluation.swebench_loader import SWEBenchLoader
from scripts.demo_patch_builder import DemoPatchBuilder
from scripts.ollama_coder_adapter import register_ollama_provider
from scripts.v2_2_recovery_manager import FailureDisambiguator, V22SupervisedWorker

# Ensure unified, syntax-verified patch builder and Ollama registration
ew.DeterministicPatchBuilder = DemoPatchBuilder
register_ollama_provider()

DEFAULT_TASKS = [
    "pylint-dev__pylint-6903",
    "pylint-dev__pylint-4970",
    "sympy__sympy-23413",
]

DEFAULT_CONDITIONS = ["baseline", "retry_only", "full_ddiv"]

TASK_BASE_COMMITS = {
    "pylint-dev__pylint-6903": "ca80f03a43bc39e4cc2c67dc99817b3c9f13b8a6",
    "pylint-dev__pylint-4970": "40cc2ffd7887959157aaf469e09585ec2be7f528",
    "sympy__sympy-23413": "10de1a18a0efac0b19b611e40c928250dda688bf",
}


def prepare_task_seed(workspace_root: Path, task_id: str):
    """Seed workspace from local cache or pre-existing eval workspaces when available."""
    cached_paths = [
        Path(f"data/workspaces/demo/eval_ws/{task_id}-eval"),
        Path(f"data/workspaces/fair_pilot/{task_id}__baseline/eval_ws/{task_id}-eval"),
        Path(f"data/workspaces/fair_pilot/{task_id}__full_ddiv/eval_ws/{task_id}-eval"),
        Path(f"data/workspaces/fair_5bug_v22/{task_id}__baseline/eval_ws/{task_id}-eval"),
        Path(f"data/workspaces/fair_5bug_v22/{task_id}__full_ddiv/eval_ws/{task_id}-eval"),
        Path(f"data/workspaces/experiments/benchmark_v2_1_batch_1/{task_id}__full_ddiv/eval_ws/{task_id}-eval"),
        Path(f"data/workspaces/experiments/validation_3tasks_v21_20261009/{task_id}__baseline/eval_ws/{task_id}-eval"),
    ]
    agent_target = workspace_root / "agent_ws" / f"{task_id}-agent"
    eval_target = workspace_root / "eval_ws" / f"{task_id}-eval"

    for src in cached_paths:
        if src.exists() and (src / ".git").exists():
            for target in (agent_target, eval_target):
                if not (target / ".git").exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        shutil.rmtree(target, ignore_errors=True)
                    shutil.copytree(src, target)
                    print(f"[Seed] Copied {src.name} to {target}")
            break

    # Ensure pristine state at exact base commit
    base_commit = TASK_BASE_COMMITS.get(task_id)
    if base_commit:
        for target in (agent_target, eval_target):
            if target.exists() and (target / ".git").exists():
                subprocess.run(["git", "reset", "--hard", base_commit], cwd=target, capture_output=True)
                subprocess.run(["git", "clean", "-fd"], cwd=target, capture_output=True)


def generate_reports(summary: Dict[str, Any], output_dir: Path, dataset: Optional[str] = None):
    """Generate CSV, Markdown summary, and high-resolution chart from completed records."""
    runs = summary.get("runs", [])
    if not runs:
        return

    # Load frozen ground truth for accurate denominators
    gt_lookup: Dict[str, Any] = {}
    ds_path = dataset or "data/swebench/test-00000-of-00001.parquet"
    if Path(ds_path).exists():
        try:
            loader = SWEBenchLoader()
            for rec in loader.load_from_file(ds_path):
                gt_lookup[rec.task.instance_id] = rec.ground_truth
        except Exception as exc:
            print(f"[!] Warning: Could not load ground truth from {ds_path}: {exc}")

    # 1. Generate CSV
    csv_path = output_dir / "local_ollama_comparison.csv"
    fieldnames = [
        "task_id", "condition", "status", "resolved", "attempts", "pass_at_1",
        "patch_generated", "patch_applied", "f2p_passed", "f2p_total",
        "p2p_passed", "p2p_total", "execution_duration_seconds",
        "total_tokens", "prompt_tokens", "completion_tokens", "coder_model", "failure_category"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in runs:
            task_id = r.get("task_id", "")
            gt = gt_lookup.get(task_id)
            gt_f2p = len(gt.fail_to_pass) if gt else None
            gt_p2p = len(gt.pass_to_pass) if gt else None

            internal_eval = r.get("internal_evaluation") or {}
            f2p_res = internal_eval.get("fail_to_pass_results") or {}
            p2p_res = internal_eval.get("pass_to_pass_results") or {}
            is_unapplied = (
                internal_eval.get("candidate_patch_applied") is False
                or "Candidate patch application failed" in str(internal_eval.get("verdict", ""))
            )

            if is_unapplied:
                f2p_p = 0
                f2p_t = gt_f2p if gt_f2p is not None else 0
                p2p_p = 0
                p2p_t = gt_p2p if gt_p2p is not None else 0
            else:
                if isinstance(f2p_res, dict) and f2p_res:
                    f2p_p = sum(1 for v in f2p_res.values() if v is True)
                    f2p_t = len(f2p_res)
                else:
                    f2p_p = len(r.get("tests_passed_fail_to_pass") or [])
                    f2p_t = len(r.get("tests_total_fail_to_pass") or []) or (gt_f2p or 0)

                if isinstance(p2p_res, dict) and p2p_res:
                    p2p_p = sum(1 for v in p2p_res.values() if v is True)
                    p2p_t = len(p2p_res)
                else:
                    p2p_p = len(r.get("tests_passed_pass_to_pass") or [])
                    p2p_t = len(r.get("tests_total_pass_to_pass") or []) or (gt_p2p or 0)

            history = r.get("attempt_history") or []
            last_hist = history[-1] if history else {}
            fd = last_hist.get("failure_detector") or {}
            fail_cat = "RESOLVED" if r.get("resolved") else (
                fd.get("granular_failure_type")
                or fd.get("candidate_failure_type")
                or last_hist.get("coder_error_code")
                or last_hist.get("failure_category")
                or "FAIL"
            )

            metrics = r.get("metrics") or {}
            tot_tokens = r.get("total_tokens") or metrics.get("total_tokens", 0)
            p_tokens = r.get("prompt_tokens") or metrics.get("input_tokens", 0)
            c_tokens = r.get("completion_tokens") or metrics.get("output_tokens", 0)

            writer.writerow({
                "task_id": r.get("task_id"),
                "condition": r.get("condition"),
                "status": r.get("status"),
                "resolved": r.get("resolved"),
                "attempts": r.get("attempts"),
                "pass_at_1": r.get("attempts") == 1 and r.get("resolved"),
                "patch_generated": r.get("patch_generated"),
                "patch_applied": r.get("patch_applied"),
                "f2p_passed": f2p_p,
                "f2p_total": f2p_t,
                "p2p_passed": p2p_p,
                "p2p_total": p2p_t,
                "execution_duration_seconds": round(r.get("execution_duration_seconds", 0.0), 2),
                "total_tokens": tot_tokens,
                "prompt_tokens": p_tokens,
                "completion_tokens": c_tokens,
                "coder_model": r.get("coder_model", "qwen2.5-coder:7b"),
                "failure_category": fail_cat,
            })
    print(f"[+] Comparison CSV written to: {csv_path}")

    # 2. Compute aggregate metrics by condition
    cond_stats: Dict[str, Dict[str, Any]] = {}
    for c in ["baseline", "retry_only", "full_ddiv"]:
        c_runs = [r for r in runs if r.get("condition") == c]
        completed = [r for r in c_runs if r.get("status") in ("COMPLETED", "RESOLVED")]
        resolved = [r for r in completed if r.get("resolved") is True]
        pass1 = [r for r in resolved if r.get("attempts") == 1]
        tokens = [
            (r.get("metrics") or {}).get("total_tokens", r.get("total_tokens", 0))
            for r in completed
        ]
        duration = [r.get("execution_duration_seconds", 0.0) for r in completed]
        cond_stats[c] = {
            "total_planned": len([t for t in summary.get("tasks", [])]),
            "completed": len(completed),
            "resolved": len(resolved),
            "pass_at_1": len(pass1),
            "avg_tokens": round(sum(tokens) / len(tokens), 1) if tokens else 0,
            "avg_duration": round(sum(duration) / len(duration), 1) if duration else 0,
        }

    # 3. Generate Markdown Report
    md_path = output_dir / "local_ollama_report.md"
    md_lines = [
        "# DDIV Controlled Pilot Report: Local Ollama Coder Evaluation",
        "",
        "> [!NOTE]",
        "> **Evaluation Framework Scope:**",
        "> All evaluations reported herein are **Tier-1 Internal Reproductions** using SWE-bench Verified task data,",
        "> exact target FAIL_TO_PASS test execution, and PASS_TO_PASS regression suites in isolated repository environments.",
        "> These represent controlled experimental metrics under DDIV and are not official SWE-bench leaderboard submissions.",
        "",
        "## 1. Experimental Configuration",
        f"- **Coder Model (Treatment):** `qwen2.5-coder:7b` (Local Ollama at `{summary.get('ollama_base_url')}`)",
        "- **Zero Fallback Guarantee:** Pure local Coder execution without cloud API fallback",
        "- **Locator Agent:** `gemini-3.1-flash-lite`",
        "- **Test Understanding / Supervisor / Critic / Tester:** `qwen/qwen3.8-27b` (Groq API)",
        "- **Patch Builder:** Unified line-aligned, AST syntax-verified `DemoPatchBuilder`",
        f"- **Execution Timestamp:** `{summary.get('started_at')}`",
        "",
        "## 2. Condition Comparison Summary",
        "",
        "| Condition | Completed Runs | Tier-1 Resolved | Resolution Rate | Pass@1 Count | Avg Tokens | Avg Wall-Clock (s) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for c in ["baseline", "retry_only", "full_ddiv"]:
        st = cond_stats[c]
        denom = st["completed"]
        res = st["resolved"]
        rate = f"{(res / denom * 100):.1f}%" if denom > 0 else "N/A"
        md_lines.append(
            f"| **{c.upper()}** | {denom}/{st['total_planned']} | {res}/{denom} | **{rate}** | {st['pass_at_1']} | {st['avg_tokens']:,} | {st['avg_duration']:.1f}s |"
        )

    md_lines.extend([
        "",
        "## 3. Detailed Per-Run Outcomes",
        "",
        "| Task ID | Condition | Status | Resolved | Attempts | F2P Passed | P2P Passed | Tokens | Latency (s) | Failure / Stage |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ])

    for r in runs:
        task_id = r.get("task_id", "")
        gt = gt_lookup.get(task_id)
        gt_f2p = len(gt.fail_to_pass) if gt else None
        gt_p2p = len(gt.pass_to_pass) if gt else None

        internal_eval = r.get("internal_evaluation") or {}
        f2p_str, p2p_str = FailureDisambiguator.format_test_counts(internal_eval, gt_f2p, gt_p2p)

        history = r.get("attempt_history") or []
        last_hist = history[-1] if history else {}
        fd = last_hist.get("failure_detector") or {}
        fail_cat = "RESOLVED" if r.get("resolved") else (
            fd.get("granular_failure_type")
            or fd.get("candidate_failure_type")
            or last_hist.get("coder_error_code")
            or last_hist.get("failure_category")
            or "FAIL"
        )
        res_sym = "✅ **YES**" if r.get("resolved") else "❌ NO"

        metrics = r.get("metrics") or {}
        tot_tokens = r.get("total_tokens") or metrics.get("total_tokens", 0)
        cond_str = str(r.get("condition")).split(".")[-1].upper()
        status_str = str(r.get("status")).split(".")[-1].upper()
        fail_cat_str = str(fail_cat).split(".")[-1]

        md_lines.append(
            f"| `{r.get('task_id')}` | `{cond_str}` | {status_str} | {res_sym} | {r.get('attempts')} | {f2p_str} | {p2p_str} | {tot_tokens:,} | {r.get('execution_duration_seconds', 0.0):.1f}s | `{fail_cat_str}` |"
        )

    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[+] Comparison Markdown Report written to: {md_path}")

    # 4. Generate Poster Chart using Matplotlib
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        conditions_labels = ["BASELINE", "RETRY_ONLY", "FULL_DDIV"]
        resolved_counts = [cond_stats[c.lower()]["resolved"] for c in conditions_labels]
        denominators = [cond_stats[c.lower()]["completed"] for c in conditions_labels]
        pass1_counts = [cond_stats[c.lower()]["pass_at_1"] for c in conditions_labels]

        x = range(len(conditions_labels))
        width = 0.35

        fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
        fig.patch.set_facecolor("#FFFFFF")
        ax.set_facecolor("#FAFAFA")

        rects1 = ax.bar([i - width/2 for i in x], resolved_counts, width, label="Total Resolved (Tier-1)", color="#2563EB", edgecolor="#1D4ED8")
        rects2 = ax.bar([i + width/2 for i in x], pass1_counts, width, label="Pass@1 Resolved", color="#10B981", edgecolor="#059669")

        ax.set_ylabel("Resolved Tasks Count", fontsize=12, fontweight="bold")
        ax.set_title("DDIV Software Repair Performance: Local Ollama (qwen2.5-coder:7b)\nControlled 3-Bug Benchmark (Completed Runs Denominators)", fontsize=13, fontweight="bold", pad=15)
        ax.set_xticks(list(x))
        ax.set_xticklabels([f"{cond}\n(N={denominators[i]})" for i, cond in enumerate(conditions_labels)], fontsize=11, fontweight="bold")
        ax.set_ylim(0, max(max(denominators or [3]), 3) + 0.8)
        ax.legend(frameon=True, facecolor="#FFFFFF", edgecolor="#E5E7EB", loc="upper left")
        ax.grid(axis="y", linestyle="--", alpha=0.5)

        # Value annotations
        def autolabel(rects, totals):
            for i, rect in enumerate(rects):
                h = rect.get_height()
                tot = totals[i]
                pct = f"({(h/tot*100):.0f}%)" if tot > 0 else ""
                ax.annotate(f"{int(h)} {pct}",
                            xy=(rect.get_x() + rect.get_width() / 2, h),
                            xytext=(0, 4),  # 4 points vertical offset
                            textcoords="offset points",
                            ha="center", va="bottom", fontsize=10, fontweight="bold")

        autolabel(rects1, denominators)
        autolabel(rects2, denominators)

        plt.tight_layout()
        chart_path = output_dir / "condition_resolution_chart.png"
        plt.savefig(chart_path, dpi=300)
        plt.close(fig)
        print(f"[+] High-resolution comparison chart saved to: {chart_path}")
    except Exception as exc:
        print(f"[!] Chart generation warning: {exc}")


def run_comparison(
    tasks: List[str],
    conditions: List[str],
    output_dir: str = "results/local_ollama_coder",
    model_id: str = "qwen2.5-coder:7b",
    base_url: str = "http://localhost:11434",
    timeout_seconds: int = 240,
    dataset: str = "data/swebench/test-00000-of-00001.parquet",
    force_rerun: bool = False,
):
    os.environ["OLLAMA_MODEL"] = model_id
    os.environ["OLLAMA_BASE_URL"] = base_url
    os.environ["OLLAMA_TIMEOUT_SECONDS"] = str(timeout_seconds)

    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    results_dir = out_path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    ws_base = Path("data/workspaces/local_ollama_coder").resolve()
    ws_base.mkdir(parents=True, exist_ok=True)

    logs_base = Path("logs/local_ollama_coder").resolve()
    logs_base.mkdir(parents=True, exist_ok=True)

    total_runs = len(tasks) * len(conditions)
    current_run = 0

    print("=" * 75)
    print(" DDIV CONTROLLED BENCHMARK: LOCAL OLLAMA CODER")
    print(f" Coder Provider:    Ollama (local, quota-free)")
    print(f" Coder Model:       {model_id}")
    print(f" Ollama Base URL:   {base_url}")
    print(f" Timeout:           {timeout_seconds}s per model call")
    print(f" Tasks:             {len(tasks)} ({', '.join(tasks)})")
    print(f" Conditions:        {len(conditions)} ({', '.join(conditions)})")
    print(f" Total Planned:     {total_runs} runs")
    print(f" Output Directory:  {out_path}")
    print("=" * 75)

    summary: Dict[str, Any] = {
        "experiment_id": "local_ollama_coder_comparison",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "coder_provider": "ollama",
        "coder_model": model_id,
        "ollama_base_url": base_url,
        "tasks": tasks,
        "conditions": conditions,
        "runs": [],
    }

    for task_id in tasks:
        for cond_str in conditions:
            current_run += 1
            cond_enum = ExperimentCondition.from_str(cond_str)
            job_name = f"{task_id}__{cond_str}"
            result_file = results_dir / f"result_{job_name}.json"
            log_file = logs_base / f"{job_name}.log"
            job_ws = ws_base / job_name

            print(f"\n[{current_run}/{total_runs}] STARTING: {task_id} [{cond_str.upper()}]")

            # Check if result already exists and is valid
            if result_file.exists() and not force_rerun:
                try:
                    existing = json.loads(result_file.read_text(encoding="utf-8"))
                    if existing.get("status") in ("COMPLETED", "RESOLVED"):
                        print(f"    [SKIP] Valid existing result found (Resolved: {existing.get('resolved')}, Attempts: {existing.get('attempts')})")
                        cand = existing.get("candidate_patch", "")
                        if cand:
                            (results_dir / f"{job_name}.patch").write_text(cand, encoding="utf-8")
                        summary["runs"].append(existing)
                        summary["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        (out_path / "comparison_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
                        generate_reports(summary, out_path, dataset=dataset)
                        continue
                except Exception:
                    pass

            prepare_task_seed(job_ws, task_id)

            if cond_enum == ExperimentCondition.FULL_DDIV:
                worker = V22SupervisedWorker(
                    experiment_id="local_ollama_coder",
                    task_id=task_id,
                    condition=cond_enum,
                    workspace_root=job_ws,
                    provider="real",
                    dataset=dataset,
                    log_file=log_file,
                )
            else:
                worker = ExperimentWorker(
                    experiment_id="local_ollama_coder",
                    task_id=task_id,
                    condition=cond_enum,
                    workspace_root=job_ws,
                    provider="real",
                    dataset=dataset,
                    log_file=log_file,
                )

            job_start = time.time()
            record: ExperimentConditionRecord = worker.run()
            duration = time.time() - job_start

            # Augment record with coder metadata and metrics
            rec_dict = record.model_dump()
            rec_dict["coder_provider"] = "ollama"
            rec_dict["coder_model"] = model_id
            rec_dict["coder_base_url"] = base_url
            metrics = rec_dict.get("metrics") or {}
            rec_dict["total_tokens"] = metrics.get("total_tokens", 0)
            rec_dict["prompt_tokens"] = metrics.get("input_tokens", 0)
            rec_dict["completion_tokens"] = metrics.get("output_tokens", 0)

            # Save independent result JSON
            result_file.write_text(json.dumps(rec_dict, indent=2), encoding="utf-8")

            # Save patch if available
            if record.candidate_patch:
                patch_file = results_dir / f"{job_name}.patch"
                patch_file.write_text(record.candidate_patch, encoding="utf-8")

            print(f"    [DONE] Resolved: {record.resolved} | Attempts: {record.attempts} | Duration: {duration:.1f}s | Status: {record.status.value}")

            summary["runs"].append(rec_dict)

            # Save rolling summary and update reports
            summary["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            (out_path / "comparison_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            generate_reports(summary, out_path, dataset=dataset)

    print("\n" + "=" * 75)
    print(" LOCAL OLLAMA COMPARISON BENCHMARK COMPLETE")
    print(f" All results stored in: {results_dir}")
    print("=" * 75)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run controlled Ollama coder comparison on SWE-bench tasks.")
    parser.add_argument("--tasks", nargs="+", default=DEFAULT_TASKS, help="Task IDs to evaluate")
    parser.add_argument("--conditions", nargs="+", default=DEFAULT_CONDITIONS, help="Conditions: baseline, retry_only, full_ddiv")
    parser.add_argument("--output-dir", default="results/local_ollama_coder", help="Output directory")
    parser.add_argument("--model", default="qwen2.5-coder:7b", help="Ollama model ID")
    parser.add_argument("--base-url", default="http://localhost:11434", help="Ollama server URL")
    parser.add_argument("--timeout", type=int, default=240, help="Ollama timeout in seconds")
    parser.add_argument("--force-rerun", action="store_true", help="Force re-execution of existing jobs")
    parser.add_argument("--dataset", default="data/swebench/test-00000-of-00001.parquet", help="SWE-bench dataset parquet path")

    args = parser.parse_args()
    run_comparison(
        tasks=args.tasks,
        conditions=args.conditions,
        output_dir=args.output_dir,
        model_id=args.model,
        base_url=args.base_url,
        timeout_seconds=args.timeout,
        dataset=args.dataset,
        force_rerun=args.force_rerun,
    )


if __name__ == "__main__":
    main()
