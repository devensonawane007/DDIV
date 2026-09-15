"""Tests for Dynamic Trust Ledger."""

import unittest
from memory.trust_ledger import TrustLedger


class TestTrustLedger(unittest.TestCase):
    def setUp(self):
        self.ledger = TrustLedger(
            initial_trust={"Locator": 0.87, "Coder": 0.74, "Tester": 0.91, "Supervisor": 0.84},
            success_reward=0.05,
            failure_penalty=0.10,
        )

    def test_initial_scores(self):
        self.assertEqual(self.ledger.get_score("Locator"), 0.87)
        self.assertEqual(self.ledger.get_score("Coder"), 0.74)
        self.assertEqual(self.ledger.get_score("Tester"), 0.91)
        self.assertEqual(self.ledger.get_score("Supervisor"), 0.84)

    def test_trust_increase_on_success(self):
        new_score = self.ledger.update_trust(
            agent_id="Coder",
            task_id="t-1",
            attempt=1,
            success=True,
            evidence_reason="Patch passed tests",
        )
        self.assertEqual(new_score, 0.79)
        self.assertEqual(self.ledger.get_score("Coder"), 0.79)

    def test_trust_decrease_on_failure(self):
        new_score = self.ledger.update_trust(
            agent_id="Coder",
            task_id="t-1",
            attempt=1,
            success=False,
            evidence_reason="Patch failed assertions",
        )
        self.assertEqual(new_score, 0.64)

    def test_trust_bounds_clipping(self):
        # Clip at 1.0
        for _ in range(10):
            self.ledger.update_trust("Tester", "t-1", 1, True, "Good assessment")
        self.assertEqual(self.ledger.get_score("Tester"), 1.0)

        # Clip at 0.0
        for _ in range(15):
            self.ledger.update_trust("Coder", "t-1", 1, False, "Failure")
        self.assertEqual(self.ledger.get_score("Coder"), 0.0)

    def test_transaction_history(self):
        self.ledger.update_trust("Coder", "t-1", 1, True, "Reason 1")
        self.ledger.update_trust("Coder", "t-1", 2, False, "Reason 2")
        history = self.ledger.get_transaction_history("Coder")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].outcome, "SUCCESS")
        self.assertEqual(history[1].outcome, "FAILURE")


if __name__ == "__main__":
    unittest.main()
