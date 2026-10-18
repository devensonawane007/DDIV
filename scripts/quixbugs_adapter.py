"""CLI entrypoint for QuixBugs Python Benchmark Adapter.

Provides inspection, task listing, dry-run examination, and verification of
discovered QuixBugs tasks without invoking any LLM, making network calls,
or launching repair experiments.

Usage:
    python scripts/quixbugs_adapter.py --list-tasks
    python scripts/quixbugs_adapter.py --list-tasks --json
    python scripts/quixbugs_adapter.py --task-id quixbugs-python-bitcount
    python scripts/quixbugs_adapter.py --manifest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.quixbugs_adapter import QuixBugsAdapter


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect and manage QuixBugs Python Benchmark integration in DDIV."
    )
    parser.add_argument(
        "--data-dir",
        default=str(PROJECT_ROOT / "data/quixbugs"),
        help="Path to QuixBugs repository checkout (default: data/quixbugs)",
    )
    parser.add_argument(
        "--list-tasks",
        action="store_true",
        help="List all discovered Python benchmark tasks.",
    )
    parser.add_argument(
        "--task-id",
        type=str,
        default=None,
        help="Display detailed specification for a single task ID or program name.",
    )
    parser.add_argument(
        "--manifest",
        action="store_true",
        help="Print the QuixBugs dataset provenance manifest.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate task discovery and print validation status without executing any tests.",
    )
    parser.add_argument(
        "--audit-isolation",
        action="store_true",
        help="Run offline ground-truth isolation audit across all tasks without executing tests or LLM calls.",
    )

    args = parser.parse_args()
    adapter = QuixBugsAdapter(quixbugs_root=args.data_dir)

    if not adapter.is_available():
        print(f"ERROR: QuixBugs dataset is not found at: {args.data_dir}", file=sys.stderr)
        sys.exit(1)

    if args.manifest:
        manifest_file = Path(args.data_dir) / "quixbugs_manifest.json"
        if manifest_file.exists():
            print(manifest_file.read_text(encoding="utf-8"))
        else:
            print(json.dumps({"error": "quixbugs_manifest.json not found"}, indent=2))
        return

    if args.task_id:
        task = adapter.get_task(args.task_id)
        if not task:
            print(f"ERROR: Task '{args.task_id}' not found in QuixBugs Python dataset.", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps(task.model_dump(), indent=2))
        else:
            print(f"Task ID:             {task.task_id}")
            print(f"Program Name:        {task.program_name}")
            print(f"Language:            {task.language}")
            print(f"Target Source File:  {task.target_file}")
            print(f"Test File(s):        {', '.join(task.test_files)}")
            print(f"Support File(s):     {', '.join(task.support_files)}")
            print(f"Test Command:        {' '.join(task.test_command)}")
            print(f"Workspace Policy:    {task.workspace_policy}")
            print(f"Baseline Status:     {task.baseline_status}")
            print(f"Eligibility Status:  {task.eligibility_status}")
            print(f"Description:         {task.problem_description}")
            print(f"Metadata:            {task.result_metadata}")
    if args.audit_isolation:
        import tempfile
        import os
        tasks = adapter.discover_tasks()
        results = []
        all_passed = True

        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            for t in tasks:
                ws_dir = temp_root / t.program_name
                try:
                    adapter.create_agent_workspace(t.task_id, ws_dir, init_git=False)
                    found_files = []
                    for root, _, files in os.walk(ws_dir):
                        for f in files:
                            rel_p = str((Path(root) / f).relative_to(ws_dir)).replace("\\", "/")
                            found_files.append(rel_p)

                    expected = [f"python_programs/{t.program_name}.py"]
                    if t.result_metadata.get("is_graph_based"):
                        expected.append("python_programs/node.py")

                    forbidden = []
                    for f in found_files:
                        fname = Path(f).name.lower()
                        if (
                            fname.startswith("test_")
                            or fname.endswith("_test.py")
                            or fname.endswith(".json")
                            or fname == "conftest.py"
                            or "correct" in fname
                        ):
                            forbidden.append(f)

                    is_isolated = (set(found_files) == set(expected)) and (len(forbidden) == 0)
                    if not is_isolated:
                        all_passed = False

                    results.append({
                        "task_id": t.task_id,
                        "program_name": t.program_name,
                        "files_found": sorted(found_files),
                        "forbidden_count": len(forbidden),
                        "isolated": is_isolated,
                    })
                except Exception as exc:
                    all_passed = False
                    results.append({
                        "task_id": t.task_id,
                        "program_name": t.program_name,
                        "error": str(exc),
                        "isolated": False,
                    })

        audit_summary = {
            "total_tasks_audited": len(tasks),
            "isolated_workspaces_count": sum(1 for r in results if r.get("isolated")),
            "failed_isolation_count": sum(1 for r in results if not r.get("isolated")),
            "overall_isolation_status": "VERIFIED" if all_passed else "FAILED",
            "results": results,
        }

        if args.json:
            print(json.dumps(audit_summary, indent=2))
        else:
            print(f"Ground-Truth Isolation Audit ({len(tasks)} tasks):")
            print(f"{'#':<3} {'Task ID':<38} {'Files in Workspace':<35} {'Status':<10}")
            print("-" * 90)
            for i, r in enumerate(results, 1):
                f_str = ", ".join(r.get("files_found", []))
                status_str = "ISOLATED" if r.get("isolated") else "LEAKED/ERROR"
                print(f"{i:<3} {r['task_id']:<38} {f_str:<35} {status_str:<10}")
            print("-" * 90)
            print(f"Overall Isolation Status: {audit_summary['overall_isolation_status']}")
            print(f"Isolated: {audit_summary['isolated_workspaces_count']}/{len(tasks)} | Leaks: {audit_summary['failed_isolation_count']}")
        return

    if args.list_tasks or args.dry_run:
        tasks = adapter.discover_tasks()
        if args.json:
            print(json.dumps([t.model_dump() for t in tasks], indent=2))
        else:
            print(f"Discovered {len(tasks)} QuixBugs Python tasks:")
            print(f"{'#':<3} {'Task ID':<38} {'Target File':<35} {'Category':<12}")
            print("-" * 90)
            for i, t in enumerate(tasks, 1):
                cat = "Graph" if t.result_metadata.get("is_graph_based") else "Standard"
                print(f"{i:<3} {t.task_id:<38} {t.target_file:<35} {cat:<12}")
            print("-" * 90)
            print(f"Total: {len(tasks)} tasks discovered. Zero model calls invoked.")
        return

    # Default help
    parser.print_help()


if __name__ == "__main__":
    main()
