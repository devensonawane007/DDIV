"""Validation tests for DDIV evaluation metrics module (core.metrics).

Covers all 14 required verification scenarios using synthetic data:
1. PASS@1 calculation
2. TSR calculation
3. Repair accuracy (empty vs valid incorrect vs valid correct)
4. Regression rate (PASS_TO_PASS failure vs non-regression)
5. Recovery success rate (subsequent attempt success vs failure)
6. Failure detection precision
7. Failure detection recall
8. Failure detection F1
9. Macro-F1 calculation
10. Average repair time (mean and median)
11. Token aggregation
12. N/A handling (baseline/retry recovery, zero-division)
13. Missing token usage handling (null tokens, null cost)
14. Recovery vs first-attempt success distinction
"""

import unittest
from typing import Any, Dict

from core.metrics import (
    ClassMetric,
    ConditionAggregateMetrics,
    ConfusionMatrixResult,
    TaskEvaluationMetrics,
    aggregate_condition_metrics,
    compute_confusion_matrix,
    compute_task_failure_detection,
    compute_task_metrics,
    determine_actual_failure_category,
    format_value,
    generate_summary_table,
)


class TestMetricsEvaluation(unittest.TestCase):
    """Synthetic unit tests for all DDIV evaluation metrics."""

    def test_01_pass_at_1_calculation(self):
        """1. PASS@1 calculation: Attempt 1 success vs Attempt 2 recovery."""
        # Task 1: Succeeded on attempt 1
        record_pass1 = {
            "task_id": "task_1",
            "condition": "full_ddiv",
            "resolved": True,
            "attempts": 1,
            "attempt_history": [
                {"attempt": 1, "internal_resolved": True, "patch_valid": True, "f2p_passed": True, "p2p_passed": True}
            ],
            "execution_duration_seconds": 15.0,
        }
        m1 = compute_task_metrics(record_pass1)
        self.assertTrue(m1.pass_at_1)

        # Task 2: Failed attempt 1, succeeded on attempt 2
        record_pass2 = {
            "task_id": "task_2",
            "condition": "full_ddiv",
            "resolved": True,
            "attempts": 2,
            "attempt_history": [
                {"attempt": 1, "internal_resolved": False, "patch_valid": True, "f2p_passed": False, "p2p_passed": True, "failure_category": "F2"},
                {"attempt": 2, "internal_resolved": True, "patch_valid": True, "f2p_passed": True, "p2p_passed": True},
            ],
            "execution_duration_seconds": 30.0,
        }
        m2 = compute_task_metrics(record_pass2)
        self.assertFalse(m2.pass_at_1)

        # Aggregate across both tasks
        agg = aggregate_condition_metrics([record_pass1, record_pass2], "FULL_DDIV")
        self.assertEqual(agg.total_tasks, 2)
        self.assertEqual(agg.pass_at_1_tasks, 1)
        self.assertAlmostEqual(agg.pass_at_1_rate, 0.5, places=4)
        self.assertEqual(agg.resolved_tasks, 2)
        self.assertAlmostEqual(agg.tsr, 1.0, places=4)

    def test_02_tsr_calculation(self):
        """2. TSR calculation: successfully resolved tasks / total tasks."""
        records = [
            {"task_id": "t1", "condition": "baseline", "resolved": True, "attempts": 1, "attempt_history": [{"attempt": 1, "internal_resolved": True}]},
            {"task_id": "t2", "condition": "baseline", "resolved": True, "attempts": 1, "attempt_history": [{"attempt": 1, "internal_resolved": True}]},
            {"task_id": "t3", "condition": "baseline", "resolved": False, "attempts": 1, "attempt_history": [{"attempt": 1, "internal_resolved": False}]},
            {"task_id": "t4", "condition": "baseline", "resolved": False, "attempts": 1, "attempt_history": [{"attempt": 1, "internal_resolved": False}]},
        ]
        agg = aggregate_condition_metrics(records, "BASELINE")
        self.assertEqual(agg.total_tasks, 4)
        self.assertEqual(agg.resolved_tasks, 2)
        self.assertAlmostEqual(agg.tsr, 0.50, places=4)

    def test_03_repair_accuracy(self):
        """3. Repair accuracy: correct valid patches / valid generated patches.

        Must distinguish:
        - invalid/empty patch
        - valid but incorrect patch
        - correct patch
        """
        # Record with 4 attempts across various tasks:
        # Att 1: empty patch (invalid/empty)
        # Att 2: invalid patch syntax/apply fail (invalid/empty)
        # Att 3: valid patch, but f2p failed (valid incorrect)
        # Att 4: valid patch, f2p & p2p passed (valid correct)
        task_data = {
            "task_id": "t_repair",
            "condition": "retry_only",
            "resolved": True,
            "attempts": 4,
            "attempt_history": [
                {"attempt": 1, "generated_patch": "", "patch_valid": False, "internal_resolved": False},
                {"attempt": 2, "generated_patch": "diff ...", "patch_valid": False, "coder_error_code": "PATCH_BUILDER_FAILED"},
                {"attempt": 3, "generated_patch": "diff valid", "patch_valid": True, "agent_apply_success": True, "f2p_passed": False, "p2p_passed": True},
                {"attempt": 4, "generated_patch": "diff correct", "patch_valid": True, "agent_apply_success": True, "f2p_passed": True, "p2p_passed": True, "internal_resolved": True},
            ],
            "execution_duration_seconds": 40.0,
        }
        agg = aggregate_condition_metrics([task_data], "RETRY_ONLY")
        self.assertEqual(agg.total_patches_generated, 4)
        self.assertEqual(agg.invalid_or_empty_patches, 2)
        self.assertEqual(agg.valid_patches_count, 2)
        self.assertEqual(agg.valid_incorrect_patches, 1)
        self.assertEqual(agg.correct_patches_count, 1)
        # Repair accuracy = 1 correct / 2 valid = 50.0%
        self.assertAlmostEqual(agg.repair_accuracy, 0.5, places=4)

    def test_04_regression_rate(self):
        """4. Regression rate: patches causing PASS_TO_PASS test failure / valid evaluated patches."""
        # Case A: Valid patch, p2p failed -> regression detected
        # Case B: Valid patch, f2p failed but p2p passed -> no regression
        # Case C: Empty patch -> NOT a regression
        task_data = {
            "task_id": "t_reg",
            "condition": "retry_only",
            "resolved": False,
            "attempts": 3,
            "attempt_history": [
                {"attempt": 1, "generated_patch": "", "patch_valid": False, "p2p_passed": False},  # Empty: not regression
                {"attempt": 2, "generated_patch": "valid diff", "patch_valid": True, "agent_apply_success": True, "f2p_passed": False, "p2p_passed": False},  # Regression!
                {"attempt": 3, "generated_patch": "valid diff 2", "patch_valid": True, "agent_apply_success": True, "f2p_passed": False, "p2p_passed": True},  # No regression
            ],
            "execution_duration_seconds": 60.0,
        }
        agg = aggregate_condition_metrics([task_data], "RETRY_ONLY")
        self.assertEqual(agg.valid_evaluated_patches_count, 2)
        self.assertEqual(agg.regression_patches_count, 1)
        self.assertAlmostEqual(agg.regression_rate, 0.50, places=4)

    def test_05_recovery_success_rate(self):
        """5. Recovery success rate: successful recovery events / recovery events attempted."""
        # Task 1: attempt 1 fails, attempt 2 succeeds (1 recovery attempted, 1 successful)
        t1 = {
            "task_id": "t1",
            "condition": "full_ddiv",
            "resolved": True,
            "attempts": 2,
            "attempt_history": [
                {"attempt": 1, "internal_resolved": False, "failure_category": "F3"},
                {"attempt": 2, "internal_resolved": True},
            ],
            "execution_duration_seconds": 20.0,
        }
        # Task 2: attempt 1 fails, attempt 2 fails, attempt 3 fails (2 recoveries attempted, 0 successful)
        t2 = {
            "task_id": "t2",
            "condition": "full_ddiv",
            "resolved": False,
            "attempts": 3,
            "attempt_history": [
                {"attempt": 1, "internal_resolved": False, "failure_category": "F2"},
                {"attempt": 2, "internal_resolved": False, "failure_category": "F2"},
                {"attempt": 3, "internal_resolved": False, "failure_category": "F2"},
            ],
            "execution_duration_seconds": 45.0,
        }
        agg = aggregate_condition_metrics([t1, t2], "FULL_DDIV")
        self.assertEqual(agg.recovery_events_attempted, 3)
        self.assertEqual(agg.recovery_events_successful, 1)
        self.assertAlmostEqual(agg.recovery_success_rate, 1 / 3, places=4)

    def test_06_failure_detection_precision(self):
        """6. Failure detection precision: TP / (TP + FP) per class."""
        samples = [
            ("F3", "F3"),  # TP for F3
            ("F3", "F3"),  # TP for F3
            ("F3", "F2"),  # FP for F3 (Actual was F2)
        ]
        cm = compute_confusion_matrix(samples)
        self.assertIsNotNone(cm)
        f3_metric = cm.per_class["F3"]
        self.assertEqual(f3_metric.tp, 2)
        self.assertEqual(f3_metric.fp, 1)
        # Precision = 2 / (2 + 1) = 0.6667
        self.assertAlmostEqual(f3_metric.precision, 2 / 3, places=4)

    def test_07_failure_detection_recall(self):
        """7. Failure detection recall: TP / (TP + FN) per class."""
        samples = [
            ("F3", "F3"),  # TP for F3
            ("F3", "F3"),  # TP for F3
            ("F2", "F3"),  # FN for F3 (Predicted F2, Actual was F3)
        ]
        cm = compute_confusion_matrix(samples)
        self.assertIsNotNone(cm)
        f3_metric = cm.per_class["F3"]
        self.assertEqual(f3_metric.tp, 2)
        self.assertEqual(f3_metric.fn, 1)
        # Recall = 2 / (2 + 1) = 0.6667
        self.assertAlmostEqual(f3_metric.recall, 2 / 3, places=4)

    def test_08_failure_detection_f1(self):
        """8. Failure detection F1: 2 * P * R / (P + R)."""
        samples = [
            ("F1", "F1"),
            ("F1", "F2"),  # FP for F1
            ("F2", "F1"),  # FN for F1
        ]
        cm = compute_confusion_matrix(samples)
        f1_metric = cm.per_class["F1"]
        # TP = 1, FP = 1, FN = 1
        # P = 0.5, R = 0.5 -> F1 = 0.5
        self.assertAlmostEqual(f1_metric.precision, 0.5, places=4)
        self.assertAlmostEqual(f1_metric.recall, 0.5, places=4)
        self.assertAlmostEqual(f1_metric.f1, 0.5, places=4)

    def test_09_macro_f1_calculation(self):
        """9. Macro-F1: Unweighted mean of per-class F1 scores."""
        samples = [
            ("F1", "F1"),  # F1: P=1.0, R=1.0, F1=1.0
            ("F2", "F2"),  # F2: P=1.0, R=1.0, F1=1.0
            ("F3", "F3"),  # F3: P=1.0, R=1.0, F1=1.0
            ("F4", "F4"),  # F4: P=1.0, R=1.0, F1=1.0
        ]
        cm = compute_confusion_matrix(samples)
        self.assertAlmostEqual(cm.macro_precision, 1.0, places=4)
        self.assertAlmostEqual(cm.macro_recall, 1.0, places=4)
        self.assertAlmostEqual(cm.macro_f1, 1.0, places=4)

    def test_10_average_repair_time(self):
        """10. Average repair time: Mean and median computation."""
        records = [
            {"task_id": "t1", "condition": "baseline", "resolved": True, "attempts": 1, "execution_duration_seconds": 10.0},
            {"task_id": "t2", "condition": "baseline", "resolved": True, "attempts": 1, "execution_duration_seconds": 20.0},
            {"task_id": "t3", "condition": "baseline", "resolved": False, "attempts": 1, "execution_duration_seconds": 60.0},
        ]
        agg = aggregate_condition_metrics(records, "BASELINE")
        self.assertAlmostEqual(agg.mean_repair_time_seconds, 30.0, places=2)
        self.assertAlmostEqual(agg.median_repair_time_seconds, 20.0, places=2)

    def test_11_token_aggregation(self):
        """11. Token usage aggregation across tasks and attempts."""
        records = [
            {
                "task_id": "t1",
                "condition": "full_ddiv",
                "resolved": True,
                "attempts": 1,
                "attempt_history": [
                    {"attempt": 1, "internal_resolved": True, "token_usage": {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200}},
                ],
                "execution_duration_seconds": 10.0,
            },
            {
                "task_id": "t2",
                "condition": "full_ddiv",
                "resolved": True,
                "attempts": 1,
                "attempt_history": [
                    {"attempt": 1, "internal_resolved": True, "token_usage": {"prompt_tokens": 2000, "completion_tokens": 400, "total_tokens": 2400}},
                ],
                "execution_duration_seconds": 12.0,
            },
        ]
        agg = aggregate_condition_metrics(records, "FULL_DDIV")
        self.assertEqual(agg.total_input_tokens, 3000)
        self.assertEqual(agg.total_output_tokens, 600)
        self.assertEqual(agg.total_tokens, 3600)
        self.assertAlmostEqual(agg.average_total_tokens, 1800.0, places=2)

    def test_12_na_handling(self):
        """12. N/A handling: BASELINE and RETRY_ONLY recovery and division-by-zero must return N/A."""
        # In BASELINE: recovery metrics and failure detection must be None (rendering as N/A)
        b_records = [
            {"task_id": "t1", "condition": "baseline", "resolved": False, "attempts": 1, "attempt_history": [{"attempt": 1, "internal_resolved": False}]}
        ]
        b_agg = aggregate_condition_metrics(b_records, "BASELINE")
        self.assertIsNone(b_agg.recovery_events_attempted)
        self.assertIsNone(b_agg.recovery_success_rate)
        self.assertIsNone(b_agg.failure_detection)
        self.assertEqual(format_value(b_agg.recovery_success_rate), "N/A")

        # In RETRY_ONLY: recovery metrics must be None (rendering as N/A)
        r_records = [
            {"task_id": "t1", "condition": "retry_only", "resolved": False, "attempts": 2, "attempt_history": [{"attempt": 1, "internal_resolved": False}, {"attempt": 2, "internal_resolved": False}]}
        ]
        r_agg = aggregate_condition_metrics(r_records, "RETRY_ONLY")
        self.assertIsNone(r_agg.recovery_success_rate)
        self.assertEqual(format_value(r_agg.recovery_success_rate), "N/A")

        # Division by zero: 0 valid patches -> repair_accuracy is None (N/A)
        empty_patch_rec = [
            {"task_id": "t1", "condition": "baseline", "resolved": False, "attempts": 1, "attempt_history": [{"attempt": 1, "generated_patch": "", "patch_valid": False}]}
        ]
        e_agg = aggregate_condition_metrics(empty_patch_rec, "BASELINE")
        self.assertIsNone(e_agg.repair_accuracy)
        self.assertEqual(format_value(e_agg.repair_accuracy), "N/A")

    def test_13_missing_token_usage_handling(self):
        """13. Missing token usage: Tokens and cost must remain None (N/A), never fabricated as 0."""
        record = {
            "task_id": "t_free",
            "condition": "full_ddiv",
            "resolved": True,
            "attempts": 1,
            "attempt_history": [{"attempt": 1, "internal_resolved": True}],  # No token_usage
            "execution_duration_seconds": 15.0,
        }
        m = compute_task_metrics(record)
        self.assertIsNone(m.total_tokens)
        self.assertIsNone(m.input_tokens)
        self.assertIsNone(m.output_tokens)
        self.assertIsNone(m.inference_cost_usd)

        agg = aggregate_condition_metrics([record], "FULL_DDIV")
        self.assertIsNone(agg.total_tokens)
        self.assertIsNone(agg.average_total_tokens)
        self.assertIsNone(agg.total_inference_cost_usd)
        self.assertEqual(format_value(agg.average_total_tokens), "N/A")
        self.assertEqual(format_value(agg.total_inference_cost_usd), "N/A")

    def test_14_recovery_vs_first_attempt_success_distinction(self):
        """14. Recovery vs first-attempt success distinction.

        First-attempt successes do NOT count as recovery events.
        """
        # FULL_DDIV run where task succeeds on Attempt 1:
        record_att1_success = {
            "task_id": "t_first",
            "condition": "full_ddiv",
            "resolved": True,
            "attempts": 1,
            "attempt_history": [
                {"attempt": 1, "internal_resolved": True, "patch_valid": True, "f2p_passed": True, "p2p_passed": True}
            ],
            "execution_duration_seconds": 18.0,
        }
        m = compute_task_metrics(record_att1_success)
        self.assertFalse(m.recovery_triggered)
        self.assertIsNone(m.recovery_success)

        # In aggregate, since 0 recovery events were attempted, recovery_success_rate must be None (N/A)
        agg = aggregate_condition_metrics([record_att1_success], "FULL_DDIV")
        self.assertEqual(agg.recovery_events_attempted, 0)
        self.assertEqual(agg.recovery_events_successful, 0)
        self.assertIsNone(agg.recovery_success_rate)
        self.assertEqual(format_value(agg.recovery_success_rate), "N/A")


if __name__ == "__main__":
    unittest.main()
