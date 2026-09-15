"""End-to-end tests for DDIVOrchestrator in Baseline and DDIV modes."""

import tempfile
import unittest
from pathlib import Path

from core.config import DDIVConfig, ExecutionMode
from core.orchestrator import DDIVOrchestrator
from core.state import TaskStatus


class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        base_path = Path(self.tmp_dir.name)

        self.config = DDIVConfig(
            mode=ExecutionMode.MOCK,
            base_dir=base_path,
            memory_db_path=base_path / "memory.db",
            workspace_root=base_path / "workspaces",
            logs_dir=base_path / "logs",
            max_recovery_attempts=3,
        )

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_baseline_mode_stops_after_single_attempt(self):
        self.config.mode = ExecutionMode.BASELINE
        orchestrator = DDIVOrchestrator(self.config)

        state = orchestrator.run_task(
            task_id="mock-baseline-task",
            issue_description="Divide by zero error in Calculator.divide",
            repository="mock-calculator",
        )

        # Baseline must stop after attempt 1
        self.assertEqual(len(state.attempt_history), 1)
        self.assertFalse(state.is_resolved)
        self.assertEqual(state.final_status, TaskStatus.FAILED)

    def test_ddiv_mode_recovers_and_resolves(self):
        self.config.mode = ExecutionMode.DDIV
        orchestrator = DDIVOrchestrator(self.config)

        state = orchestrator.run_task(
            task_id="mock-ddiv-task",
            issue_description="Divide by zero error in Calculator.divide",
            repository="mock-calculator",
        )

        # In DDIV mode:
        # Attempt 1: Fails with F2
        # Supervisor diagnoses F2 and prescribes A2
        # Attempt 2: Coder incorporates A2 instructions, repairs patch
        # Tests pass -> SUCCESS!
        self.assertTrue(state.is_resolved)
        self.assertEqual(state.final_status, TaskStatus.SUCCESS)
        self.assertEqual(len(state.attempt_history), 2)

        attempt1 = state.attempt_history[0]
        self.assertFalse(attempt1.test_passed)
        self.assertEqual(attempt1.failure_type, "F2")
        self.assertEqual(attempt1.recovery_action, "A2")

        attempt2 = state.attempt_history[1]
        self.assertTrue(attempt2.test_passed)

        # Check trust scores
        coder_trust = orchestrator.trust_ledger.get_score("Coder")
        self.assertGreater(coder_trust, 0.0)

        # Check memory store
        records = orchestrator.memory_store.get_records_by_task("mock-ddiv-task")
        self.assertGreaterEqual(len(records), 2)


if __name__ == "__main__":
    unittest.main()
