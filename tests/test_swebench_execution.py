"""Tests for SWE-bench workspace execution, commit validation, timeout, and zero leakage."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from evaluation.command_runner import CommandRunner
from evaluation.swebench_loader import SWEBenchLoader, SWEBenchTask
from evaluation.swebench_runner import SWEBenchRunner
from evaluation.workspace import WorkspaceManager


class TestSWEBenchExecution(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.tmp_dir.name)
        self.workspace_mgr = WorkspaceManager(base_workspace_dir=self.base_path / "workspaces")
        self.runner = SWEBenchRunner()
        self.cmd_runner = CommandRunner()

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_1_base_commit_validation(self):
        """Verify git rev-parse HEAD correctly validates checked-out commit."""
        ws = self.workspace_mgr.create_workspace("test-commit-val", init_git=True)
        try:
            # Create a file and commit it
            (ws.path / "file.txt").write_text("initial commit content", encoding="utf-8")
            self.cmd_runner.run(["git", "add", "."], cwd=ws.path)
            self.cmd_runner.run(["git", "commit", "-m", "Commit 1"], cwd=ws.path)

            rev_res = self.cmd_runner.run(["git", "rev-parse", "HEAD"], cwd=ws.path)
            commit1 = rev_res.stdout.strip()
            self.assertTrue(len(commit1) >= 40)

            # Create second commit
            (ws.path / "file.txt").write_text("second commit content", encoding="utf-8")
            self.cmd_runner.run(["git", "add", "."], cwd=ws.path)
            self.cmd_runner.run(["git", "commit", "-m", "Commit 2"], cwd=ws.path)

            rev_res2 = self.cmd_runner.run(["git", "rev-parse", "HEAD"], cwd=ws.path)
            commit2 = rev_res2.stdout.strip()
            self.assertNotEqual(commit1, commit2)

            # Checkout commit1
            co_res = self.cmd_runner.run(["git", "checkout", commit1], cwd=ws.path)
            self.assertTrue(co_res.is_success)

            head_res = self.cmd_runner.run(["git", "rev-parse", "HEAD"], cwd=ws.path)
            self.assertEqual(head_res.stdout.strip(), commit1)
        finally:
            ws.cleanup()

    def test_2_workspace_isolation(self):
        """Verify multiple workspaces remain strictly isolated."""
        ws1 = self.workspace_mgr.create_workspace("task-iso-1", init_git=True)
        ws2 = self.workspace_mgr.create_workspace("task-iso-2", init_git=True)

        try:
            (ws1.path / "file1.txt").write_text("task1 data", encoding="utf-8")
            (ws2.path / "file2.txt").write_text("task2 data", encoding="utf-8")

            self.assertTrue((ws1.path / "file1.txt").exists())
            self.assertFalse((ws1.path / "file2.txt").exists())

            self.assertTrue((ws2.path / "file2.txt").exists())
            self.assertFalse((ws2.path / "file1.txt").exists())
        finally:
            ws1.cleanup()
            ws2.cleanup()

    def test_3_safe_task_metadata_propagation(self):
        """Verify SWEBenchTask exposes only safe metadata."""
        task = SWEBenchTask(
            instance_id="sample-1",
            repo="org/sample-repo",
            base_commit="abc1234567890abcdef",
            problem_statement="Sample bug description",
            hints_text="Sample hint",
        )
        data = task.model_dump()
        self.assertEqual(data["instance_id"], "sample-1")
        self.assertEqual(data["repo"], "org/sample-repo")
        self.assertEqual(data["base_commit"], "abc1234567890abcdef")
        self.assertNotIn("gold_patch", data)
        self.assertNotIn("test_patch", data)
        self.assertNotIn("fail_to_pass", data)

    def test_4_no_ground_truth_leakage_in_execution(self):
        """Verify ground truth is never passed to task execution."""
        loader = SWEBenchLoader()
        mock_rec = loader.get_mock_record()

        ws = self.workspace_mgr.create_workspace("mock-leak-test")
        self.workspace_mgr.provision_mock_task(ws)

        try:
            # Execute base commit tests using only task object
            res = self.runner.run_task_at_base_commit(ws, mock_rec.task)
            # Verify result was captured
            self.assertIsNotNone(res)
            self.assertIn("TestCalculator", res.raw_stdout + res.raw_stderr)
            # Confirm gold patch was not injected
            self.assertNotIn("ValueError('Cannot divide by zero')", (ws.path / "src" / "calculator.py").read_text(encoding="utf-8"))
        finally:
            ws.cleanup()

    def test_5_command_result_capture(self):
        """Verify command runner captures stdout, stderr, and exit codes correctly."""
        ws = self.workspace_mgr.create_workspace("cmd-capture-test", init_git=False)
        try:
            res = self.cmd_runner.run(["python", "-c", "import sys; sys.stdout.write('OUT'); sys.stderr.write('ERR'); sys.exit(42)"], cwd=ws.path)
            self.assertEqual(res.exit_code, 42)
            self.assertEqual(res.stdout, "OUT")
            self.assertEqual(res.stderr, "ERR")
            self.assertFalse(res.timed_out)
        finally:
            ws.cleanup()

    def test_6_timeout_handling(self):
        """Verify command runner halts and flags timeout properly."""
        ws = self.workspace_mgr.create_workspace("timeout-test", init_git=False)
        try:
            res = self.cmd_runner.run(["python", "-c", "import time; time.sleep(10)"], cwd=ws.path, timeout=1)
            self.assertTrue(res.timed_out)
            self.assertEqual(res.exit_code, -1)
            self.assertIn("timed out after 1 seconds", res.stderr)
        finally:
            ws.cleanup()

    def test_7_checkout_failure_handling(self):
        """Verify checkout gracefully reports error on non-existent repo or commit."""
        ws = self.workspace_mgr.create_workspace("checkout-fail-test", init_git=False)
        try:
            res = self.workspace_mgr.checkout_repository(
                workspace=ws,
                repo="nonexistent_org/nonexistent_repo_12345",
                base_commit="0000000000000000000000000000000000000000",
                timeout=10,
            )
            self.assertFalse(res.success)
            self.assertIsNotNone(res.error)
            self.assertNotEqual(res.exit_code, 0)
        finally:
            ws.cleanup()

    def test_8_checkout_empty_commit_rejection(self):
        """Verify checkout fails if expected or actual commit is empty."""
        ws = self.workspace_mgr.create_workspace("empty-commit-test", init_git=True)
        try:
            res = self.workspace_mgr.checkout_repository(
                workspace=ws,
                repo="mock-repo",
                base_commit="",
                timeout=10,
            )
            self.assertFalse(res.success)
            self.assertIn("cannot be empty", res.error)
        finally:
            ws.cleanup()

    def test_9_targeted_test_execution(self):
        """Verify run_task_at_base_commit executes only targeted tests when specified."""
        loader = SWEBenchLoader()
        mock_rec = loader.get_mock_record()
        ws = self.workspace_mgr.create_workspace("targeted-test-ws")
        self.workspace_mgr.provision_mock_task(ws)
        try:
            # 1. Target passing test
            res_pass = self.runner.run_task_at_base_commit(
                ws,
                mock_rec.task,
                test_targets=["tests/test_calculator.py::TestCalculator::test_add"],
            )
            self.assertTrue(res_pass.passed)
            self.assertEqual(res_pass.status_label, "PASS")
            self.assertEqual(res_pass.total_tests, 1)
            self.assertEqual(res_pass.passed_tests, 1)
            self.assertEqual(res_pass.failed_tests, 0)

            # 2. Target failing test
            res_fail = self.runner.run_task_at_base_commit(
                ws,
                mock_rec.task,
                test_targets=["tests/test_calculator.py::TestCalculator::test_divide_by_zero"],
            )
            self.assertFalse(res_fail.passed)
            self.assertEqual(res_fail.status_label, "FAIL")
            self.assertEqual(res_fail.total_tests, 1)
            self.assertEqual(res_fail.error_tests + res_fail.failed_tests, 1)
        finally:
            ws.cleanup()

    def test_10_workspace_subfolder_nesting(self):
        """Verify subfolder does not duplicate task ID when already included."""
        ws = self.workspace_mgr.create_workspace(
            task_id="task-123",
            init_git=False,
            subfolder="swebench/task-123",
        )
        try:
            self.assertEqual(ws.path.name, "task-123")
            self.assertEqual(ws.path.parent.name, "swebench")
        finally:
            ws.cleanup()


if __name__ == "__main__":
    unittest.main()
