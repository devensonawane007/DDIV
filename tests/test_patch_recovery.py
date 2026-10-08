"""Offline regression tests for patch validation, malformed diff rejection, sanitization, and A3 recovery."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from evaluation.patch_manager import PatchManager
from evaluation.swebench_evaluator import InternalSWEBenchEvaluator
from evaluation.swebench_loader import SWEBenchGroundTruth, SWEBenchRecord, SWEBenchTask
from evaluation.workspace import TaskWorkspace
from recovery.failure_detector import FailureDetector, FailureType
from recovery.strategies import RecoveryAction, RecoveryStrategy, StrategySelector


class TestPatchRecovery(unittest.TestCase):
    def setUp(self):
        self.patch_mgr = PatchManager()

    def test_valid_unified_diff_accepted(self):
        """1. Verify valid standard unified diff with line coordinates is accepted."""
        valid_patch = (
            "diff --git a/pkg/math_utils.py b/pkg/math_utils.py\n"
            "--- a/pkg/math_utils.py\n"
            "+++ b/pkg/math_utils.py\n"
            "@@ -10,4 +10,6 @@\n"
            " def compute(val):\n"
            "+    if val is None:\n"
            "+        raise ValueError('val required')\n"
            "     return val * 2\n"
        )
        res = self.patch_mgr.validate_patch(valid_patch)
        self.assertTrue(res.is_valid)
        self.assertIn("pkg/math_utils.py", res.modified_files)
        self.assertIsNone(res.error_message)

    def test_malformed_bare_at_diff_rejected(self):
        """2. Verify malformed diff with bare @@ (missing line numbers) is strictly rejected."""
        malformed_patch = (
            "--- a/pkg/math_utils.py\n"
            "+++ b/pkg/math_utils.py\n"
            "@@\n"
            "-    return val * 2\n"
            "+    return val * 3\n"
        )
        res = self.patch_mgr.validate_patch(malformed_patch)
        self.assertFalse(res.is_valid)
        self.assertIn("standard unified diff format", res.error_message)
        self.assertIn("line numbers", res.error_message)

    def test_markdown_fenced_diff_handled_by_sanitization(self):
        """3. Verify markdown code fences are cleanly stripped by sanitize_patch."""
        fenced_patch = (
            "```diff\n"
            "--- a/pkg/core.py\n"
            "+++ b/pkg/core.py\n"
            "@@ -5,3 +5,4 @@\n"
            " def run():\n"
            "+    pass\n"
            "     return True\n"
            "```"
        )
        sanitized = self.patch_mgr.sanitize_patch(fenced_patch)
        self.assertFalse(sanitized.startswith("```"))
        self.assertFalse(sanitized.strip().endswith("```"))
        self.assertTrue(sanitized.startswith("--- a/pkg/core.py"))

        val_res = self.patch_mgr.validate_patch(fenced_patch)
        self.assertTrue(val_res.is_valid)
        self.assertIn("pkg/core.py", val_res.modified_files)

    def test_patch_context_whitespace_preserved(self):
        """4. Verify context lines with single leading space and code indentation are preserved."""
        patch_with_indentation = (
            "--- a/pkg/service.py\n"
            "+++ b/pkg/service.py\n"
            "@@ -20,5 +20,6 @@\n"
            "     class Handler:\n"
            "         def process(self):\n"
            "+            check_auth()\n"
            "             return True\n"
        )
        sanitized = self.patch_mgr.sanitize_patch(patch_with_indentation)
        lines = sanitized.splitlines()
        # Find the context line
        context_line = [l for l in lines if "class Handler:" in l][0]
        self.assertTrue(context_line.startswith("     class Handler:"))
        self.assertEqual(context_line[0], " ")  # Git context line prefix is space

    def test_recovery_can_request_new_candidate(self):
        """5. Verify A3 recovery directive instructs Coder to regenerate with standard hunk syntax."""
        action: RecoveryAction = StrategySelector.build_action(
            strategy=RecoveryStrategy.A3,
            diagnosis_text="Hunk header missing line numbers: found '@@'.",
            test_output="Patch validation error",
            previous_patch="@@\n+bad_code",
            located_files=["pkg/service.py"],
            supervisor_instructions="Reformat diff to include standard line numbers.",
        )
        self.assertEqual(action.strategy, RecoveryStrategy.A3)
        self.assertTrue(action.rerun_coder)
        self.assertIn("PATCH SYNTAX / EXECUTION RECOVERY (A3)", action.guidance_for_coder)
        self.assertIn("@@ -old_start,old_count +new_start,new_count @@", action.guidance_for_coder)
        self.assertIn("NEVER emit a bare '@@'", action.guidance_for_coder)

    def test_invalid_patch_cannot_bypass_evaluation(self):
        """6. Verify that an invalid or malformed patch cannot bypass evaluation and cannot be marked resolved."""
        mock_ws = MagicMock(spec=TaskWorkspace)
        mock_ws.path = Path("fake_workspace")

        task = SWEBenchTask(
            instance_id="test__repo-100",
            repo="test/repo",
            base_commit="abc1234",
            problem_statement="Fix bug in service",
        )
        gt = SWEBenchGroundTruth(
            gold_patch="--- a/file.py\n+++ b/file.py\n@@ -1,1 +1,2 @@\n+fixed\n",
            test_patch="",
            fail_to_pass=["tests/test_mod.py::test_case"],
            pass_to_pass=[],
        )
        record = SWEBenchRecord(task=task, ground_truth=gt)

        evaluator = InternalSWEBenchEvaluator(patch_manager=self.patch_mgr)
        malformed_patch = "Invalid non-diff text"

        result = evaluator.evaluate_candidate_patch(
            workspace=mock_ws,
            record=record,
            candidate_patch=malformed_patch,
        )

        self.assertFalse(result.candidate_patch_applied)
        self.assertFalse(result.internal_resolved)
        self.assertIn("UNRESOLVED_INTERNALLY", result.evaluation_verdict)


if __name__ == "__main__":
    unittest.main()
