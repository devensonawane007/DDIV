"""Tests for Targeted Recovery Strategies (A1, A2, A3, A4)."""

import unittest
from recovery.failure_detector import FailureType
from recovery.strategies import RecoveryAction, RecoveryStrategy, StrategySelector


class TestRecoveryStrategies(unittest.TestCase):
    def test_failure_to_strategy_mapping(self):
        self.assertEqual(StrategySelector.map_failure_to_strategy(FailureType.F1), RecoveryStrategy.A1)
        self.assertEqual(StrategySelector.map_failure_to_strategy(FailureType.F2), RecoveryStrategy.A2)
        self.assertEqual(StrategySelector.map_failure_to_strategy(FailureType.F3), RecoveryStrategy.A3)
        self.assertEqual(StrategySelector.map_failure_to_strategy(FailureType.F4), RecoveryStrategy.A4)

    def test_a1_localization_recovery_action(self):
        action = StrategySelector.build_action(
            strategy=RecoveryStrategy.A1,
            diagnosis_text="Wrong file modified",
            located_files=["wrong.py"],
        )
        self.assertEqual(action.strategy, RecoveryStrategy.A1)
        self.assertTrue(action.rerun_locator)
        self.assertTrue(action.rerun_coder)
        self.assertIn("BROADEN SEARCH", action.guidance_for_locator)

    def test_a2_code_reasoning_recovery_action(self):
        action = StrategySelector.build_action(
            strategy=RecoveryStrategy.A2,
            diagnosis_text="Assertion error in divide",
            test_output="AssertionError: 0 != 5",
        )
        self.assertEqual(action.strategy, RecoveryStrategy.A2)
        self.assertFalse(action.rerun_locator)
        self.assertTrue(action.rerun_coder)
        self.assertIn("AssertionError", action.guidance_for_coder)

    def test_a3_execution_recovery_action(self):
        action = StrategySelector.build_action(
            strategy=RecoveryStrategy.A3,
            diagnosis_text="Patch failed to apply cleanly",
        )
        self.assertEqual(action.strategy, RecoveryStrategy.A3)
        self.assertFalse(action.rerun_locator)
        self.assertTrue(action.rerun_coder)
        self.assertIn("unified diff", action.guidance_for_coder)

    def test_a4_strategy_coordination_recovery_action(self):
        action = StrategySelector.build_action(
            strategy=RecoveryStrategy.A4,
            diagnosis_text="Repeated loop detected",
            previous_patch="--- bad patch",
        )
        self.assertEqual(action.strategy, RecoveryStrategy.A4)
        self.assertTrue(action.rerun_locator)
        self.assertTrue(action.rerun_coder)
        self.assertIn("EXPLICITLY BANNED", action.guidance_for_coder)


if __name__ == "__main__":
    unittest.main()
