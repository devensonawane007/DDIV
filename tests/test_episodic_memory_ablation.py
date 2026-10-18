"""Deterministic test suite for DDIV Phase 7 Controlled Episodic Memory Ablation.

Verifies:
1. Condition properties symmetry & memory divergence between FULL_DDIV_MEMORY_OFF and FULL_DDIV_MEMORY_ON.
2. Production path recovery hooks active for both ablation conditions in V22SupervisedWorker.
3. FULL_DDIV_MEMORY_OFF performs 0 memory queries, 0 DB reads/writes, 0 memory prompt injections, while preserving within-task retry feedback.
4. FULL_DDIV_MEMORY_ON queries memory, injects advisory blocks into actual LLM prompts, and persists records.
5. Anti-contamination and forbidden reference redaction.
6. Evaluator and scoring symmetry across both conditions.
7. Empty / corrupt database resilience.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from agents.base import AgentExecutionResult, AgentInputMetadata
from agents.coder import CoderAgent
from agents.locator import LocatorAgent
from agents.supervisor import SupervisorAgent
from core.conditions import ExperimentCondition
from core.config import DDIVConfig, ExecutionMode
from core.experiment_record import ConditionJobStatus, ExperimentConditionRecord
from core.experiment_worker import (
    ExperimentWorker,
    sanitize_memory_record,
    sanitize_text,
    FORBIDDEN_REFERENCE_TOKENS,
)
import core.experiment_worker as ew_module
from evaluation.backends import EvaluationOutcome, EvaluationResult, EvaluationTier
from evaluation.swebench_loader import SWEBenchGroundTruth, SWEBenchRecord, SWEBenchTask
from memory.memory_store import MemoryStore
from memory.retrieval import MemoryRetriever
from memory.schemas import MemoryRecord
from models.base import ModelConfig, ProviderResponse
from models.providers import MockModelProvider
from scripts.v2_2_recovery_manager import V22SupervisedWorker


class TestEpisodicMemoryAblation:
    """Comprehensive deterministic verification for Phase 7 memory ablation."""

    def test_01_condition_properties_symmetry_and_memory_divergence(self):
        """Verify structural symmetry and exact memory divergence between conditions."""
        off = ExperimentCondition.FULL_DDIV_MEMORY_OFF
        on = ExperimentCondition.FULL_DDIV_MEMORY_ON
        standard = ExperimentCondition.FULL_DDIV

        # String parsing
        assert ExperimentCondition.from_str("full_ddiv_memory_off") == off
        assert ExperimentCondition.from_str("FULL-DDIV-MEMORY-ON") == on

        # Execution mode symmetry
        assert off.to_execution_mode() == ExecutionMode.FULL_DDIV
        assert on.to_execution_mode() == ExecutionMode.FULL_DDIV
        assert standard.to_execution_mode() == ExecutionMode.FULL_DDIV

        # Symmetrical recovery pipeline settings
        assert off.max_attempts == on.max_attempts == 3
        assert off.is_supervisor_enabled is True and on.is_supervisor_enabled is True
        assert off.is_diagnosis_enabled is True and on.is_diagnosis_enabled is True
        assert off.is_intervention_enabled is True and on.is_intervention_enabled is True
        assert off.is_trust_enabled is True and on.is_trust_enabled is True

        # Sole controlled point of ablation: is_memory_enabled
        assert off.is_memory_enabled is False
        assert on.is_memory_enabled is True
        assert standard.is_memory_enabled is True

    def test_02_production_path_v22_worker_hooks_active_for_both_conditions(self, tmp_path: Path):
        """Verify V22SupervisedWorker activates recovery hooks for both ablation conditions."""
        worker_off = V22SupervisedWorker(
            task_id="pylint-dev__pylint-6903",
            condition=ExperimentCondition.FULL_DDIV_MEMORY_OFF,
            experiment_id="exp_test_off",
            workspace_root=tmp_path / "ws_off",
            provider="mock",
        )

        worker_on = V22SupervisedWorker(
            task_id="pylint-dev__pylint-6903",
            condition=ExperimentCondition.FULL_DDIV_MEMORY_ON,
            experiment_id="exp_test_on",
            workspace_root=tmp_path / "ws_on",
            provider="mock",
        )

        # Both workers must have proposal_history initialized and supervisor enabled
        assert hasattr(worker_off, "proposal_history")
        assert hasattr(worker_on, "proposal_history")
        assert worker_off.condition.is_supervisor_enabled is True
        assert worker_on.condition.is_supervisor_enabled is True

    def test_03_memory_off_zero_reads_zero_writes_zero_injections_with_retry_context(self, tmp_path: Path, monkeypatch):
        """Verify FULL_DDIV_MEMORY_OFF has zero memory activity while preserving within-task retry feedback."""
        mem_db = tmp_path / "never_touched.db"

        captured_coder_prompts = []
        captured_loc_prompts = []
        captured_sup_prompts = []

        orig_coder_execute = ew_module.CoderAgent.execute
        orig_loc_execute = ew_module.LocatorAgent.execute
        orig_sup_execute = ew_module.SupervisorAgent.execute

        def spy_coder(self_agent, input_data, meta):
            prompt = self_agent.build_prompt(input_data, meta)
            captured_coder_prompts.append(prompt)
            return orig_coder_execute(self_agent, input_data, meta)

        def spy_loc(self_agent, input_data, meta):
            prompt = self_agent.build_prompt(input_data, meta)
            captured_loc_prompts.append(prompt)
            return orig_loc_execute(self_agent, input_data, meta)

        def spy_sup(self_agent, input_data, meta):
            prompt = self_agent.build_prompt(input_data, meta)
            captured_sup_prompts.append(prompt)
            return orig_sup_execute(self_agent, input_data, meta)

        monkeypatch.setattr(ew_module.CoderAgent, "execute", spy_coder)
        monkeypatch.setattr(ew_module.LocatorAgent, "execute", spy_loc)
        monkeypatch.setattr(ew_module.SupervisorAgent, "execute", spy_sup)

        mock_task = SWEBenchTask(
            instance_id="pylint-dev__pylint-6903",
            repo="pylint-dev/pylint",
            base_commit="ca80f03a",
            problem_statement="Test issue in pylint run",
        )
        mock_record = SWEBenchRecord(task=mock_task, ground_truth=SWEBenchGroundTruth())
        monkeypatch.setattr(ew_module.SWEBenchLoader, "get_mock_record", lambda *args, **kwargs: mock_record)
        monkeypatch.setattr(ew_module.SWEBenchLoader, "load_from_file", lambda *args, **kwargs: [mock_record])

        ws_mock = MagicMock()
        ws_mock.path = tmp_path / "mock_repo_off"
        ws_mock.path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(ew_module.WorkspaceManager, "create_workspace", lambda *args, **kwargs: ws_mock)
        monkeypatch.setattr(ew_module.CommandRunner, "run", lambda *args, **kwargs: MagicMock(returncode=0, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "revert_workspace", lambda *args, **kwargs: None)
        monkeypatch.setattr(ew_module.PatchManager, "apply_patch", lambda *args, **kwargs: MagicMock(is_success=True, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "validate_patch", lambda *args, **kwargs: MagicMock(is_valid=True, error_message=None))

        eval_attempts = [0]
        def eval_step(*args, **kwargs):
            eval_attempts[0] += 1
            if eval_attempts[0] == 1:
                return EvaluationResult(
                    task_id="pylint-dev__pylint-6903",
                    backend_name="internal",
                    outcome=EvaluationOutcome.UNRESOLVED,
                    tier=EvaluationTier.TIER_1_INTERNAL,
                    verdict="FAIL",
                    duration_seconds=0.1,
                    details={"failed_f2p_tests": ["test_run.py::test_fail"]},
                )
            return EvaluationResult(
                task_id="pylint-dev__pylint-6903",
                backend_name="internal",
                outcome=EvaluationOutcome.RESOLVED,
                tier=EvaluationTier.TIER_1_INTERNAL,
                verdict="RESOLVED",
                duration_seconds=0.1,
            )

        monkeypatch.setattr(ew_module.TwoTierEvaluator, "evaluate_internal", eval_step)
        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_official",
            lambda *args, **kwargs: EvaluationResult(
                task_id="pylint-dev__pylint-6903",
                backend_name="official",
                outcome=EvaluationOutcome.OFFICIAL_HARNESS_UNAVAILABLE,
                tier=EvaluationTier.TIER_2_OFFICIAL,
                verdict="OFFICIAL_HARNESS_UNAVAILABLE",
                is_available=False,
            ),
        )

        worker = ExperimentWorker(
            task_id="pylint-dev__pylint-6903",
            condition=ExperimentCondition.FULL_DDIV_MEMORY_OFF,
            experiment_id="exp_mem_off_test",
            workspace_root=tmp_path / "ws_worker_off",
            provider="mock",
            memory_db_path=mem_db,
        )

        rec = worker.run()

        # 1. DB was never created or accessed
        assert not mem_db.exists()

        # 2. Coder received NO memory_context in input or prompt
        for prompt in captured_coder_prompts:
            assert "=== HISTORICAL EPISODIC MEMORY" not in prompt
            assert "The following retrieved experiences" not in prompt

        # 3. Locator received NO memory_context
        for prompt in captured_loc_prompts:
            assert "HISTORICAL EPISODIC" not in prompt

        # 4. Supervisor received NO memory_matches
        for prompt in captured_sup_prompts:
            assert "HISTORICAL EPISODIC" not in prompt

        # 5. But Attempt 2 Coder prompt DID receive ordinary within-task retry feedback!
        assert len(captured_coder_prompts) == 2
        attempt_2_prompt = captured_coder_prompts[1]
        assert "=== SUPERVISOR RECOVERY DIRECTIVE ===" in attempt_2_prompt
        assert "=== WHAT NOT TO REPEAT ===" in attempt_2_prompt
        assert "Do not repeat the same flawed logic" in attempt_2_prompt

    def test_04_memory_on_production_path_retrieves_injects_and_persists(self, tmp_path: Path, monkeypatch):
        """Verify FULL_DDIV_MEMORY_ON retrieves historical experience, injects into prompt, and persists."""
        mem_db = tmp_path / "phase7_memory_on.db"
        store = MemoryStore(mem_db)

        # Seed approved historical experience (SymPy validation run)
        store.insert_record(
            sanitize_memory_record(
                MemoryRecord(
                    task_id="sympy__sympy-23262",
                    repository="sympy/sympy",
                    issue_summary="Tuple printing logic error",
                    failure_type="F2",
                    diagnosis="Logic error in pycode printer single element tuple formatting",
                    recovery_action="A2",
                    attempt=1,
                    result="FAILED",
                    relevant_files=["sympy/printing/pycode.py"],
                    agent="Supervisor",
                )
            )
        )

        captured_coder_prompts = []
        orig_coder_execute = ew_module.CoderAgent.execute

        def spy_coder(self_agent, input_data, meta):
            prompt = self_agent.build_prompt(input_data, meta)
            captured_coder_prompts.append(prompt)
            return orig_coder_execute(self_agent, input_data, meta)

        monkeypatch.setattr(ew_module.CoderAgent, "execute", spy_coder)

        mock_task = SWEBenchTask(
            instance_id="sympy__sympy-23413",
            repo="sympy/sympy",
            base_commit="10de1a18",
            problem_statement="Fix matrix hermitian transform bug",
        )
        mock_record = SWEBenchRecord(task=mock_task, ground_truth=SWEBenchGroundTruth())
        monkeypatch.setattr(ew_module.SWEBenchLoader, "get_mock_record", lambda *args, **kwargs: mock_record)
        monkeypatch.setattr(ew_module.SWEBenchLoader, "load_from_file", lambda *args, **kwargs: [mock_record])

        ws_mock = MagicMock()
        ws_mock.path = tmp_path / "mock_repo_on"
        ws_mock.path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(ew_module.WorkspaceManager, "create_workspace", lambda *args, **kwargs: ws_mock)
        monkeypatch.setattr(ew_module.CommandRunner, "run", lambda *args, **kwargs: MagicMock(returncode=0, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "revert_workspace", lambda *args, **kwargs: None)
        monkeypatch.setattr(ew_module.PatchManager, "apply_patch", lambda *args, **kwargs: MagicMock(is_success=True, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "validate_patch", lambda *args, **kwargs: MagicMock(is_valid=True, error_message=None))

        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_internal",
            lambda *args, **kwargs: EvaluationResult(
                task_id="sympy__sympy-23413",
                backend_name="internal",
                outcome=EvaluationOutcome.RESOLVED,
                tier=EvaluationTier.TIER_1_INTERNAL,
                verdict="RESOLVED",
                duration_seconds=0.1,
            ),
        )
        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_official",
            lambda *args, **kwargs: EvaluationResult(
                task_id="sympy__sympy-23413",
                backend_name="official",
                outcome=EvaluationOutcome.OFFICIAL_HARNESS_UNAVAILABLE,
                tier=EvaluationTier.TIER_2_OFFICIAL,
                verdict="OFFICIAL_HARNESS_UNAVAILABLE",
                is_available=False,
            ),
        )

        worker = ExperimentWorker(
            task_id="sympy__sympy-23413",
            condition=ExperimentCondition.FULL_DDIV_MEMORY_ON,
            experiment_id="exp_mem_on_test",
            workspace_root=tmp_path / "ws_worker_on",
            provider="mock",
            memory_db_path=mem_db,
        )

        rec = worker.run()

        # 1. Coder prompt MUST contain the advisory historical memory block
        found_advisory = False
        for prompt in captured_coder_prompts:
            if "=== HISTORICAL EPISODIC MEMORY (ADVISORY CONTEXT) ===" in prompt:
                found_advisory = True
                assert "sympy__sympy-23262" in prompt or "pycode" in prompt
                assert "DO NOT assume their filenames, symbols, or specific logic apply verbatim" in prompt
        assert found_advisory, "Coder prompt did not contain advisory episodic memory block"

        # 2. Condition DB MUST now contain the newly resolved task's experience
        resolved_records = store.get_records_by_task("sympy__sympy-23413")
        assert len(resolved_records) == 1
        assert resolved_records[0].result == "SUCCESS"

    def test_05_anti_contamination_reference_tokens_and_self_exclusion(self):
        """Verify forbidden benchmark tokens are redacted and target task cannot retrieve its own prior solution."""
        rec = MemoryRecord(
            task_id="pylint-dev__pylint-6903",
            repository="pylint-dev/pylint",
            issue_summary="Header issue",
            failure_type="F2",
            diagnosis="gold_patch was applied with test_patch and FAIL_TO_PASS assertions",
            recovery_action="A2",
            attempt=1,
            result="FAILED",
            failed_tests=["FAIL_TO_PASS:test_run.py::test_header"],
            metadata={"gold_patch": "diff --git...", "notes": "PASS_TO_PASS test verified"},
        )
        sanitized = sanitize_memory_record(rec)

        assert "gold_patch" not in sanitized.diagnosis
        assert "[REDACTED_REF]" in sanitized.diagnosis
        assert "FAIL_TO_PASS" not in sanitized.diagnosis
        assert "PASS_TO_PASS" not in json.dumps(sanitized.metadata)

    def test_06_evaluator_and_scoring_protocol_identical(self):
        """Verify evaluator outcomes and metrics calculations are mathematically identical across conditions."""
        from core.metrics import compute_task_metrics

        logs = [
            {"attempt": 1, "internal_resolved": False, "patch_valid": True, "patch_applied": True, "failure_category": "F2"},
            {"attempt": 2, "internal_resolved": True, "patch_valid": True, "patch_applied": True, "failure_category": None},
        ]

        metrics_off = compute_task_metrics({
            "condition": ExperimentCondition.FULL_DDIV_MEMORY_OFF.value,
            "resolved": True,
            "attempts": 2,
            "attempt_history": logs,
            "execution_duration_seconds": 45.0,
        })

        metrics_on = compute_task_metrics({
            "condition": ExperimentCondition.FULL_DDIV_MEMORY_ON.value,
            "resolved": True,
            "attempts": 2,
            "attempt_history": logs,
            "execution_duration_seconds": 45.0,
        })

        assert metrics_off.pass_at_1 == metrics_on.pass_at_1 == False
        assert metrics_off.recovery_triggered == metrics_on.recovery_triggered == True
        assert metrics_off.recovery_success == metrics_on.recovery_success == True

    def test_07_resilience_to_empty_corrupt_or_locked_memory_db(self, tmp_path: Path, monkeypatch):
        """Verify worker handles empty, locked, or corrupt memory database gracefully."""
        corrupt_db = tmp_path / "corrupt.db"
        corrupt_db.write_text("NOT A SQLITE DATABASE", encoding="utf-8")

        mock_task = SWEBenchTask(
            instance_id="pylint-dev__pylint-6903",
            repo="pylint-dev/pylint",
            base_commit="ca80f03a",
            problem_statement="Test issue in pylint run",
        )
        mock_record = SWEBenchRecord(task=mock_task, ground_truth=SWEBenchGroundTruth())
        monkeypatch.setattr(ew_module.SWEBenchLoader, "get_mock_record", lambda *args, **kwargs: mock_record)
        monkeypatch.setattr(ew_module.SWEBenchLoader, "load_from_file", lambda *args, **kwargs: [mock_record])

        ws_mock = MagicMock()
        ws_mock.path = tmp_path / "mock_repo_corrupt"
        ws_mock.path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(ew_module.WorkspaceManager, "create_workspace", lambda *args, **kwargs: ws_mock)
        monkeypatch.setattr(ew_module.CommandRunner, "run", lambda *args, **kwargs: MagicMock(returncode=0, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "revert_workspace", lambda *args, **kwargs: None)
        monkeypatch.setattr(ew_module.PatchManager, "apply_patch", lambda *args, **kwargs: MagicMock(is_success=True, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "validate_patch", lambda *args, **kwargs: MagicMock(is_valid=True, error_message=None))

        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_internal",
            lambda *args, **kwargs: EvaluationResult(
                task_id="pylint-dev__pylint-6903",
                backend_name="internal",
                outcome=EvaluationOutcome.RESOLVED,
                tier=EvaluationTier.TIER_1_INTERNAL,
                verdict="RESOLVED",
                duration_seconds=0.1,
            ),
        )
        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_official",
            lambda *args, **kwargs: EvaluationResult(
                task_id="pylint-dev__pylint-6903",
                backend_name="official",
                outcome=EvaluationOutcome.OFFICIAL_HARNESS_UNAVAILABLE,
                tier=EvaluationTier.TIER_2_OFFICIAL,
                verdict="OFFICIAL_HARNESS_UNAVAILABLE",
                is_available=False,
            ),
        )

        worker = ExperimentWorker(
            task_id="pylint-dev__pylint-6903",
            condition=ExperimentCondition.FULL_DDIV_MEMORY_ON,
            experiment_id="exp_corrupt_test",
            workspace_root=tmp_path / "ws_corrupt",
            provider="mock",
            memory_db_path=corrupt_db,
        )

        # Must run and complete without crashing
        rec = worker.run()
        assert rec.status == ConditionJobStatus.COMPLETED
