"""DDIV v2.2 Isolated Development Validation Runner.

Executes real-repository development validation on:
- pylint-dev__pylint-4970
- pylint-dev__pylint-6903

Applies v2.2 components:
1. Block-aware indentation normalization and safe placeholder path remapping (DemoPatchBuilder).
2. Explicit path constraint in Ollama Coder prompt.
3. Anti-repetition tracking (ProposalHistory) and empirical FailureDisambiguator.

Outputs are strictly isolated under:
- Workspaces: data/workspaces/v2_2_dev_val/
- Logs: logs/v2_2_dev_val/
- Results: results/v2_2_development/dev_validation/
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Set root
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set UTF-8 for Windows console
os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Set Ollama provider
os.environ["DDIV_CODER_PROVIDER"] = "ollama"

from dotenv import load_dotenv
load_dotenv(Path(project_root) / ".env", override=False)

import core.experiment_worker as ew
from core.conditions import ExperimentCondition
from core.experiment_record import ExperimentConditionRecord
from core.experiment_worker import ExperimentWorker
from scripts.demo_patch_builder import DemoPatchBuilder
from scripts.ollama_coder_adapter import register_ollama_provider
from scripts.v2_2_recovery_manager import (
    FailureDisambiguator,
    ProposalHistory,
    V22SupervisedWorker,
)


def run_dev_validation(
    tasks: Optional[List[str]] = None,
    output_dir: str = "results/v2_2_development/dev_validation",
    dataset: str = "data/swebench/test-00000-of-00001.parquet",
) -> Dict[str, Any]:
    tasks = tasks or ["pylint-dev__pylint-4970", "pylint-dev__pylint-6903"]

    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    results_dir = out_path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    ws_base = Path("data/workspaces/v2_2_dev_val").resolve()
    ws_base.mkdir(parents=True, exist_ok=True)

    logs_base = Path("logs/v2_2_dev_val").resolve()
    logs_base.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {
        "validation_id": "ddiv_v2_2_dev_validation",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "coder_provider": "ollama",
        "coder_model": "qwen2.5-coder:7b",
        "tasks": tasks,
        "condition": "full_ddiv",
        "runs": [],
    }

    print("=" * 75)
    print(" DDIV v2.2 DEVELOPMENT VALIDATION: REAL REPOSITORIES")
    print(f" Tasks:            {', '.join(tasks)}")
    print(f" Condition:        FULL_DDIV")
    print(f" Coder Model:      qwen2.5-coder:7b (Ollama local)")
    print(f" Output Directory: {out_path}")
    print("=" * 75)

    for idx, task_id in enumerate(tasks, 1):
        job_name = f"{task_id}__full_ddiv"
        result_file = results_dir / f"result_{job_name}.json"
        log_file = logs_base / f"{job_name}.log"
        job_ws = ws_base / job_name

        print(f"\n[{idx}/{len(tasks)}] STARTING VALIDATION: {task_id}")
        prepare_task_seed(job_ws, task_id)

        worker = V22SupervisedWorker(
            experiment_id="v2_2_dev_val",
            task_id=task_id,
            condition=ExperimentCondition.FULL_DDIV,
            workspace_root=job_ws,
            provider="real",
            dataset=dataset,
            log_file=log_file,
        )

        job_start = time.time()
        record: ExperimentConditionRecord = worker.run()
        duration = time.time() - job_start

        rec_dict = record.model_dump()
        rec_dict["coder_provider"] = "ollama"
        rec_dict["coder_model"] = "qwen2.5-coder:7b"
        rec_dict["execution_duration_seconds"] = duration

        result_file.write_text(json.dumps(rec_dict, indent=2), encoding="utf-8")
        if record.candidate_patch:
            (results_dir / f"{job_name}.patch").write_text(record.candidate_patch, encoding="utf-8")

        print(f"    [COMPLETE] Resolved: {record.resolved} | Attempts: {record.attempts} | Duration: {duration:.1f}s | Status: {record.status.value}")
        summary["runs"].append(rec_dict)

    summary["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out_path / "dev_val_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Generate Markdown Report
    generate_validation_report(summary, out_path)
    return summary


def generate_validation_report(summary: Dict[str, Any], output_dir: Path):
    md_path = output_dir / "dev_validation_report.md"
    lines = [
        "# DDIV v2.2 Real-Repository Development Validation Report",
        "",
        "> [!NOTE]",
        "> **Scope:** Internal Tier-1 isolated development validation evaluating DDIV v2.2 improvements",
        "> (block-aware indentation normalization, placeholder path remapping, and anti-repetition directives)",
        "> on SWE-bench Verified tasks using local Ollama (`qwen2.5-coder:7b`) under `FULL_DDIV`.",
        "",
        "## 1. Experimental Configuration",
        f"- **Coder Model:** `{summary.get('coder_model')}` via local Ollama",
        "- **Locator:** `gemini-3.1-flash-lite`",
        "- **Supervisor & RCA:** `qwen/qwen3.8-27b` via Groq",
        "- **Condition:** `FULL_DDIV`",
        f"- **Started At:** `{summary.get('started_at')}`",
        f"- **Completed At:** `{summary.get('completed_at')}`",
        "",
        "## 2. Validation Run Outcomes",
        "",
        "| Task ID | Status | Resolved | Attempts | F2P Passed | P2P Passed | Tokens | Duration (s) | Failure / Diagnostic |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]

    for r in summary.get("runs", []):
        internal_eval = r.get("internal_evaluation") or {}
        # Known ground truth totals for tested tasks
        gt_f2p = 1 if "pylint" in r.get("task_id", "") else None
        gt_p2p = 17 if "4970" in r.get("task_id", "") else (8 if "6903" in r.get("task_id", "") else None)

        f2p_str, p2p_str = FailureDisambiguator.format_test_counts(
            internal_eval,
            ground_truth_f2p_total=gt_f2p,
            ground_truth_p2p_total=gt_p2p,
        )

        history = r.get("attempt_history") or []
        last_hist = history[-1] if history else {}
        diag = "RESOLVED" if r.get("resolved") else (
            last_hist.get("failure_category")
            or last_hist.get("coder_error_code")
            or "UNRESOLVED"
        )
        res_sym = "✅ **YES**" if r.get("resolved") else "❌ NO"
        metrics = r.get("metrics") or {}
        tot_tok = r.get("total_tokens") or metrics.get("total_tokens", 0)

        lines.append(
            f"| `{r.get('task_id')}` | {r.get('status')} | {res_sym} | {r.get('attempts')} | {f2p_str} | {p2p_str} | {tot_tok:,} | {r.get('execution_duration_seconds', 0.0):.1f}s | `{diag}` |"
        )

    lines.extend([
        "",
        "## 3. Detailed Attempt Progression & Empirical Analysis",
        "",
    ])

    for r in summary.get("runs", []):
        lines.append(f"### Task: `{r.get('task_id')}`")
        lines.append(f"- **Final Resolution:** {r.get('resolved')}")
        lines.append(f"- **Total Attempts Executed:** {r.get('attempts')}")
        lines.append("")
        for att in r.get("attempt_history", []):
            att_num = att.get("attempt")
            patch_gen = att.get("patch_generated")
            patch_val = att.get("patch_valid")
            patch_app = att.get("agent_apply_success")
            f2p = att.get("f2p_passed")
            p2p = att.get("p2p_passed")
            fail_cat = att.get("failure_category")
            sup_diag = att.get("supervisor_diagnosis", "")
            sup_inst = att.get("supervisor_instructions", "")

            lines.append(f"#### Attempt {att_num}:")
            lines.append(f"- **Patch Generated:** {patch_gen} | **Patch Valid:** {patch_val} | **Patch Applied:** {patch_app}")
            lines.append(f"- **F2P Passed:** {f2p} | **P2P Passed:** {p2p}")
            if fail_cat:
                lines.append(f"- **Diagnosed Failure Category:** `{fail_cat}`")
            if sup_diag:
                lines.append(f"- **Supervisor Diagnosis:** {sup_diag}")
            if sup_inst:
                lines.append(f"- **Supervisor Instructions:** {sup_inst[:150]}...")
            lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[+] Dev Validation Report written to: {md_path}")


def main():
    parser = argparse.ArgumentParser(description="Run DDIV v2.2 isolated development validation.")
    parser.add_argument("--tasks", nargs="+", default=["pylint-dev__pylint-4970", "pylint-dev__pylint-6903"])
    parser.add_argument("--output-dir", default="results/v2_2_development/dev_validation")
    parser.add_argument("--dataset", default="data/swebench/test-00000-of-00001.parquet")
    args = parser.parse_args()

    run_dev_validation(tasks=args.tasks, output_dir=args.output_dir, dataset=args.dataset)


if __name__ == "__main__":
    main()
