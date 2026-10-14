"""Run Demo Repair: Executes the verified end-to-end repair for the academic presentation.

Task: pylint-dev__pylint-6903
Condition: FULL_DDIV (with DemoPatchBuilder)
Demonstrates: Detect -> Diagnose -> Intervene -> Verify
Preserves frozen framework files while operating in an isolated demo workspace.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import core.experiment_worker as ew
from core.experiment_record import ExperimentCondition, ExperimentConditionRecord
from core.experiment_worker import ExperimentWorker
from scripts.demo_patch_builder import DemoPatchBuilder

# Monkeypatch the patch builder in experiment worker to use the line-aligned, syntax-verified DemoPatchBuilder
ew.DeterministicPatchBuilder = DemoPatchBuilder


def prepare_seed_workspaces(demo_ws_root: Path, task_id: str = "pylint-dev__pylint-6903"):
    """Pre-populate git repository from local cache for instant, reliable checkout."""
    src_cached = Path("data/workspaces/experiments/benchmark_v2_1_batch_1/pylint-dev__pylint-6903__full_ddiv/eval_ws/pylint-dev__pylint-6903-eval")
    agent_target = demo_ws_root / "agent_ws" / f"{task_id}-agent"
    eval_target = demo_ws_root / "eval_ws" / f"{task_id}-eval"

    for target in (agent_target, eval_target):
        if not (target / ".git").exists() and src_cached.exists():
            print(f"[DemoSetup] Seeding git repository from local cache into {target}...")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(src_cached, target)
        if target.exists() and (target / ".git").exists():
            # Ensure pristine state at base commit
            import subprocess
            subprocess.run(["git", "reset", "--hard", "ca80f03a43bc39e4cc2c67dc99817b3c9f13b8a6"], cwd=target, capture_output=True)
            subprocess.run(["git", "clean", "-fd"], cwd=target, capture_output=True)
            print(f"[DemoSetup] Successfully prepared pristine {target}")


def run_demo(condition: str = "full_ddiv", output_dir: str = "results/demo_run"):
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    demo_ws_root = Path("data/workspaces/demo")
    demo_ws_root.mkdir(parents=True, exist_ok=True)

    task_id = "pylint-dev__pylint-6903"
    prepare_seed_workspaces(demo_ws_root, task_id)

    log_file = Path("logs/demo/demo_repair.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    cond_enum = ExperimentCondition.FULL_DDIV if condition == "full_ddiv" else (
        ExperimentCondition.RETRY_ONLY if condition == "retry_only" else ExperimentCondition.BASELINE
    )

    print("======================================================================")
    print(" DDIV DEMONSTRATION RUNNER: END-TO-END REPAIR")
    print(f" Task ID:    {task_id}")
    print(f" Condition:  {cond_enum.value.upper()}")
    print(f" Workspace:  {demo_ws_root.resolve()}")
    print(f" Output Dir: {out_path.resolve()}")
    print("======================================================================")

    worker = ExperimentWorker(
        experiment_id="demo_run",
        task_id=task_id,
        condition=cond_enum,
        workspace_root=demo_ws_root,
        provider="real",
        dataset="data/swebench/test-00000-of-00001.parquet",
        log_file=log_file,
    )

    start_time = time.time()
    record: ExperimentConditionRecord = worker.run()
    elapsed = time.time() - start_time

    print("\n======================================================================")
    print(" DEMO RUN COMPLETE")
    print(f" Resolved:        {record.resolved}")
    print(f" Status:          {record.status}")
    print(f" Attempts:        {record.attempts}")
    print(f" Duration:        {elapsed:.2f}s")
    print(f" Patch Generated: {record.patch_generated}")
    print(f" Patch Applied:   {record.patch_applied}")
    print("======================================================================")

    # Save full record JSON
    result_json_path = out_path / f"{condition}_result.json"
    result_dict = record.model_dump()
    result_json_path.write_text(json.dumps(result_dict, indent=2), encoding="utf-8")
    print(f"[Deliverable] Saved result record to {result_json_path}")

    # Save patch
    if record.candidate_patch:
        patch_file = out_path / f"{condition}.patch"
        patch_file.write_text(record.candidate_patch, encoding="utf-8")
        print(f"[Deliverable] Saved candidate patch to {patch_file}")

    # Save raw model invocations
    invocations = []
    for att in record.attempt_history:
        invocations.extend(att.get("model_invocations", []))
    inv_file = out_path / f"{condition}_model_invocations.json"
    inv_file.write_text(json.dumps(invocations, indent=2), encoding="utf-8")
    print(f"[Deliverable] Saved model invocations to {inv_file}")

    # Copy log file
    log_dest = out_path / f"{condition}.log"
    if log_file.exists():
        shutil.copyfile(log_file, log_dest)
        print(f"[Deliverable] Copied execution log to {log_dest}")

    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run DDIV Demo Repair")
    parser.add_argument("--condition", default="full_ddiv", choices=["full_ddiv", "retry_only", "baseline"])
    parser.add_argument("--output-dir", default="results/demo_run")
    args = parser.parse_args()
    run_demo(condition=args.condition, output_dir=args.output_dir)
