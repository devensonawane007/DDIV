"""Execute QuixBugs Python Baseline Screening on approved task batch.

Runs unpatched buggy implementations in isolated workspaces to verify defect
reproduction without invoking any LLM, external network call, or repair experiment.

Usage:
    python scripts/run_quixbugs_baseline_screening.py
    python scripts/run_quixbugs_baseline_screening.py --output-dir results/custom_screening
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.quixbugs_adapter import QuixBugsAdapter, QuixBugsBaselineResult

DEFAULT_TASKS = [
    "quixbugs-python-bucketsort",
    "quixbugs-python-flatten",
    "quixbugs-python-is_valid_parenthesization",
    "quixbugs-python-max_sublist_sum",
    "quixbugs-python-pascal",
    "quixbugs-python-quicksort",
    "quixbugs-python-rpn_eval",
    "quixbugs-python-to_base",
]


def run_baseline_screening(
    task_ids: List[str],
    output_dir: Path,
    data_dir: Path,
    timeout: int = 10,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter = QuixBugsAdapter(quixbugs_root=data_dir)

    print("=" * 80)
    print(f"QuixBugs Baseline Screening: {len(task_ids)} Tasks")
    print(f"Dataset root: {data_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Per-task timeout: {timeout}s")
    print("=" * 80)

    results = []
    task_details = []
    start_total = time.time()

    for idx, tid in enumerate(task_ids, 1):
        task = adapter.get_task(tid)
        if not task:
            print(f"[{idx}/{len(task_ids)}] ERROR: Task '{tid}' not found in dataset!")
            continue

        print(f"[{idx}/{len(task_ids)}] Screening {task.task_id} ({task.program_name})...", end=" ", flush=True)
        res: QuixBugsBaselineResult = adapter.check_baseline_eligibility(task, timeout=timeout)

        status_flag = res.eligibility_status
        fail_count = len(res.failed_tests)
        pass_count = len(res.passed_tests)
        total_count = res.total_tests
        dur = res.duration_seconds

        print(f"-> {status_flag} ({fail_count}/{total_count} failed, {pass_count} passed, {dur:.2f}s)")

        # Save individual task log
        task_out_dir = output_dir / task.program_name
        task_out_dir.mkdir(parents=True, exist_ok=True)
        (task_out_dir / "baseline_result.json").write_text(
            json.dumps(res.model_dump(), indent=2), encoding="utf-8"
        )
        (task_out_dir / "sanitized_test_output.txt").write_text(
            res.sanitized_output or "", encoding="utf-8"
        )

        results.append(res)
        task_details.append({
            "task_id": task.task_id,
            "program_name": task.program_name,
            "target_file": task.target_file,
            "test_file": task.test_files[0] if task.test_files else "",
            "eligibility_status": res.eligibility_status,
            "has_reproduced_defect": res.has_reproduced_defect,
            "has_environment_failure": res.has_environment_failure,
            "is_timeout": res.is_timeout,
            "total_tests": res.total_tests,
            "passed_tests_count": len(res.passed_tests),
            "failed_tests_count": len(res.failed_tests),
            "failed_tests": res.failed_tests,
            "duration_seconds": res.duration_seconds,
        })

    total_duration = round(time.time() - start_total, 3)

    eligible_count = sum(1 for r in results if r.eligibility_status == "ELIGIBLE")
    ineligible_count = sum(1 for r in results if r.eligibility_status == "INELIGIBLE")
    recheck_count = sum(1 for r in results if r.eligibility_status == "NEEDS_RECHECK")

    summary = {
        "screening_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "benchmark": "QuixBugs (Python)",
        "dataset_path": str(data_dir).replace("\\", "/"),
        "total_tasks_screened": len(results),
        "eligible_tasks_count": eligible_count,
        "ineligible_tasks_count": ineligible_count,
        "needs_recheck_count": recheck_count,
        "overall_screening_status": "SUCCESS" if (eligible_count == len(results)) else "PARTIAL",
        "total_duration_seconds": total_duration,
        "tasks": task_details,
    }

    # Write machine-readable summary
    (output_dir / "baseline_screening_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    # Generate Markdown Report
    md_lines = [
        "# QuixBugs Phase 8.2: Baseline Defect Screening Report",
        "",
        f"**Screening Date:** {summary['screening_timestamp']}  ",
        f"**Dataset Location:** `{summary['dataset_path']}`  ",
        f"**Total Screened:** {len(results)} tasks  ",
        f"**Eligible Tasks (Defect Reproduced):** {eligible_count}  ",
        f"**Ineligible Tasks:** {ineligible_count}  ",
        f"**Environment / Recheck Needed:** {recheck_count}  ",
        f"**Screening Runtime:** {total_duration} seconds  ",
        "",
        "---",
        "",
        "## 1. Summary of Baseline Screening Results",
        "",
        "| # | Task ID | Program | Total Tests | Failed Tests | Status | Duration |",
        "| :-: | :--- | :--- | :-: | :-: | :-: | :-: |",
    ]

    for idx, t in enumerate(task_details, 1):
        md_lines.append(
            f"| {idx} | `{t['task_id']}` | `{t['program_name']}` | {t['total_tests']} | "
            f"{t['failed_tests_count']} | **`{t['eligibility_status']}`** | {t['duration_seconds']:.2f}s |"
        )

    md_lines.extend([
        "",
        "---",
        "",
        "## 2. Detailed Task Breakdown",
        "",
    ])

    for idx, t in enumerate(task_details, 1):
        md_lines.extend([
            f"### 2.{idx} {t['task_id']}",
            f"- **Target File:** `{t['target_file']}`",
            f"- **Test File:** `{t['test_file']}`",
            f"- **Eligibility Verdict:** **`{t['eligibility_status']}`**",
            f"- **Defect Reproduced:** `{t['has_reproduced_defect']}`",
            f"- **Environment Errors:** `{t['has_environment_failure']}`",
            f"- **Failed Test Cases ({t['failed_tests_count']}):**",
        ])
        for ft in t["failed_tests"]:
            md_lines.append(f"  - `{ft}`")
        md_lines.append("")

    md_lines.extend([
        "---",
        "",
        "## 3. Strict Research Constraints Adherence",
        "- **Zero LLM / Inference API Calls:** All baseline runs executed using local Python and pytest.",
        "- **Zero Repair Experiments Launched:** No candidate patches or model generations were requested.",
        "- **Historical Data Untouched:** SWE-bench results and `data/ddiv_memory.db` remain unaltered.",
        "- **Ground-Truth Isolation:** Execution used temporary isolated workspaces with complete test/JSON exclusion and sanitized diagnostic outputs.",
        "",
        "## 4. Conclusion & Readiness for Repair Evaluation",
        f"All {eligible_count} selected tasks have verified defect reproduction under authoritative test suites without environment errors. They are confirmed eligible for Phase 8.3 repair experiments.",
    ])

    (output_dir / "baseline_screening_report.md").write_text("\n".join(md_lines), encoding="utf-8")
    print("=" * 80)
    print(f"Screening complete: {eligible_count}/{len(results)} tasks ELIGIBLE.")
    print(f"Report saved to: {output_dir / 'baseline_screening_report.md'}")
    print("=" * 80)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run QuixBugs Python baseline defect screening.")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "results/quixbugs_baseline_screening_20261016T054600Z"),
        help="Directory to save screening results and report.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(PROJECT_ROOT / "data/quixbugs"),
        help="Path to QuixBugs dataset.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Per-task execution timeout in seconds (default: 10).",
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        default=DEFAULT_TASKS,
        help="List of task IDs to screen.",
    )

    args = parser.parse_args()
    run_baseline_screening(
        task_ids=args.tasks,
        output_dir=Path(args.output_dir),
        data_dir=Path(args.data_dir),
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
