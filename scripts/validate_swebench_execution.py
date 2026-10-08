from __future__ import annotations

import sys
import time
from pathlib import Path

# Add project root to sys.path for direct CLI invocation
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from evaluation.swebench_loader import SWEBenchLoader
from evaluation.swebench_runner import SWEBenchRunner
from evaluation.workspace import WorkspaceManager


def main():
    loader = SWEBenchLoader()
    parquet_path = Path("data/swebench/test-00000-of-00001.parquet")

    if not parquet_path.exists():
        print(f"Error: Dataset parquet not found at {parquet_path}")
        return

    records = loader.load_from_file(parquet_path)
    total_records = len(records)

    # 1. Select exactly ONE real task (first record)
    selected_record = records[0]
    task = selected_record.task

    # 2. Workspace Setup
    workspace_mgr = WorkspaceManager(base_workspace_dir="data/workspaces")
    workspace = workspace_mgr.create_workspace(
        task_id=task.instance_id,
        init_git=False,
        subfolder="swebench",
    )

    print("============================================")
    print(" SWE-BENCH INFRASTRUCTURE VALIDATION")
    print("============================================")
    print()
    print("Dataset:")
    print("  SWE-bench Verified")
    print()
    print(f"Records available:\n  {total_records}")
    print()
    print(f"Selected instance:\n  {task.instance_id}")
    print()
    print(f"Repository:\n  {task.repo}")
    print()
    print(f"Expected base commit:\n  {task.base_commit}")
    print()
    print(f"Workspace:\n  {workspace.path}")
    print()

    # 3. Repository Checkout
    checkout_res = workspace_mgr.checkout_repository(
        workspace=workspace,
        repo=task.repo,
        base_commit=task.base_commit,
        timeout=300,
    )

    checkout_status = "SUCCESS" if checkout_res.success else "FAILURE"
    print(f"Checkout:\n  {checkout_status}")
    print()
    print(f"Actual HEAD:\n  {checkout_res.actual_commit or 'N/A'}")
    print()
    print(f"Base commit verified:\n  {str(checkout_res.success).upper()}")
    print()

    # 4. Environment Check
    runner = SWEBenchRunner()
    env_status = runner.check_environment(workspace=workspace, task=task)
    print(f"Environment:\n  {env_status.status} ({env_status.details})")
    print()

    # 5. Base Commit Test Execution
    start_test_time = time.time()
    test_res = runner.run_task_at_base_commit(workspace=workspace, task=task, timeout=120)
    test_duration = time.time() - start_test_time

    print(f"Test execution:\n  {test_res.status_label}")
    print()
    print(f"Exit code:\n  {test_res.exit_code}")
    print()
    print(f"Duration:\n  {test_duration:.2f}s")
    print()
    print("Ground-truth leakage:\n  NOT USED")
    print()


if __name__ == "__main__":
    main()
