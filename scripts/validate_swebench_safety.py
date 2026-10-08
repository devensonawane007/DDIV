"""Validation script to demonstrate SWE-bench Parquet loading, agent safety, and zero data leakage."""

import json
import sys
from pathlib import Path

# Add project root to sys.path for direct CLI invocation
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from evaluation.swebench_loader import SWEBenchLoader


def main():
    loader = SWEBenchLoader()
    parquet_path = Path("data/swebench/test-00000-of-00001.parquet")

    if not parquet_path.exists():
        print(f"Error: Parquet file not found at {parquet_path}")
        return

    records = loader.load_from_file(parquet_path)
    print(f"SWE-bench records loaded: {len(records)}\n")

    first_record = records[0]
    task_dict = first_record.task.model_dump()
    gt_dict = first_record.ground_truth.model_dump()

    print("Agent Task Fields:")
    for field in task_dict.keys():
        print(f"  {field}")
    print()

    print("Ground Truth Fields:")
    for field in gt_dict.keys():
        print(f"  {field}")
    print()

    # Agent input simulation
    locator_input = {
        "issue": first_record.task.problem_statement,
        "repo_structure": f"Repository: {first_record.task.repo}",
        "memory_context": "",
        "recovery_guidance": "",
    }
    serialized_input = json.dumps(locator_input)

    gold_patch = first_record.ground_truth.gold_patch.strip()
    gold_patch_in_input = bool(gold_patch and gold_patch in serialized_input)
    test_patch_in_input = bool(first_record.ground_truth.test_patch and first_record.ground_truth.test_patch in serialized_input)
    fail_to_pass_in_input = any(f in serialized_input for f in first_record.ground_truth.fail_to_pass if f)
    pass_to_pass_in_input = any(p in serialized_input for p in first_record.ground_truth.pass_to_pass if p)

    print("Leakage Check:")
    print(f"  GOLD_PATCH_IN_AGENT_INPUT = {gold_patch_in_input}")
    print(f"  TEST_PATCH_IN_AGENT_INPUT = {test_patch_in_input}")
    print(f"  FAIL_TO_PASS_IN_AGENT_INPUT = {fail_to_pass_in_input}")
    print(f"  PASS_TO_PASS_IN_AGENT_INPUT = {pass_to_pass_in_input}")


if __name__ == "__main__":
    main()
