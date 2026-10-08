"""Comprehensive unit tests for the improved DDIV pipeline components."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from core.conditions import ExperimentCondition
from core.config import (
    TRUST_FAILURE_DELTA,
    TRUST_REGRESSION_DELTA,
    TRUST_SUCCESS_DELTA,
    DDIVConfig,
)
from core.metrics import (
    ConditionAggregateMetrics,
    aggregate_condition_metrics,
    compute_task_metrics,
    generate_summary_table,
)
from evaluation.context_builder import TargetedContext, TargetedContextBuilder
from evaluation.patch_manager import PatchManager
from evaluation.swebench_evaluator import CleanBaseHealthResult, InternalEvaluationResult
from evaluation.workspace import TaskWorkspace
from memory.memory_store import MemoryStore
from memory.retrieval import MemoryRetriever
from memory.schemas import MemoryRecord
from memory.trust_ledger import TrustLedger
from models.base import ModelConfig
from models.providers import MockModelProvider
from recovery.failure_detector import (
    DetectionResult,
    FailureDetector,
    FailureType,
    GranularFailureType,
)
from agents.test_understanding import RootCauseAnalysis, TestUnderstandingAgent
from agents.patch_critic import PatchCriticAgent, PatchCriticOutput
from agents.supervisor import SupervisorAgent, SupervisorDecision
from agents.base import AgentInputMetadata


class TestImprovedPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace_path = Path(self.temp_dir) / "test_repo"
        self.workspace_path.mkdir(parents=True)

        # Create mock source files
        calc_py = (
            "import math\n\n"
            "class Calculator:\n"
            "    def divide(self, a, b):\n"
            "        return a / b\n\n"
            "    def multiply(self, a, b):\n"
            "        return a * b\n"
        )
        (self.workspace_path / "calculator.py").write_text(calc_py, encoding="utf-8")

        test_calc_py = (
            "import unittest\n"
            "from calculator import Calculator\n\n"
            "class TestCalculator(unittest.TestCase):\n"
            "    def test_divide(self):\n"
            "        c = Calculator()\n"
            "        self.assertEqual(c.divide(10, 2), 5)\n"
        )
        tests_dir = self.workspace_path / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_calculator.py").write_text(test_calc_py, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_targeted_context_builder(self):
        builder = TargetedContextBuilder(char_budget=5000)
        ctx: TargetedContext = builder.build_context(
            workspace_path=self.workspace_path,
            located_files=["calculator.py"],
            target_symbols=["Calculator.divide"],
        )
        self.assertIn("def divide", ctx.formatted_source_code)
        self.assertIn("Calculator", ctx.formatted_source_code)
        self.assertIn("calculator.py", ctx.context_files)
        self.assertGreater(ctx.character_size, 0)
        self.assertLessEqual(ctx.character_size, 5000)

    def test_test_understanding_agent(self):
        provider = MockModelProvider(
            ModelConfig(name="TestUnderstanding", model_id="mock-rca", provider="mock")
        )
        agent = TestUnderstandingAgent(provider)
        meta = AgentInputMetadata(task_id="task-1", run_id="run-1", attempt=1)
        res = agent.execute(
            {
                "issue": "divide() should handle zero division gracefully.",
                "located_symbols": ["Calculator.divide"],
                "source_code": "def divide(self, a, b): return a / b",
                "repo_tests": "def test_divide(self): pass",
            },
            meta,
        )
        self.assertTrue(res.success)
        self.assertIsInstance(res.output, RootCauseAnalysis)
        self.assertTrue(len(res.output.root_cause) > 0)
        self.assertTrue(len(res.output.behavioral_contract) > 0)

    def test_patch_critic_agent_non_blocking(self):
        provider = MockModelProvider(
            ModelConfig(name="PatchCritic", model_id="mock-critic", provider="mock")
        )
        agent = PatchCriticAgent(provider)
        meta = AgentInputMetadata(task_id="task-1", run_id="run-1", attempt=1)
        res = agent.execute(
            {
                "issue": "divide() should handle zero division gracefully.",
                "patch_text": "diff --git a/calc.py b/calc.py\n+if b == 0: raise ValueError()",
                "changed_files": ["calculator.py"],
                "root_cause_analysis": "Missing check on b == 0",
            },
            meta,
        )
        self.assertTrue(res.success)
        self.assertIsInstance(res.output, PatchCriticOutput)
        self.assertIn(res.output.risk_level, ["LOW", "MEDIUM", "HIGH"])

    def test_failure_detector_deterministic_rules(self):
        detector = FailureDetector()

        # F3 on invalid patch
        res = detector.evaluate(
            patch_valid=False,
            patch_applied=False,
            test_passed=False,
        )
        self.assertTrue(res.is_failure)
        self.assertEqual(res.candidate_failure_type, FailureType.F3)
        self.assertEqual(res.granular_failure_type, GranularFailureType.PATCH_INVALID)

        # F1 on locator mismatch
        res = detector.evaluate(
            patch_valid=True,
            patch_applied=True,
            test_passed=False,
            located_files=["calc.py"],
            modified_files=["unrelated.py"],
        )
        self.assertTrue(res.is_failure)
        self.assertEqual(res.candidate_failure_type, FailureType.F1)
        self.assertEqual(res.granular_failure_type, GranularFailureType.LOCATOR_FAILURE)

        # F2 on P2P regression
        res = detector.evaluate(
            patch_valid=True,
            patch_applied=True,
            test_passed=False,
            located_files=["calc.py"],
            modified_files=["calc.py"],
            p2p_passed=False,
            failed_p2p_tests=["test_divide_normal"],
        )
        self.assertTrue(res.is_failure)
        self.assertEqual(res.candidate_failure_type, FailureType.F2)
        self.assertEqual(res.granular_failure_type, GranularFailureType.P2P_REGRESSION)

        # F4 on clean base environment failure
        res = detector.evaluate(
            patch_valid=True,
            patch_applied=True,
            test_passed=False,
            clean_base_passed=False,
        )
        self.assertTrue(res.is_failure)
        self.assertEqual(res.candidate_failure_type, FailureType.F4)
        self.assertEqual(res.granular_failure_type, GranularFailureType.ENVIRONMENT_FAILURE)

    def test_supervisor_strict_mapping(self):
        provider = MockModelProvider(
            ModelConfig(name="Supervisor", model_id="mock-sup", provider="mock")
        )
        provider.injected_failure_type = "F1"
        provider.injected_recovery_strategy = "A1"
        agent = SupervisorAgent(provider)
        meta = AgentInputMetadata(task_id="task-1", run_id="run-1", attempt=1)
        res = agent.execute(
            {
                "task_id": "task-1",
                "max_attempts": 3,
                "issue": "Bug in calc",
            },
            meta,
        )
        self.assertTrue(res.success)
        self.assertIsInstance(res.output, SupervisorDecision)
        self.assertEqual(res.output.failure_category, "F1")
        self.assertEqual(res.output.recovery_strategy, "A1")
        self.assertTrue(hasattr(res.output, "avoid_previous_mistake"))

    def test_trust_ledger_regression_penalty(self):
        db_path = Path(self.temp_dir) / "test_trust.db"
        store = MemoryStore(db_path)
        ledger = TrustLedger(
            memory_store=store,
            initial_trust={"Coder": 0.80},
            success_reward=TRUST_SUCCESS_DELTA,
            failure_penalty=TRUST_FAILURE_DELTA,
            regression_penalty=TRUST_REGRESSION_DELTA,
        )

        # Normal failure penalty
        ledger.update_trust(
            "Coder", "task-1", 1, False, "Tests failed", is_regression=False
        )
        score1 = ledger.get_score("Coder")
        self.assertAlmostEqual(score1, 0.80 - TRUST_FAILURE_DELTA, places=4)

        # Regression penalty
        ledger.update_trust(
            "Coder", "task-1", 2, False, "P2P regression", is_regression=True
        )
        score2 = ledger.get_score("Coder")
        self.assertAlmostEqual(score2, score1 - TRUST_REGRESSION_DELTA, places=4)

        # Check recorded event
        events = ledger.get_transaction_history("Coder")
        self.assertEqual(events[-1].outcome, "REGRESSION")

    def test_memory_retrieval_prioritization(self):
        db_path = Path(self.temp_dir) / "test_mem.db"
        store = MemoryStore(db_path)
        retriever = MemoryRetriever(store)

        # Insert records
        store.insert_record(
            MemoryRecord(
                task_id="task-1",
                repository="repo-a",
                issue_summary="Task 1 attempt 1",
                failure_type="F2",
                failed_tests=["test_1"],
                attempt=1,
                result="FAILED",
            )
        )
        store.insert_record(
            MemoryRecord(
                task_id="task-2",
                repository="repo-a",
                issue_summary="Task 2 matching subsystem",
                failure_type="F2",
                subsystem="calc",
                attempt=1,
                result="SUCCESS",
            )
        )

        matches = retriever.retrieve_context_for_supervisor(
            task_id="task-1",
            repository="repo-a",
            current_failure_candidate="F2",
            subsystem="calc",
        )
        self.assertGreaterEqual(len(matches), 1)
        sources = [m["source"] for m in matches]
        self.assertIn("current_task_history", sources)

    def test_extended_metrics_aggregation(self):
        records = [
            {
                "task_id": "task-1",
                "condition": "full_ddiv",
                "resolved": True,
                "attempts": 2,
                "execution_duration_seconds": 15.0,
                "attempt_history": [
                    {
                        "attempt": 1,
                        "internal_resolved": False,
                        "failure_category": "F2",
                        "patch_valid": True,
                        "agent_apply_success": True,
                        "f2p_passed": False,
                        "p2p_passed": True,
                        "patch_critic": {"approved": False, "risk_level": "HIGH"},
                        "context_characters": 3500,
                        "memory_retrieved": False,
                        "model_invocations": [{"agent": "Coder"}],
                    },
                    {
                        "attempt": 2,
                        "internal_resolved": True,
                        "patch_valid": True,
                        "agent_apply_success": True,
                        "f2p_passed": True,
                        "p2p_passed": True,
                        "patch_critic": {"approved": True, "risk_level": "LOW"},
                        "context_characters": 4000,
                        "memory_retrieved": True,
                        "model_invocations": [{"agent": "Coder"}, {"agent": "Supervisor"}],
                    },
                ],
            }
        ]

        agg = aggregate_condition_metrics(records, "FULL_DDIV")
        self.assertEqual(agg.tsr, 1.0)
        self.assertEqual(agg.pass_at_1_rate, 0.0)
        self.assertEqual(agg.recovery_gain, 1.0)
        self.assertEqual(agg.patch_critic_rejection_rate, 0.5)
        self.assertEqual(agg.memory_retrieval_rate, 1.0)
        self.assertEqual(agg.memory_assisted_recovery_rate, 1.0)
        self.assertAlmostEqual(agg.average_context_characters, 3750.0)

        # Generate summary table
        table = generate_summary_table({"FULL_DDIV": agg})
        self.assertIn("Recovery Gain (TSR - Pass@1)", table)
        self.assertIn("Critic Rejection Rate", table)
        self.assertIn("Memory Retrieval Rate", table)


if __name__ == "__main__":
    unittest.main()
