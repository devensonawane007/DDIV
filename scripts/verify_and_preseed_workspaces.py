"""Safe workspace verification and pre-seeding for DDIV v2.2 20-task benchmark.

Guarantees:
- Uses dedicated disposable workspace targets (data/workspaces/preflight_verification/).
- Never touches or overwrites existing user workspaces (data/workspaces/experiments, local_ollama_coder, etc.).
- Verifies exact HEAD commit against frozen benchmark_v2_tasks.json base_commit.
- Never modifies the frozen manifest or checkpoint.
- Never invokes any model or experiment worker.
- Validates all 20 tasks, 7 batches, and 60 task-condition pairs in dry-run mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.workspace import WorkspaceManager, TaskWorkspace

EXPECTED_MANIFEST_HASH = "16fb9c829a2163f8187e3ffaec9cde585a843af905459a4e6467995792e2a605"
EXPECTED_CHECKPOINT_HASH = "3088b7c08707b30b6b87064844c45595520a4c86c599e9b1fcb45af3b3d4e52e"

BATCH_MAPPING = {
    1: ["pylint-dev__pylint-6903", "mwaskom__seaborn-3187", "pydata__xarray-7393"],
    2: ["astropy__astropy-8872", "astropy__astropy-14508", "psf__requests-2931"],
    3: ["pytest-dev__pytest-8399", "sympy__sympy-23413", "matplotlib__matplotlib-26342"],
    4: ["scikit-learn__scikit-learn-26323", "pydata__xarray-4966", "pylint-dev__pylint-4970"],
    5: ["sympy__sympy-13878", "django__django-16429", "sphinx-doc__sphinx-8638"],
    6: ["django__django-11141", "pytest-dev__pytest-7982", "scikit-learn__scikit-learn-13496"],
    7: ["sphinx-doc__sphinx-8269", "matplotlib__matplotlib-20676"],
}

CONDITIONS = ["baseline", "retry_only", "full_ddiv"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def verify_manifest_integrity() -> Dict[str, Any]:
    """Verify that the frozen manifest and checkpoint have not been altered."""
    mnf_path = Path("data/experiments/benchmark_v2_tasks.json")
    if not mnf_path.exists():
        raise FileNotFoundError(f"Manifest missing: {mnf_path}")
    actual_hash = sha256_file(mnf_path)
    if actual_hash != EXPECTED_MANIFEST_HASH:
        raise ValueError(
            f"FROZEN MANIFEST CORRUPTED! Expected {EXPECTED_MANIFEST_HASH}, got {actual_hash}"
        )

    chk_path = Path("data/experiments/benchmark_v2_1/checkpoint.json")
    if not chk_path.exists():
        raise FileNotFoundError(f"Checkpoint missing: {chk_path}")
    actual_chk_hash = sha256_file(chk_path)
    if actual_chk_hash != EXPECTED_CHECKPOINT_HASH:
        raise ValueError(
            f"FROZEN CHECKPOINT CORRUPTED! Expected {EXPECTED_CHECKPOINT_HASH}, got {actual_chk_hash}"
        )

    with open(mnf_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def verify_task_checkout(
    task: Dict[str, Any],
    disposable_root: Path,
    timeout: int = 180,
) -> Dict[str, Any]:
    """Checkout a task in a strictly isolated, disposable directory and verify HEAD."""
    task_id = task["instance_id"]
    repo = task["repo"]
    base_commit = task["base_commit"]

    safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in task_id)
    target_ws_dir = disposable_root / safe_id

    # Check if already verified at exact commit
    if target_ws_dir.exists():
        try:
            head_proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=target_ws_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            head = head_proc.stdout.strip()
            if head == base_commit or head.startswith(base_commit) or base_commit.startswith(head):
                return {
                    "task_id": task_id,
                    "repo": repo,
                    "base_commit": base_commit,
                    "actual_commit": head,
                    "verified": True,
                    "cached": True,
                    "duration_seconds": 0.0,
                    "error": None,
                }
        except Exception:
            pass

    t0 = time.time()
    ws_mgr = WorkspaceManager(base_workspace_dir=disposable_root)
    ws = TaskWorkspace(workspace_path=target_ws_dir, task_id=task_id, is_temp=False)

    chk_res = ws_mgr.checkout_repository(ws, repo=repo, base_commit=base_commit, timeout=timeout)
    duration = time.time() - t0

    if not chk_res.success:
        return {
            "task_id": task_id,
            "repo": repo,
            "base_commit": base_commit,
            "actual_commit": chk_res.actual_commit,
            "verified": False,
            "cached": False,
            "duration_seconds": duration,
            "error": chk_res.error,
        }

    head_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=target_ws_dir,
        capture_output=True,
        text=True,
        timeout=10,
    )
    actual_head = head_proc.stdout.strip()
    match = (actual_head == base_commit) or actual_head.startswith(base_commit) or base_commit.startswith(actual_head)

    py_files = len(list(target_ws_dir.glob("**/*.py")))

    return {
        "task_id": task_id,
        "repo": repo,
        "base_commit": base_commit,
        "actual_commit": actual_head,
        "verified": match,
        "py_file_count": py_files,
        "cached": False,
        "duration_seconds": duration,
        "error": None if match else f"Commit mismatch: {actual_head} != {base_commit}",
    }


def run_dry_run_preflight(
    manifest_tasks: List[Dict[str, Any]],
    verified_tasks: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Run a dry-run preflight covering all 60 task-condition pairs and 7 batches without calling any model."""
    task_map = {t["instance_id"]: t for t in manifest_tasks}

    batch_reports = []
    total_pairs = 0
    all_pairs_valid = True

    for b_num, tasks in sorted(BATCH_MAPPING.items()):
        b_info = {
            "batch": b_num,
            "tasks": tasks,
            "conditions_per_task": CONDITIONS,
            "pairs": [],
            "batch_valid": True,
        }
        for tid in tasks:
            if tid not in task_map:
                b_info["batch_valid"] = False
                all_pairs_valid = False
                continue

            t_meta = task_map[tid]
            t_ver = verified_tasks.get(tid, {})
            is_checkout_ok = t_ver.get("verified", False)

            for cond in CONDITIONS:
                total_pairs += 1
                pair_ok = is_checkout_ok
                if not pair_ok:
                    b_info["batch_valid"] = False
                    all_pairs_valid = False

                b_info["pairs"].append({
                    "task_id": tid,
                    "condition": cond,
                    "repo": t_meta["repo"],
                    "base_commit": t_meta["base_commit"],
                    "checkout_verified": is_checkout_ok,
                    "coder_provider": "ollama",
                    "coder_model": "qwen2.5-coder:7b",
                    "supporting_provider": "groq",
                    "supporting_model": "qwen/qwen3.8-27b",
                    "mock_or_real": "real",
                    "model_calls_permitted_in_preflight": False,
                    "patch_generation_permitted_in_preflight": False,
                    "pair_valid": pair_ok,
                })

        batch_reports.append(b_info)

    return {
        "total_batches": len(BATCH_MAPPING),
        "total_tasks": len(manifest_tasks),
        "total_task_condition_pairs": total_pairs,
        "all_pairs_valid": all_pairs_valid,
        "batches": batch_reports,
    }


def main():
    parser = argparse.ArgumentParser(description="Verify and safely pre-seed workspaces for DDIV v2.2 benchmark.")
    parser.add_argument(
        "--target-dir",
        default="data/workspaces/preflight_verification",
        help="Dedicated disposable workspace target directory",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Timeout per repository checkout in seconds (default: 180)",
    )
    parser.add_argument(
        "--output",
        default="results/v2_2_development/workspace_preflight_verification.json",
        help="Output JSON report path",
    )
    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(" DDIV v2.2 WORKSPACE PRE-SEEDING & PREFLIGHT VERIFICATION")
    print("=" * 70)
    print(f"Target Disposable Directory: {target_dir}")

    # 1. Verify Manifest Integrity
    print("\n[1/3] Verifying frozen manifest and checkpoint integrity...")
    data = verify_manifest_integrity()
    manifest_tasks = data.get("tasks", [])
    print(f"  [+] Manifest verified: {len(manifest_tasks)} tasks defined. SHA-256 matches.")

    # 2. Verify all 20 Task Checkouts
    print("\n[2/3] Verifying repository checkouts at exact base commits in disposable workspaces...")
    verified_results = {}
    all_checkouts_passed = True

    for i, t in enumerate(manifest_tasks, 1):
        tid = t["instance_id"]
        repo = t["repo"]
        commit = t["base_commit"]
        print(f"  [{i:02d}/20] Checking {tid} ({repo}@{commit[:10]})...", end=" ", flush=True)

        res = verify_task_checkout(t, target_dir, timeout=args.timeout)
        verified_results[tid] = res

        if res["verified"]:
            cached_str = " (cached)" if res.get("cached") else f" ({res['duration_seconds']:.1f}s)"
            print(f"OK{cached_str} [HEAD: {res['actual_commit'][:10]}]")
        else:
            print(f"FAILED: {res.get('error')}")
            all_checkouts_passed = False

    # 3. Dry-Run Preflight Across All 60 Task-Condition Pairs & 7 Batches
    print("\n[3/3] Running dry-run preflight validation across all 7 batches and 60 conditions...")
    dry_run_report = run_dry_run_preflight(manifest_tasks, verified_results)
    print(f"  [+] Total batches: {dry_run_report['total_batches']}")
    print(f"  [+] Total tasks: {dry_run_report['total_tasks']}")
    print(f"  [+] Total task-condition pairs: {dry_run_report['total_task_condition_pairs']}")
    print(f"  [+] Zero models invoked: True")
    print(f"  [+] Zero patches generated: True")
    print(f"  [+] All 60 pairs valid: {dry_run_report['all_pairs_valid']}")

    # Save Output Report
    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_directory": str(target_dir),
        "manifest_sha256": EXPECTED_MANIFEST_HASH,
        "checkpoint_sha256": EXPECTED_CHECKPOINT_HASH,
        "checkouts_verified_count": sum(1 for r in verified_results.values() if r["verified"]),
        "checkouts_total_count": len(manifest_tasks),
        "all_checkouts_passed": all_checkouts_passed,
        "task_checkouts": verified_results,
        "dry_run_preflight": dry_run_report,
    }
    out_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"\n[+] Verification report written to: {out_path}")

    print("=" * 70)
    status_str = "GO" if all_checkouts_passed and dry_run_report["all_pairs_valid"] else "NO-GO"
    print(f" WORKSPACE VERIFICATION STATUS: {status_str}")
    print("=" * 70)

    if not (all_checkouts_passed and dry_run_report["all_pairs_valid"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
