"""Unit tests for the two-tier evaluation backend architecture in DDIV."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from evaluation.backends import (
    EvaluationBackend,
    EvaluationOutcome,
    EvaluationResult,
    EvaluationTier,
    InternalSWEBenchBackend,
    OfficialSWEbenchBackend,
    TwoTierEvaluator,
)
from evaluation.command_runner import CommandResult
from evaluation.swebench_evaluator import InternalEvaluationResult, OfficialHarnessStatus
from evaluation.swebench_loader import SWEBenchGroundTruth, SWEBenchRecord, SWEBenchTask
from evaluation.workspace import TaskWorkspace


class TestEvaluationBackends(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        self.mock_task = SWEBenchTask(
            instance_id="test__repo-1234",
            repo="test/repo",
            base_commit="abcdef1234567890abcdef1234567890abcdef12",
            problem_statement="Fix bug in foo()",
            hints_text="Check foo.py line 10",
        )
        self.mock_ground_truth = SWEBenchGroundTruth(
            gold_patch="diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n@@ -1,1 +1,1 @@\n-old\n+new",
            test_patch="diff --git a/test_foo.py b/test_foo.py\n--- a/test_foo.py\n+++ b/test_foo.py\n@@ -1,1 +1,1 @@\n-old\n+new",
            fail_to_pass=["tests/test_foo.py::test_fix"],
            pass_to_pass=["tests/test_foo.py::test_existing"],
        )
        self.record = SWEBenchRecord(
            task=self.mock_task,
            ground_truth=self.mock_ground_truth,
        )

    def tearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_enums_and_result_schema(self):
        """Verify tier and outcome enums and EvaluationResult structure."""
        self.assertEqual(EvaluationTier.TIER_1_INTERNAL.value, "tier_1_internal")
        self.assertEqual(EvaluationTier.TIER_2_OFFICIAL.value, "tier_2_official")

        res = EvaluationResult(
            backend_name="test_backend",
            tier=EvaluationTier.TIER_1_INTERNAL,
            task_id="test__repo-1234",
            is_available=True,
            outcome=EvaluationOutcome.RESOLVED,
            verdict="RESOLVED_INTERNALLY",
            duration_seconds=1.5,
            details={"key": "val"},
        )
        data = res.model_dump()
        self.assertEqual(data["backend_name"], "test_backend")
        self.assertEqual(data["tier"], "tier_1_internal")
        self.assertEqual(data["outcome"], "RESOLVED")
        self.assertEqual(data["verdict"], "RESOLVED_INTERNALLY")
        self.assertEqual(data["duration_seconds"], 1.5)
        self.assertIn("key", data["details"])

    def test_internal_backend_no_workspace(self):
        """Internal backend must return error when no workspace is provided."""
        backend = InternalSWEBenchBackend()
        res = backend.evaluate(record=self.record, candidate_patch="dummy patch", workspace=None)

        self.assertEqual(res.outcome, EvaluationOutcome.ERROR)
        self.assertIn("No evaluation workspace provided", res.verdict)
        self.assertIsNotNone(res.error_message)

    def test_internal_backend_resolved(self):
        """Internal backend maps successful evaluation to RESOLVED outcome and verdict."""
        backend = InternalSWEBenchBackend()
        mock_eval_res = InternalEvaluationResult(
            task_id="test__repo-1234",
            candidate_patch_applied=True,
            test_patch_applied=True,
            fail_to_pass_results={"tests/test_foo.py::test_fix": True},
            pass_to_pass_results={"tests/test_foo.py::test_existing": True},
            all_f2p_passed=True,
            all_p2p_passed=True,
            internal_resolved=True,
            evaluation_verdict="RESOLVED_INTERNALLY",
        )

        dummy_ws = TaskWorkspace(workspace_path=self.tmp_path, task_id="test__repo-1234")
        with patch.object(backend.evaluator, "evaluate_candidate_patch", return_value=mock_eval_res):
            res = backend.evaluate(
                record=self.record,
                candidate_patch="diff --git a/foo.py...",
                workspace=dummy_ws,
            )

        self.assertEqual(res.tier, EvaluationTier.TIER_1_INTERNAL)
        self.assertEqual(res.outcome, EvaluationOutcome.RESOLVED)
        self.assertEqual(res.verdict, "RESOLVED_INTERNALLY")
        self.assertTrue(res.details["internal_resolved"])
        self.assertTrue(res.details["all_f2p_passed"])
        self.assertTrue(res.details["all_p2p_passed"])

    def test_internal_backend_unresolved(self):
        """Internal backend maps failed evaluation to UNRESOLVED outcome and verdict."""
        backend = InternalSWEBenchBackend()
        mock_eval_res = InternalEvaluationResult(
            task_id="test__repo-1234",
            candidate_patch_applied=True,
            test_patch_applied=True,
            fail_to_pass_results={"tests/test_foo.py::test_fix": False},
            pass_to_pass_results={"tests/test_foo.py::test_existing": True},
            all_f2p_passed=False,
            all_p2p_passed=True,
            internal_resolved=False,
            evaluation_verdict="UNRESOLVED_INTERNALLY (1 FAIL_TO_PASS tests failed)",
        )

        dummy_ws = TaskWorkspace(workspace_path=self.tmp_path, task_id="test__repo-1234")
        with patch.object(backend.evaluator, "evaluate_candidate_patch", return_value=mock_eval_res):
            res = backend.evaluate(
                record=self.record,
                candidate_patch="diff --git a/foo.py...",
                workspace=dummy_ws,
            )

        self.assertEqual(res.tier, EvaluationTier.TIER_1_INTERNAL)
        self.assertEqual(res.outcome, EvaluationOutcome.UNRESOLVED)
        self.assertIn("UNRESOLVED_INTERNALLY", res.verdict)
        self.assertFalse(res.details["internal_resolved"])

    def test_official_backend_unavailable(self):
        """Official backend strictly returns OFFICIAL_HARNESS_UNAVAILABLE when prerequisites missing."""
        backend = OfficialSWEbenchBackend()
        with patch.object(
            backend.checker,
            "check_harness_availability",
            return_value=OfficialHarnessStatus(
                docker_available=False,
                swebench_package_available=False,
                available=False,
                status="UNAVAILABLE",
                details="Docker daemon is not running.",
            ),
        ):
            res = backend.evaluate(record=self.record, candidate_patch="diff --git...")

        self.assertEqual(res.tier, EvaluationTier.TIER_2_OFFICIAL)
        self.assertEqual(res.outcome, EvaluationOutcome.OFFICIAL_HARNESS_UNAVAILABLE)
        self.assertEqual(res.verdict, "OFFICIAL_HARNESS_UNAVAILABLE")
        self.assertFalse(res.is_available)
        self.assertIn("Docker daemon is not running", res.error_message)
        self.assertEqual(res.details["resolution_claim"], "NOT_EVALUATED")

    def test_official_backend_never_substitutes_internal_verdict(self):
        """Verify official backend never silently substitutes internal evaluation."""
        backend = OfficialSWEbenchBackend()
        with patch.object(
            backend.checker,
            "check_harness_availability",
            return_value=OfficialHarnessStatus(
                docker_available=False,
                swebench_package_available=False,
                available=False,
                status="UNAVAILABLE",
                details="Docker missing",
            ),
        ):
            res = backend.evaluate(record=self.record, candidate_patch="valid_patch")

        self.assertNotEqual(res.verdict, "RESOLVED_INTERNALLY")
        self.assertNotEqual(res.verdict, "RESOLVED")
        self.assertEqual(res.verdict, "OFFICIAL_HARNESS_UNAVAILABLE")

    def test_official_backend_simulated_execution(self):
        """Simulate official harness execution when prerequisites are available."""
        backend = OfficialSWEbenchBackend()

        with patch.object(
            backend.checker,
            "check_harness_availability",
            return_value=OfficialHarnessStatus(
                docker_available=True,
                swebench_package_available=True,
                available=True,
                status="AVAILABLE",
                details="Official harness ready",
            ),
        ):
            def mock_run(cmd, cwd, timeout):
                run_id_arg = cmd[cmd.index("--run_id") + 1]
                report_file = Path(cwd) / f"{run_id_arg}.json"
                report_file.write_text(
                    json.dumps({
                        "resolved_instances": ["test__repo-1234"],
                        "total_instances": 1,
                    }),
                    encoding="utf-8",
                )
                return CommandResult(
                    command=" ".join(cmd),
                    exit_code=0,
                    stdout="Evaluation completed successfully",
                    stderr="",
                    duration_seconds=10.0,
                )

            with patch.object(backend.runner, "run", side_effect=mock_run):
                res = backend.evaluate(record=self.record, candidate_patch="valid_patch")

            self.assertEqual(res.tier, EvaluationTier.TIER_2_OFFICIAL)
            self.assertEqual(res.outcome, EvaluationOutcome.RESOLVED)
            self.assertEqual(res.verdict, "RESOLVED_OFFICIAL")
            self.assertTrue(res.is_available)
            self.assertIn("official_report", res.details)

    def test_two_tier_evaluator_coordination(self):
        """Test TwoTierEvaluator dispatches both tiers independently."""
        two_tier = TwoTierEvaluator()

        mock_internal_res = EvaluationResult(
            backend_name="internal_targeted_evaluator",
            tier=EvaluationTier.TIER_1_INTERNAL,
            task_id="test__repo-1234",
            is_available=True,
            outcome=EvaluationOutcome.RESOLVED,
            verdict="RESOLVED_INTERNALLY",
            duration_seconds=5.0,
            details={"internal_resolved": True},
        )
        mock_official_res = EvaluationResult(
            backend_name="official_swebench_harness",
            tier=EvaluationTier.TIER_2_OFFICIAL,
            task_id="test__repo-1234",
            is_available=False,
            outcome=EvaluationOutcome.OFFICIAL_HARNESS_UNAVAILABLE,
            verdict="OFFICIAL_HARNESS_UNAVAILABLE",
            duration_seconds=0.0,
            details={"resolution_claim": "NOT_EVALUATED"},
        )

        dummy_ws = TaskWorkspace(workspace_path=self.tmp_path, task_id="test__repo-1234")
        with patch.object(two_tier.internal_backend, "evaluate", return_value=mock_internal_res), \
             patch.object(two_tier.official_backend, "evaluate", return_value=mock_official_res):

            internal_eval = two_tier.evaluate_internal(
                record=self.record,
                candidate_patch="patch_str",
                workspace=dummy_ws,
            )
            official_eval = two_tier.evaluate_official(
                record=self.record,
                candidate_patch="patch_str",
            )

        self.assertEqual(internal_eval.tier, EvaluationTier.TIER_1_INTERNAL)
        self.assertEqual(internal_eval.verdict, "RESOLVED_INTERNALLY")
        self.assertEqual(official_eval.tier, EvaluationTier.TIER_2_OFFICIAL)
        self.assertEqual(official_eval.verdict, "OFFICIAL_HARNESS_UNAVAILABLE")

        self.assertNotEqual(internal_eval.verdict, official_eval.verdict)
        self.assertNotEqual(internal_eval.outcome, official_eval.outcome)

    def test_zero_ground_truth_leakage_in_backends(self):
        """Verify backends do not leak gold_patch to the candidate patch or outside evaluation."""
        backend = OfficialSWEbenchBackend()
        candidate = "candidate diff"
        with patch.object(
            backend.checker,
            "check_harness_availability",
            return_value=OfficialHarnessStatus(
                available=False,
                docker_available=False,
                swebench_package_available=False,
                status="UNAVAILABLE",
                details="",
            ),
        ):
            res = backend.evaluate(record=self.record, candidate_patch=candidate)

        self.assertNotIn(self.mock_ground_truth.gold_patch, json.dumps(res.model_dump()))


if __name__ == "__main__":
    unittest.main()
