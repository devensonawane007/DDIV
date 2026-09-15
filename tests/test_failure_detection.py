"""Tests for Failure Detection deterministic rules (F1, F2, F3, F4)."""

import unittest
from recovery.failure_detector import FailureDetector, FailureType


class TestFailureDetection(unittest.TestCase):
    def setUp(self):
        self.detector = FailureDetector()

    def test_no_failure_when_clean_and_passed(self):
        res = self.detector.evaluate(
            patch_valid=True,
            patch_applied=True,
            test_passed=True,
            test_output="OK (Ran 3 tests)",
            located_files=["src/calculator.py"],
            modified_files=["src/calculator.py"],
            current_patch="diff --git a/src/calculator.py b/src/calculator.py",
            previous_attempts=[],
        )
        self.assertFalse(res.is_failure)
        self.assertIsNone(res.candidate_failure_type)

    def test_f3_detection_on_invalid_patch(self):
        res = self.detector.evaluate(
            patch_valid=False,
            patch_applied=False,
            test_passed=False,
            test_output="",
            located_files=["src/calculator.py"],
            modified_files=[],
            current_patch="INVALID PATCH CONTENT",
            previous_attempts=[],
        )
        self.assertTrue(res.is_failure)
        self.assertEqual(res.candidate_failure_type, FailureType.F3)
        self.assertTrue(res.deterministic)

    def test_f3_detection_on_apply_failure(self):
        res = self.detector.evaluate(
            patch_valid=True,
            patch_applied=False,
            test_passed=False,
            test_output="error: patch failed: src/calculator.py:10",
            located_files=["src/calculator.py"],
            modified_files=["src/calculator.py"],
            current_patch="diff content",
            previous_attempts=[],
        )
        self.assertTrue(res.is_failure)
        self.assertEqual(res.candidate_failure_type, FailureType.F3)

    def test_f1_detection_on_disjoint_files(self):
        res = self.detector.evaluate(
            patch_valid=True,
            patch_applied=True,
            test_passed=False,
            test_output="FAIL: test_divide",
            located_files=["src/calculator.py"],
            modified_files=["src/completely_unrelated_module.py"],
            current_patch="diff content",
            previous_attempts=[],
        )
        self.assertTrue(res.is_failure)
        self.assertEqual(res.candidate_failure_type, FailureType.F1)

    def test_f2_detection_on_test_failure(self):
        res = self.detector.evaluate(
            patch_valid=True,
            patch_applied=True,
            test_passed=False,
            test_output="AssertionError: Cannot divide by zero not raised\nFAILED (failures=1)",
            located_files=["src/calculator.py"],
            modified_files=["src/calculator.py"],
            current_patch="diff content",
            previous_attempts=[],
        )
        self.assertTrue(res.is_failure)
        self.assertEqual(res.candidate_failure_type, FailureType.F2)

    def test_f4_detection_on_repeated_patch(self):
        prev_patch = "--- a/src/calc.py\n+++ b/src/calc.py\n@@ -1,1 +1,1 @@"
        current_patch = "--- a/src/calc.py\n+++ b/src/calc.py\n@@ -1,1 +1,1 @@"

        res = self.detector.evaluate(
            patch_valid=True,
            patch_applied=True,
            test_passed=False,
            test_output="FAILED",
            located_files=["src/calc.py"],
            modified_files=["src/calc.py"],
            current_patch=current_patch,
            previous_attempts=[{"attempt": 1, "patch": prev_patch}],
        )
        self.assertTrue(res.is_failure)
        self.assertEqual(res.candidate_failure_type, FailureType.F4)
        self.assertTrue(res.deterministic)


if __name__ == "__main__":
    unittest.main()
