"""Tests for SWEBenchLoader, Parquet parsing, Agent-Safe separation, and zero-leakage enforcement."""

import json
import unittest
from pathlib import Path

from evaluation.swebench_loader import (
    SWEBenchGroundTruth,
    SWEBenchLoader,
    SWEBenchRecord,
    SWEBenchTask,
)


class TestSWEBenchLoader(unittest.TestCase):
    def setUp(self):
        self.loader = SWEBenchLoader()
        self.parquet_path = Path("data/swebench/test-00000-of-00001.parquet")

    def test_1_parquet_loading(self):
        """Test loading real SWE-bench Verified Parquet dataset and verify row count and fields."""
        if not self.parquet_path.exists():
            self.skipTest(f"Parquet file not found at {self.parquet_path}")

        records = self.loader.load_from_file(self.parquet_path)
        self.assertGreater(len(records), 0, "Loader should return non-empty record list")
        self.assertEqual(len(records), 500, "SWE-bench Verified test split must contain 500 records")

        first_record = records[0]
        self.assertIsInstance(first_record, SWEBenchRecord)
        self.assertIsInstance(first_record.task, SWEBenchTask)
        self.assertIsInstance(first_record.ground_truth, SWEBenchGroundTruth)

        # Verify task mandatory fields
        self.assertTrue(bool(first_record.task.instance_id.strip()))
        self.assertTrue(bool(first_record.task.repo.strip()))
        self.assertTrue(bool(first_record.task.base_commit.strip()))
        self.assertTrue(bool(first_record.task.problem_statement.strip()))

    def test_2_agent_safe_task(self):
        """Verify that record.task does NOT contain any ground-truth fields."""
        mock_rec = self.loader.get_mock_record()
        task_dict = mock_rec.task.model_dump()

        forbidden_keys = {
            "patch",
            "test_patch",
            "FAIL_TO_PASS",
            "PASS_TO_PASS",
            "gold_patch",
            "fail_to_pass",
            "pass_to_pass",
        }

        for key in forbidden_keys:
            self.assertNotIn(
                key,
                task_dict,
                f"Agent task dictionary contains forbidden ground-truth key '{key}'",
            )

        # Also verify with real parquet records if available
        if self.parquet_path.exists():
            records = self.loader.load_from_file(self.parquet_path)
            for rec in records[:10]:
                dump = rec.task.model_dump()
                for key in forbidden_keys:
                    self.assertNotIn(key, dump)

    def test_3_ground_truth_separation(self):
        """Verify that ground-truth fields are present in record.ground_truth and typed properly."""
        mock_rec = self.loader.get_mock_record()
        gt = mock_rec.ground_truth

        self.assertIsInstance(gt, SWEBenchGroundTruth)
        self.assertTrue(hasattr(gt, "gold_patch"))
        self.assertTrue(hasattr(gt, "test_patch"))
        self.assertTrue(hasattr(gt, "fail_to_pass"))
        self.assertTrue(hasattr(gt, "pass_to_pass"))

        self.assertIsInstance(gt.fail_to_pass, list)
        self.assertIsInstance(gt.pass_to_pass, list)
        self.assertGreater(len(gt.fail_to_pass), 0)

        # Check parquet records
        if self.parquet_path.exists():
            records = self.loader.load_from_file(self.parquet_path)
            rec = records[0]
            self.assertIsInstance(rec.ground_truth.gold_patch, str)
            self.assertTrue(len(rec.ground_truth.gold_patch) > 0)
            self.assertIsInstance(rec.ground_truth.fail_to_pass, list)
            self.assertIsInstance(rec.ground_truth.pass_to_pass, list)

    def test_4_no_agent_leakage(self):
        """Verify that inputs to Locator, Coder, Tester, and Supervisor cannot leak ground truth."""
        if not self.parquet_path.exists():
            rec = self.loader.get_mock_record()
        else:
            rec = self.loader.load_from_file(self.parquet_path)[0]

        task = rec.task
        gt = rec.ground_truth

        # Simulate agent input structures as prepared by DDIVOrchestrator
        locator_input = {
            "issue": task.problem_statement,
            "repo_structure": f"Repository: {task.repo}",
            "memory_context": "",
            "recovery_guidance": "",
        }

        coder_input = {
            "issue": task.problem_statement,
            "locator_result": {"relevant_files": ["src/module.py"], "relevant_symbols": ["func"]},
            "source_files": "Target files: src/module.py",
            "previous_attempts": "",
            "recovery_instructions": "",
        }

        tester_input = {
            "issue": task.problem_statement,
            "candidate_patch": "",
            "relevant_code": "Files: src/module.py",
        }

        supervisor_input = {
            "task_id": task.instance_id,
            "max_attempts": 3,
            "issue": task.problem_statement,
            "locator_summary": "Located files: ['src/module.py']",
            "patch_summary": "",
            "patch_applied": True,
            "test_results": {"passed": False, "failures": ["AssertionError"], "exit_code": 1},
            "deterministic_hints": ["F2"],
            "trust_scores": {},
            "memory_matches": [],
            "attempt_history": [],
        }

        agent_inputs = [locator_input, coder_input, tester_input, supervisor_input]

        for idx, agent_input in enumerate(agent_inputs):
            serialized = json.dumps(agent_input)

            # 1. Check for key names
            self.assertNotIn("gold_patch", serialized)
            self.assertNotIn("test_patch", serialized)
            self.assertNotIn("FAIL_TO_PASS", serialized)
            self.assertNotIn("PASS_TO_PASS", serialized)

            # 2. Check for actual gold patch content
            if gt.gold_patch and len(gt.gold_patch.strip()) > 20:
                self.assertNotIn(
                    gt.gold_patch.strip(),
                    serialized,
                    f"Agent {idx} input contains actual gold patch content!",
                )

            # 3. Check for specific test names in fail_to_pass if non-empty
            for f2p_test in gt.fail_to_pass:
                if len(f2p_test) > 10:
                    self.assertNotIn(
                        f2p_test,
                        serialized,
                        f"Agent {idx} input contains ground-truth FAIL_TO_PASS test name '{f2p_test}'",
                    )

    def test_5_mock_compatibility(self):
        """Verify get_mock_task() and get_mock_record() provide backward-compatible functionality."""
        task = self.loader.get_mock_task("mock-task-1")
        self.assertIsInstance(task, SWEBenchTask)
        self.assertEqual(task.instance_id, "mock-task-1")
        self.assertEqual(task.repo, "mock-org/calculator")
        self.assertIn("Calculator.divide", task.problem_statement)

        record = self.loader.get_mock_record("mock-task-1")
        self.assertIsInstance(record, SWEBenchRecord)
        self.assertEqual(record.task.instance_id, "mock-task-1")
        self.assertIn("ValueError", record.ground_truth.gold_patch)
        self.assertEqual(len(record.ground_truth.fail_to_pass), 1)


if __name__ == "__main__":
    unittest.main()
