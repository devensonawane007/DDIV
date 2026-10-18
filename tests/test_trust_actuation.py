"""Deterministic offline verification suite for DDIV trust-score actuation and recovery integration.

Verifies:
1. High-trust path: Coder trust >= 0.70 proceeds directly without critique requirement.
2. Low-trust valid path: Coder trust < 0.70 invokes deterministic critique on workspace patch; valid patch passes and resolves.
3. Low-trust rejected path: Coder trust < 0.70 invokes critique; placeholder / no-op patch is rejected, converting outcome to UNRESOLVED and blocking premature resolution.
4. Exact threshold boundary: 0.70 is high trust (no critique required); 0.6999 is low trust (critique required).
5. Failing-test invariance: Failing tests (f2p_passed=False) are NEVER accepted regardless of trust score.
6. Genuine recovery loop: Critique rejection on Attempt 1 feeds directive to Attempt 2 Coder prompt, respecting retry budget.
7. Controlled cross-task lesson transfer with provenance without persistent production memory pollution.
"""

from __future__ import annotations

import ast
from pathlib import Path
import tempfile
import shutil
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import pytest

from agents.base import AgentExecutionResult, AgentInputMetadata
from agents.coder import CoderAgent, CoderOutput
from agents.supervisor import SupervisorAgent, SupervisorDecision
from core.conditions import ExperimentCondition
from core.config import DDIVConfig, CODER_TRUST_CRITIQUE_THRESHOLD
from core.experiment_record import ConditionJobStatus, ExperimentConditionRecord
from core.experiment_worker import ExperimentWorker, sanitize_memory_record
import core.experiment_worker as ew_module
from evaluation.backends import EvaluationOutcome, EvaluationResult, EvaluationTier
from evaluation.patch_builder import CodeModification
from evaluation.swebench_loader import SWEBenchGroundTruth, SWEBenchRecord, SWEBenchTask
from memory.memory_store import MemoryStore
from memory.retrieval import MemoryRetriever
from memory.schemas import MemoryRecord
from memory.trust_ledger import TrustLedger


class TestTrustActuation:
    """Comprehensive test suite for trust-score actuation and recovery integration."""

    @pytest.fixture
    def test_env(self, tmp_path: Path):
        """Setup isolated temporary workspace and task fixtures."""
        ws_dir = tmp_path / "workspace"
        ws_dir.mkdir(parents=True, exist_ok=True)
        src_file = ws_dir / "calc.py"
        src_file.write_text(
            "def compute(a, b):\n    # base implementation\n    return a + b\n",
            encoding="utf-8",
        )

        mem_db = tmp_path / "test_trust.db"
        task = SWEBenchTask(
            instance_id="calc__issue-1",
            repo="calc/calc",
            base_commit="abc1234",
            problem_statement="Fix subtraction handling in compute",
        )
        record = SWEBenchRecord(task=task, ground_truth=SWEBenchGroundTruth())
        return {
            "tmp_path": tmp_path,
            "ws_dir": ws_dir,
            "src_file": src_file,
            "mem_db": mem_db,
            "task": task,
            "record": record,
        }

    def test_01_high_trust_path_direct_resolution(self, test_env, monkeypatch):
        """High coder trust (>= 0.70) bypasses critique and resolves directly when tests pass."""
        env = test_env
        ws_mock = MagicMock()
        ws_mock.path = env["ws_dir"]

        monkeypatch.setattr(ew_module.SWEBenchLoader, "load_from_file", lambda *a, **kw: [env["record"]])
        monkeypatch.setattr(ew_module.WorkspaceManager, "create_workspace", lambda *a, **kw: ws_mock)
        monkeypatch.setattr(ew_module.CommandRunner, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "revert_workspace", lambda *a, **kw: None)
        monkeypatch.setattr(ew_module.PatchManager, "apply_patch", lambda *a, **kw: MagicMock(is_success=True, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "validate_patch", lambda *a, **kw: MagicMock(is_valid=True, error_message=None))

        # Tests pass on attempt 1
        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_internal",
            lambda *a, **kw: EvaluationResult(
                task_id=env["task"].instance_id,
                backend_name="internal",
                outcome=EvaluationOutcome.RESOLVED,
                tier=EvaluationTier.TIER_1_INTERNAL,
                verdict="RESOLVED",
                duration_seconds=0.1,
                details={"all_f2p_passed": True, "all_p2p_passed": True},
            ),
        )

        # High trust initial: Coder = 0.85 (>= 0.70)
        cfg = DDIVConfig.load_from_env()
        cfg.init_trust_coder = 0.85
        cfg.coder_trust_critique_threshold = 0.70

        worker = ExperimentWorker(
            task_id=env["task"].instance_id,
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="test_exp_high",
            workspace_root=env["tmp_path"] / "root_high",
            provider="mock",
            config=cfg,
            memory_db_path=env["mem_db"],
        )

        rec = worker.run()

        # Observable outcomes:
        assert rec.resolved is True
        assert rec.workflow_completed is True
        assert rec.attempts == 1
        assert len(rec.attempt_history) == 1
        # High trust: critique not required
        assert rec.attempt_history[0]["trust_critique_required"] is False
        assert rec.attempt_history[0]["trust_critique_passed"] is True

    def test_02_low_trust_valid_patch_passes_critique_and_resolves(self, test_env, monkeypatch):
        """Low coder trust (< 0.70) invokes critique; clean patch passes critique and resolves."""
        env = test_env
        ws_mock = MagicMock()
        ws_mock.path = env["ws_dir"]

        monkeypatch.setattr(ew_module.SWEBenchLoader, "load_from_file", lambda *a, **kw: [env["record"]])
        monkeypatch.setattr(ew_module.WorkspaceManager, "create_workspace", lambda *a, **kw: ws_mock)
        monkeypatch.setattr(ew_module.CommandRunner, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "revert_workspace", lambda *a, **kw: None)

        valid_diff = (
            "--- a/calc.py\n"
            "+++ b/calc.py\n"
            "@@ -1,3 +1,3 @@\n"
            " def compute(a, b):\n"
            "-    return a + b\n"
            "+    return a - b\n"
        )
        monkeypatch.setattr(ew_module.PatchManager, "apply_patch", lambda *a, **kw: MagicMock(is_success=True, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "validate_patch", lambda *a, **kw: MagicMock(is_valid=True, error_message=None))

        # Write actual modified content to workspace file so AST critique checks it
        env["src_file"].write_text("def compute(a, b):\n    return a - b\n", encoding="utf-8")

        # Mock Coder to emit valid patch
        monkeypatch.setattr(
            ew_module.CoderAgent,
            "execute",
            lambda self, in_data, meta: AgentExecutionResult(
                task_id=meta.task_id,
                run_id=meta.run_id,
                agent_id="Coder",
                attempt=meta.attempt,
                success=True,
                output=CoderOutput(
                    patch=valid_diff,
                    modified_files=["calc.py"],
                    reasoning_summary="Fixed subtraction logic",
                    confidence=0.95,
                ),
            ),
        )

        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_internal",
            lambda *a, **kw: EvaluationResult(
                task_id=env["task"].instance_id,
                backend_name="internal",
                outcome=EvaluationOutcome.RESOLVED,
                tier=EvaluationTier.TIER_1_INTERNAL,
                verdict="RESOLVED",
                duration_seconds=0.1,
                details={"all_f2p_passed": True, "all_p2p_passed": True},
            ),
        )

        # Low trust initial: Coder = 0.50 (< 0.70)
        cfg = DDIVConfig.load_from_env()
        cfg.init_trust_coder = 0.50
        cfg.coder_trust_critique_threshold = 0.70

        worker = ExperimentWorker(
            task_id=env["task"].instance_id,
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="test_exp_low_valid",
            workspace_root=env["tmp_path"] / "root_low_valid",
            provider="mock",
            config=cfg,
            memory_db_path=env["mem_db"],
        )

        rec = worker.run()

        # Observable outcomes:
        assert rec.resolved is True
        assert rec.attempts == 1
        # Low trust triggered critique and it passed
        assert rec.attempt_history[0]["trust_critique_required"] is True
        assert rec.attempt_history[0]["trust_critique_passed"] is True
        assert "passed in workspace" in rec.attempt_history[0]["trust_critique_reason"]

    def test_03_low_trust_rejected_patch_converts_to_unresolved(self, test_env, monkeypatch):
        """Low coder trust (< 0.70) critique catches placeholder/no-op patch, blocking resolution."""
        env = test_env
        ws_mock = MagicMock()
        ws_mock.path = env["ws_dir"]

        monkeypatch.setattr(ew_module.SWEBenchLoader, "load_from_file", lambda *a, **kw: [env["record"]])
        monkeypatch.setattr(ew_module.WorkspaceManager, "create_workspace", lambda *a, **kw: ws_mock)
        monkeypatch.setattr(ew_module.CommandRunner, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "revert_workspace", lambda *a, **kw: None)

        # Patch contains executable code with forbidden placeholder: "# TODO: implement real fix"
        placeholder_diff = (
            "--- a/calc.py\n"
            "+++ b/calc.py\n"
            "@@ -1,3 +1,4 @@\n"
            " def compute(a, b):\n"
            "+    res = a + b  # TODO: implement real fix\n"
            "+    return res\n"
            "-    return a + b\n"
        )
        monkeypatch.setattr(ew_module.PatchManager, "apply_patch", lambda *a, **kw: MagicMock(is_success=True, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "validate_patch", lambda *a, **kw: MagicMock(is_valid=True, error_message=None))

        # Mock Coder to emit placeholder diff
        monkeypatch.setattr(
            ew_module.CoderAgent,
            "execute",
            lambda self, in_data, meta: AgentExecutionResult(
                task_id=meta.task_id,
                run_id=meta.run_id,
                agent_id="Coder",
                attempt=meta.attempt,
                success=True,
                output=CoderOutput(
                    patch=placeholder_diff,
                    modified_files=["calc.py"],
                    reasoning_summary="Attempt with placeholder",
                    confidence=0.8,
                ),
            ),
        )

        # Evaluator reports tests passed
        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_internal",
            lambda *a, **kw: EvaluationResult(
                task_id=env["task"].instance_id,
                backend_name="internal",
                outcome=EvaluationOutcome.RESOLVED,
                tier=EvaluationTier.TIER_1_INTERNAL,
                verdict="RESOLVED",
                duration_seconds=0.1,
                details={"all_f2p_passed": True, "all_p2p_passed": True},
            ),
        )

        # Restrict to 1 attempt
        monkeypatch.setattr(ExperimentCondition, "max_attempts", property(lambda self: 1))

        # Low trust initial: Coder = 0.50 (< 0.70)
        cfg = DDIVConfig.load_from_env()
        cfg.init_trust_coder = 0.50
        cfg.coder_trust_critique_threshold = 0.70

        worker = ExperimentWorker(
            task_id=env["task"].instance_id,
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="test_exp_low_reject",
            workspace_root=env["tmp_path"] / "root_low_reject",
            provider="mock",
            config=cfg,
            memory_db_path=env["mem_db"],
        )

        rec = worker.run()

        # Observable outcomes:
        assert rec.resolved is False
        assert rec.attempt_history[0]["trust_critique_required"] is True
        assert rec.attempt_history[0]["trust_critique_passed"] is False
        assert "Unfinished placeholder detected" in rec.attempt_history[0]["trust_critique_reason"]

    def test_04_exact_threshold_boundary(self, test_env, monkeypatch):
        """Exact boundary: 0.70 is high trust (no critique); 0.6999 is low trust (critique required)."""
        env = test_env
        ws_mock = MagicMock()
        ws_mock.path = env["ws_dir"]

        monkeypatch.setattr(ew_module.SWEBenchLoader, "load_from_file", lambda *a, **kw: [env["record"]])
        monkeypatch.setattr(ew_module.WorkspaceManager, "create_workspace", lambda *a, **kw: ws_mock)
        monkeypatch.setattr(ew_module.CommandRunner, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "revert_workspace", lambda *a, **kw: None)
        monkeypatch.setattr(ew_module.PatchManager, "apply_patch", lambda *a, **kw: MagicMock(is_success=True, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "validate_patch", lambda *a, **kw: MagicMock(is_valid=True, error_message=None))
        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_internal",
            lambda *a, **kw: EvaluationResult(
                task_id=env["task"].instance_id,
                backend_name="internal",
                outcome=EvaluationOutcome.RESOLVED,
                tier=EvaluationTier.TIER_1_INTERNAL,
                verdict="RESOLVED",
                duration_seconds=0.1,
                details={"all_f2p_passed": True, "all_p2p_passed": True},
            ),
        )

        # Boundary Case A: Trust = 0.70 exactly -> High Trust (Critique not required)
        cfg_a = DDIVConfig.load_from_env()
        cfg_a.init_trust_coder = 0.70
        cfg_a.coder_trust_critique_threshold = 0.70
        worker_a = ExperimentWorker(
            task_id=env["task"].instance_id,
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="test_boundary_a",
            workspace_root=env["tmp_path"] / "ws_bound_a",
            provider="mock",
            config=cfg_a,
            memory_db_path=env["tmp_path"] / "db_a.db",
        )
        rec_a = worker_a.run()
        assert rec_a.attempt_history[0]["trust_critique_required"] is False

        # Boundary Case B: Trust = 0.6999 -> Low Trust (Critique Required)
        cfg_b = DDIVConfig.load_from_env()
        cfg_b.init_trust_coder = 0.6999
        cfg_b.coder_trust_critique_threshold = 0.70
        worker_b = ExperimentWorker(
            task_id=env["task"].instance_id,
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="test_boundary_b",
            workspace_root=env["tmp_path"] / "ws_bound_b",
            provider="mock",
            config=cfg_b,
            memory_db_path=env["tmp_path"] / "db_b.db",
        )
        rec_b = worker_b.run()
        assert rec_b.attempt_history[0]["trust_critique_required"] is True

    def test_05_failing_test_invariance(self, test_env, monkeypatch):
        """Failing tests (f2p_passed=False) are NEVER accepted regardless of high or low trust."""
        env = test_env
        ws_mock = MagicMock()
        ws_mock.path = env["ws_dir"]

        monkeypatch.setattr(ew_module.SWEBenchLoader, "load_from_file", lambda *a, **kw: [env["record"]])
        monkeypatch.setattr(ew_module.WorkspaceManager, "create_workspace", lambda *a, **kw: ws_mock)
        monkeypatch.setattr(ew_module.CommandRunner, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "revert_workspace", lambda *a, **kw: None)
        monkeypatch.setattr(ew_module.PatchManager, "apply_patch", lambda *a, **kw: MagicMock(is_success=True, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "validate_patch", lambda *a, **kw: MagicMock(is_valid=True, error_message=None))

        # Tests FAIL
        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_internal",
            lambda *a, **kw: EvaluationResult(
                task_id=env["task"].instance_id,
                backend_name="internal",
                outcome=EvaluationOutcome.UNRESOLVED,
                tier=EvaluationTier.TIER_1_INTERNAL,
                verdict="FAIL",
                duration_seconds=0.1,
                details={"all_f2p_passed": False, "failed_f2p_tests": ["test_compute"]},
            ),
        )

        monkeypatch.setattr(ExperimentCondition, "max_attempts", property(lambda self: 1))

        for trust_val in (0.95, 0.40):
            cfg = DDIVConfig.load_from_env()
            cfg.init_trust_coder = trust_val
            worker = ExperimentWorker(
                task_id=env["task"].instance_id,
                condition=ExperimentCondition.FULL_DDIV,
                experiment_id=f"test_invar_{trust_val}",
                workspace_root=env["tmp_path"] / f"ws_invar_{trust_val}",
                provider="mock",
                config=cfg,
                memory_db_path=env["tmp_path"] / f"db_{trust_val}.db",
            )
            rec = worker.run()
            # Invariant: Failing tests are never resolved
            assert rec.resolved is False
            assert rec.attempt_history[0]["f2p_passed"] is False

    def test_06_genuine_recovery_loop_critique_delivery(self, test_env, monkeypatch):
        """Critique rejection feeds failure evidence to next coder prompt and allows recovery on attempt 2."""
        env = test_env
        ws_mock = MagicMock()
        ws_mock.path = env["ws_dir"]

        monkeypatch.setattr(ew_module.SWEBenchLoader, "load_from_file", lambda *a, **kw: [env["record"]])
        monkeypatch.setattr(ew_module.WorkspaceManager, "create_workspace", lambda *a, **kw: ws_mock)
        monkeypatch.setattr(ew_module.CommandRunner, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "revert_workspace", lambda *a, **kw: None)
        monkeypatch.setattr(ew_module.PatchManager, "apply_patch", lambda *a, **kw: MagicMock(is_success=True, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "validate_patch", lambda *a, **kw: MagicMock(is_valid=True, error_message=None))

        # Attempt 1: placeholder diff; Attempt 2: clean fix
        patch_attempt = [0]
        placeholder_diff = (
            "--- a/calc.py\n"
            "+++ b/calc.py\n"
            "@@ -1,3 +1,4 @@\n"
            " def compute(a, b):\n"
            "+    res = a + b  # TODO: stub\n"
            "+    return res\n"
            "-    return a + b\n"
        )
        clean_diff = (
            "--- a/calc.py\n"
            "+++ b/calc.py\n"
            "@@ -1,3 +1,3 @@\n"
            " def compute(a, b):\n"
            "-    return a + b\n"
            "+    return a - b\n"
        )

        captured_coder_inputs = []
        def mock_coder_execute(self_agent, in_data, meta):
            captured_coder_inputs.append(dict(in_data))
            patch_attempt[0] += 1
            if patch_attempt[0] == 1:
                return AgentExecutionResult(
                    task_id=meta.task_id,
                    run_id=meta.run_id,
                    agent_id="Coder",
                    attempt=meta.attempt,
                    success=True,
                    output=CoderOutput(
                        patch=placeholder_diff,
                        modified_files=["calc.py"],
                        reasoning_summary="Attempt 1 stub",
                        confidence=0.8,
                    ),
                )
            # Attempt 2: update file content in workspace as well
            env["src_file"].write_text("def compute(a, b):\n    return a - b\n", encoding="utf-8")
            return AgentExecutionResult(
                task_id=meta.task_id,
                run_id=meta.run_id,
                agent_id="Coder",
                attempt=meta.attempt,
                success=True,
                output=CoderOutput(
                    patch=clean_diff,
                    modified_files=["calc.py"],
                    reasoning_summary="Attempt 2 clean fix",
                    confidence=0.98,
                ),
            )

        monkeypatch.setattr(ew_module.CoderAgent, "execute", mock_coder_execute)

        # Both attempts pass internal tests
        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_internal",
            lambda *a, **kw: EvaluationResult(
                task_id=env["task"].instance_id,
                backend_name="internal",
                outcome=EvaluationOutcome.RESOLVED,
                tier=EvaluationTier.TIER_1_INTERNAL,
                verdict="RESOLVED",
                duration_seconds=0.1,
                details={"all_f2p_passed": True, "all_p2p_passed": True},
            ),
        )

        cfg = DDIVConfig.load_from_env()
        cfg.init_trust_coder = 0.50  # Low trust

        worker = ExperimentWorker(
            task_id=env["task"].instance_id,
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="test_recovery_loop",
            workspace_root=env["tmp_path"] / "ws_recovery",
            provider="mock",
            config=cfg,
            memory_db_path=env["mem_db"],
        )

        rec = worker.run()

        # Observable recovery loop:
        # Attempt 1 rejected by critique; Attempt 2 fixed and resolved
        assert rec.resolved is True
        assert rec.attempts == 2
        assert len(captured_coder_inputs) == 2

        # Attempt 2 input received the low-trust critique directive
        att2_avoid = captured_coder_inputs[1].get("avoid_previous_mistake", "")
        assert "Previous attempt failed low-trust critique" in att2_avoid
        assert "Unfinished placeholder detected" in att2_avoid

    def test_07_controlled_cross_task_lesson_transfer_with_provenance(self, tmp_path: Path):
        """Cross-task memory transfer functions with provenance under isolated test store."""
        test_db = tmp_path / "isolated_memory.db"
        store = MemoryStore(test_db)

        # Seed Task 1 experience
        rec1 = MemoryRecord(
            task_id="pylint-dev__pylint-4970",
            repository="pylint-dev/pylint",
            issue_summary="Disable min-similarity lines check",
            failure_type="F2",
            diagnosis="Check min-similarity before checking similarities",
            recovery_action="A2",
            attempt=1,
            result="RESOLVED",
            relevant_files=["pylint/checkers/similar.py"],
            agent="Coder",
            patch_diff="--- a/similar.py\n+++ b/similar.py\n",
            key_learnings="Check min_similarity_lines is not None",
        )
        rec1_sanitized = sanitize_memory_record(rec1)
        store.insert_record(rec1_sanitized)

        # Retrieve for Task 2 (same repository)
        retriever = MemoryRetriever(store)
        matches = retriever.retrieve_context_for_supervisor(
            task_id="pylint-dev__pylint-6903",
            repository="pylint-dev/pylint",
            current_failure_candidate="F2",
        )

        assert len(matches) == 1
        match = matches[0]
        # Verify provenance
        assert match["source"] == "repo_similar_experience"
        assert match["failure_type"] == "F2"
        assert match["diagnosis"] == "Check min-similarity before checking similarities"

        # Production memory database is completely untouched
        prod_db = Path("data/ddiv_memory.db")
        if prod_db.exists():
            prod_store = MemoryStore(prod_db)
            records = prod_store.get_records_by_task("calc__issue-1")
            assert len(records) == 0
