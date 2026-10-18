"""Deterministic integration test suite for DDIV Phase 6 Episodic Memory.

Verifies:
1. Stage A: Prompt Injection into Locator, Coder, and Supervisor LLM requests via Mock Provider.
2. Stage B: Cross-task persistent SQLite storage and evidence-based retrieval across synthetic tasks.
3. Stage C: Strict condition isolation (BASELINE and RETRY_ONLY receive zero memory).
4. Stage D: Empty memory retrieval and error resilience (corrupt/locked DB fallback).
5. Stage E: Contamination prevention (sanitizing benchmark reference tokens).
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from agents.base import AgentExecutionResult, AgentInputMetadata
from agents.coder import CoderAgent
from agents.locator import LocatorAgent
from agents.supervisor import SupervisorAgent, SupervisorDecision
from core.conditions import ExperimentCondition
from core.config import DDIVConfig, ExecutionMode
from core.experiment_record import ConditionJobStatus
from core.experiment_worker import (
    ExperimentWorker,
    sanitize_memory_record,
    sanitize_text,
    FORBIDDEN_REFERENCE_TOKENS,
)
from evaluation.backends import EvaluationOutcome, EvaluationResult, EvaluationTier
from evaluation.swebench_loader import SWEBenchGroundTruth, SWEBenchRecord, SWEBenchTask
from memory.memory_store import MemoryStore
from memory.retrieval import MemoryRetriever
from memory.schemas import MemoryRecord
from models.base import ModelConfig
from models.providers import MockModelProvider


class RecordingMockProvider(MockModelProvider):
    """Mock provider that records all generated prompts and arguments."""

    def __init__(self, config: ModelConfig, return_output: Any = None):
        super().__init__(config)
        self.recorded_calls: List[Dict[str, Any]] = []
        self.return_output = return_output

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        response_schema: Optional[Any] = None,
    ) -> Any:
        self.recorded_calls.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "response_schema": response_schema,
        })
        if self.return_output is not None:
            import json
            from models.base import ProviderResponse
            raw_text = json.dumps(self.return_output) if isinstance(self.return_output, dict) else str(self.return_output)
            return ProviderResponse(
                raw_text=raw_text,
                parsed_json=self.return_output if isinstance(self.return_output, dict) else {},
                model_id=self.config.model_id,
                latency_seconds=0.01,
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            )
        return super().generate(prompt=prompt, system_prompt=system_prompt, response_schema=response_schema)


class TestEpisodicMemoryIntegration:
    """End-to-end deterministic verification of episodic memory integration."""

    @pytest.fixture
    def temp_memory_db(self, tmp_path: Path) -> Path:
        """Provide a clean temporary SQLite database for episodic memory."""
        db_path = tmp_path / "test_episodic_memory.db"
        return db_path

    # =========================================================================
    # Stage A: Prompt Injection Verification
    # =========================================================================

    def test_01_stage_a_prompt_injection_coder_hook(self):
        """Verify CoderAgent.build_prompt wraps episodic memory with advisory block."""
        provider = RecordingMockProvider(ModelConfig(name="Coder", model_id="mock-coder", provider="mock"))
        coder = CoderAgent(provider)

        # 1. When memory_context is provided
        input_with_memory = {
            "issue": "Fix off-by-one error in parser",
            "memory_context": "[1] (repo_similar) Failure: F2 | Action: A2 | Context: Guard against empty tokens",
        }
        meta = AgentInputMetadata(run_id="run-001", task_id="test__pkg-001", attempt=1)
        prompt = coder.build_prompt(input_with_memory, meta)

        assert "=== HISTORICAL EPISODIC MEMORY (ADVISORY CONTEXT) ===" in prompt
        assert "DO NOT assume their filenames, symbols, or specific logic apply verbatim" in prompt
        assert "[1] (repo_similar) Failure: F2 | Action: A2 | Context: Guard against empty tokens" in prompt
        assert "Synthesize the smallest correct code modification resolving the issue." in prompt

        # 2. When memory_context is empty
        input_without_memory = {
            "issue": "Fix off-by-one error in parser",
            "memory_context": "",
        }
        prompt_empty = coder.build_prompt(input_without_memory, meta)
        assert "=== HISTORICAL EPISODIC MEMORY (ADVISORY CONTEXT) ===" not in prompt_empty

    def test_02_stage_a_prompt_injection_locator_and_supervisor(self):
        """Verify LocatorAgent and SupervisorAgent receive memory in prompts."""
        loc_prov = RecordingMockProvider(ModelConfig(name="Locator", model_id="mock-loc", provider="mock"))
        locator = LocatorAgent(loc_prov)

        sup_prov = RecordingMockProvider(ModelConfig(name="Supervisor", model_id="mock-sup", provider="mock"))
        supervisor = SupervisorAgent(sup_prov)

        meta = AgentInputMetadata(run_id="run-001", task_id="test__pkg-001", attempt=1)

        # Locator with memory
        loc_input = {
            "issue": "Attribute error in parser",
            "memory_context": "[1] Relevant file: src/parser/core.py",
        }
        loc_prompt = locator.build_prompt(loc_input, meta)
        assert "=== HISTORICAL MEMORY (PRIOR SIMILAR ISSUES) ===" in loc_prompt
        assert "[1] Relevant file: src/parser/core.py" in loc_prompt

        # Supervisor with memory
        sup_input = {
            "task_id": "test__pkg-001",
            "memory_matches": [
                {
                    "source": "repo_similar_experience",
                    "failure_type": "F2",
                    "recovery_action": "A2",
                    "diagnosis": "Check boundary condition",
                }
            ],
        }
        sup_prompt = supervisor.build_prompt(sup_input, meta)
        assert "=== RELEVANT MEMORY MATCHES ===" in sup_prompt
        assert "Check boundary condition" in sup_prompt

    def test_03_stage_a_prompt_reaches_provider_generate(self):
        """Verify that agent.execute() sends memory context to provider.generate()."""
        provider = RecordingMockProvider(
            ModelConfig(name="Coder", model_id="mock-coder", provider="mock"),
            return_output=MagicMock(modifications=[], patch="", modified_files=[]),
        )
        coder = CoderAgent(provider)

        input_data = {
            "issue": "UnboundLocalError",
            "memory_context": "PRIOR_EXPERIENCE_TOKEN_999",
        }
        meta = AgentInputMetadata(run_id="run-002", task_id="test__pkg-002", attempt=1)
        coder.execute(input_data, meta)

        assert len(provider.recorded_calls) == 1
        recorded = provider.recorded_calls[0]
        assert "PRIOR_EXPERIENCE_TOKEN_999" in recorded["prompt"]
        assert "=== HISTORICAL EPISODIC MEMORY (ADVISORY CONTEXT) ===" in recorded["prompt"]

    # =========================================================================
    # Stage B: Cross-Task Persistent Storage & Retrieval
    # =========================================================================

    def test_04_stage_b_cross_task_persistence_and_retrieval(self, temp_memory_db: Path):
        """Store experience in Task A, close store, retrieve in Task B from same DB."""
        # 1. Task A writes a record
        store_a = MemoryStore(temp_memory_db)
        record_task_a = MemoryRecord(
            task_id="repo1__pkg-1001",
            repository="test_org/test_repo",
            issue_summary="TypeError in json serializer",
            failure_type="F2",
            failure_evidence=["TypeError: Object of type Decimal is not JSON serializable"],
            failed_tests=["tests/test_serializer.py::test_decimal"],
            subsystem="serializer",
            diagnosis="Convert Decimal to float or str before serialization",
            recovery_action="A2",
            attempt=1,
            result="FAILED",
            relevant_files=["serializer/core.py"],
            agent="Supervisor",
        )
        store_a.insert_record(sanitize_memory_record(record_task_a))

        # 2. Simulate fresh connection / new process for Task B
        store_b = MemoryStore(temp_memory_db)
        retriever_b = MemoryRetriever(store_b)

        # Query for Task B in the same repo with same failure type
        matches = retriever_b.retrieve_context_for_supervisor(
            task_id="repo1__pkg-1002",
            repository="test_org/test_repo",
            current_failure_candidate="F2",
            failed_tests=["tests/test_serializer.py::test_custom_type"],
            subsystem="serializer",
        )

        assert len(matches) > 0
        match = matches[0]
        assert match["task_id"] == "repo1__pkg-1001"
        assert match["failure_type"] == "F2"
        assert match["subsystem"] == "serializer"
        assert "Convert Decimal to float" in match["diagnosis"]

        formatted = retriever_b.format_matches_for_prompt(matches)
        assert "(repo_similar_experience)" in formatted
        assert "Failure: F2" in formatted
        assert "Action: A2" in formatted

    def test_05_stage_b_relevance_sorting_priority(self, temp_memory_db: Path):
        """Verify relevance prioritization: exact repo+failure > cross-repo > general."""
        store = MemoryStore(temp_memory_db)

        # Record 1: Different repo, different failure
        store.insert_record(
            sanitize_memory_record(
                MemoryRecord(
                    task_id="other__pkg-001",
                    repository="other_org/other_repo",
                    issue_summary="CSS parsing error",
                    failure_type="F1",
                    diagnosis="Wrong path",
                    recovery_action="A1",
                    attempt=1,
                    result="FAILED",
                    agent="Supervisor",
                )
            )
        )

        # Record 2: Same repo, matching failure F2
        store.insert_record(
            sanitize_memory_record(
                MemoryRecord(
                    task_id="target_org__pkg-001",
                    repository="target_org/target_repo",
                    issue_summary="Parser syntax crash",
                    failure_type="F2",
                    subsystem="parser",
                    diagnosis="Check AST tokens",
                    recovery_action="A2",
                    attempt=1,
                    result="FAILED",
                    agent="Supervisor",
                )
            )
        )

        retriever = MemoryRetriever(store)
        matches = retriever.retrieve_context_for_supervisor(
            task_id="target_org__pkg-002",
            repository="target_org/target_repo",
            current_failure_candidate="F2",
            subsystem="parser",
        )

        assert len(matches) >= 1
        # The first match should be the repo-similar experience
        assert matches[0]["source"] == "repo_similar_experience"
        assert matches[0]["task_id"] == "target_org__pkg-001"

    # =========================================================================
    # Stage C: Condition Isolation
    # =========================================================================

    def test_06_stage_c_condition_isolation_baseline_receives_no_memory(self, tmp_path: Path):
        """Verify BASELINE condition never retrieves or injects episodic memory."""
        worker = ExperimentWorker(
            task_id="pallets__flask-5014",
            condition=ExperimentCondition.BASELINE,
            experiment_id="exp-baseline-iso",
            workspace_root=tmp_path / "ws_baseline",
            provider="mock",
        )
        assert worker.condition.is_memory_enabled is False

    def test_07_stage_c_condition_isolation_retry_only_receives_no_memory(self, tmp_path: Path):
        """Verify RETRY_ONLY condition never retrieves or injects episodic memory."""
        worker = ExperimentWorker(
            task_id="pallets__flask-5014",
            condition=ExperimentCondition.RETRY_ONLY,
            experiment_id="exp-retry-iso",
            workspace_root=tmp_path / "ws_retry",
            provider="mock",
        )
        assert worker.condition.is_memory_enabled is False

    def test_08_stage_c_full_ddiv_has_memory_enabled(self, tmp_path: Path):
        """Verify FULL_DDIV enables episodic memory."""
        worker = ExperimentWorker(
            task_id="pallets__flask-5014",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="exp-full-iso",
            workspace_root=tmp_path / "ws_full",
            provider="mock",
        )
        assert worker.condition.is_memory_enabled is True

    # =========================================================================
    # Stage D: Empty Retrieval & Error Resilience
    # =========================================================================

    def test_09_stage_d_empty_memory_db_graceful_handling(self, temp_memory_db: Path):
        """Empty memory DB produces empty matches and prompts without errors."""
        store = MemoryStore(temp_memory_db)
        retriever = MemoryRetriever(store)

        matches = retriever.retrieve_context_for_supervisor(
            task_id="empty_task_001",
            repository="any/repo",
            current_failure_candidate="F1",
        )
        assert matches == []
        formatted = retriever.format_matches_for_prompt(matches)
        assert formatted == ""

    def test_10_stage_d_locked_or_inaccessible_db_resilience(self, tmp_path: Path):
        """Worker handles inaccessible or invalid memory DB gracefully without crashing."""
        invalid_db_path = tmp_path / "nonexistent_dir_12345" / "sub" / "memory.db"

        # Should not raise exception during worker initialization or execution
        worker = ExperimentWorker(
            task_id="pallets__flask-5014",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="exp-resilience",
            workspace_root=tmp_path / "ws_resilience",
            provider="mock",
            memory_db_path=invalid_db_path,
        )
        assert worker.memory_db_path == invalid_db_path.resolve()

    # =========================================================================
    # Stage E: Reference Contamination Sanitization
    # =========================================================================

    def test_11_stage_e_sanitizer_redacts_forbidden_tokens(self):
        """Verify benchmark reference tokens are redacted from memory records."""
        rec = MemoryRecord(
            task_id="test__leak-001",
            repository="test/repo",
            issue_summary="Found in gold_patch and test_patch",
            failure_type="F2",
            failure_evidence=["FAIL_TO_PASS test failed", "pass_to_pass check"],
            failed_tests=["FAIL_TO_PASS_test1"],
            previous_patch="--- gold_patch diff",
            diagnosis="Comparing with gold_patch solution",
            attempt=1,
            result="FAILED",
            metadata={
                "gold_patch": "secret_diff",
                "safe_note": "Look at pass_to_pass",
            },
        )
        clean = sanitize_memory_record(rec)

        assert "gold_patch" not in clean.issue_summary
        assert "[REDACTED_REF]" in clean.issue_summary

        assert "FAIL_TO_PASS" not in clean.failure_evidence[0]
        assert "[REDACTED_REF]" in clean.failure_evidence[0]

        assert "FAIL_TO_PASS" not in clean.failed_tests[0]
        assert "[REDACTED_REF]" in clean.failed_tests[0]

        assert "gold_patch" not in clean.previous_patch
        assert "[REDACTED_REF]" in clean.previous_patch

        assert "gold_patch" not in clean.diagnosis
        assert "[REDACTED_REF]" in clean.diagnosis

        # Forbidden key in metadata must be completely dropped
        assert "gold_patch" not in clean.metadata
        # Safe key with forbidden value must have value redacted
        assert clean.metadata["safe_note"] == "Look at [REDACTED_REF]"

    def test_12_stage_e_sanitize_text_edge_cases(self):
        """Verify sanitize_text handles None, empty strings, and multiple tokens."""
        assert sanitize_text("") == ""
        assert sanitize_text(None) == ""
        mixed = "Check gold_patch with FAIL_TO_PASS and test_patch"
        clean = sanitize_text(mixed)
        for tok in FORBIDDEN_REFERENCE_TOKENS:
            assert tok not in clean
        assert clean.count("[REDACTED_REF]") == 3

    # =========================================================================
    # End-to-End Worker Lifecycle Tests
    # =========================================================================

    def test_13_end_to_end_worker_stage_b_stores_and_recalls_memory_across_tasks(self, temp_memory_db: Path, monkeypatch):
        """Simulate Task A recording a memory into persistent SQLite and Task B recalling it."""
        store = MemoryStore(temp_memory_db)
        # Pre-seed Task A failure experience in SQLite
        rec_a = MemoryRecord(
            task_id="pallets__flask-5000",
            repository="pallets/flask",
            issue_summary="Blueprint name empty validation failure",
            failure_type="F2",
            failure_evidence=["ValueError not raised"],
            subsystem="src/flask",
            diagnosis="Validate blueprint name is non-empty string",
            recovery_action="A2",
            attempt=1,
            result="FAILED",
            relevant_files=["src/flask/blueprints.py"],
            agent="Supervisor",
        )
        store.insert_record(sanitize_memory_record(rec_a))

        # Setup Task B worker with temp_memory_db
        worker = ExperimentWorker(
            task_id="pallets__flask-5014",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="exp-e2e-recall",
            workspace_root=temp_memory_db.parent / "ws_recall",
            provider="mock",
            memory_db_path=temp_memory_db,
        )

        captured_coder_prompts = []

        import core.experiment_worker as ew_module
        orig_coder_execute = ew_module.CoderAgent.execute

        def spy_coder_execute(self_coder, input_data, meta):
            prompt = self_coder.build_prompt(input_data, meta)
            captured_coder_prompts.append(prompt)
            return orig_coder_execute(self_coder, input_data, meta)

        monkeypatch.setattr(ew_module.CoderAgent, "execute", spy_coder_execute)

        mock_task = SWEBenchTask(
            instance_id="pallets__flask-5014",
            repo="pallets/flask",
            base_commit="abc123",
            problem_statement="Empty blueprint name causes silent failure",
        )
        mock_record = SWEBenchRecord(task=mock_task, ground_truth=SWEBenchGroundTruth())
        monkeypatch.setattr(ew_module.SWEBenchLoader, "get_mock_record", lambda *args, **kwargs: mock_record)
        monkeypatch.setattr(ew_module.SWEBenchLoader, "load_from_file", lambda *args, **kwargs: [mock_record])

        ws_mock = MagicMock()
        ws_mock.path = temp_memory_db.parent / "mock_repo"
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
                task_id="pallets__flask-5014",
                backend_name="internal",
                outcome=EvaluationOutcome.UNRESOLVED,
                tier=EvaluationTier.TIER_1_INTERNAL,
                verdict="FAIL",
                duration_seconds=0.1,
                details={"failed_f2p_tests": ["test_empty_name"]},
            ),
        )
        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_official",
            lambda *args, **kwargs: EvaluationResult(
                task_id="pallets__flask-5014",
                backend_name="official",
                outcome=EvaluationOutcome.UNRESOLVED,
                tier=EvaluationTier.TIER_2_OFFICIAL,
                verdict="FAIL",
                duration_seconds=0.1,
            ),
        )

        worker.config.max_recovery_attempts = 1
        res = worker.run()

        # Verify that Coder prompt captured historical episodic memory from Task A
        assert len(captured_coder_prompts) >= 1
        coder_prompt = captured_coder_prompts[0]
        assert "=== HISTORICAL EPISODIC MEMORY (ADVISORY CONTEXT) ===" in coder_prompt
        assert "Validate blueprint name is non-empty string" in coder_prompt

        # Verify attempt log recorded memory retrieval
        assert len(res.attempt_history) >= 1
        assert res.attempt_history[0]["memory_retrieved"] is True

    def test_14_end_to_end_worker_condition_isolation(self, temp_memory_db: Path, monkeypatch):
        """Verify BASELINE and RETRY_ONLY under ExperimentWorker.run() ignore memory DB completely."""
        store = MemoryStore(temp_memory_db)
        rec = MemoryRecord(
            task_id="pallets__flask-5000",
            repository="pallets/flask",
            issue_summary="Memory seed",
            failure_type="F2",
            diagnosis="Should never be seen in baseline",
            recovery_action="A2",
            attempt=1,
            result="FAILED",
            agent="Supervisor",
        )
        store.insert_record(sanitize_memory_record(rec))

        import core.experiment_worker as ew_module

        orig_coder_execute = ew_module.CoderAgent.execute
        captured_coder_prompts = []

        def spy_coder_execute(self_coder, input_data, meta):
            prompt = self_coder.build_prompt(input_data, meta)
            captured_coder_prompts.append(prompt)
            return orig_coder_execute(self_coder, input_data, meta)

        monkeypatch.setattr(ew_module.CoderAgent, "execute", spy_coder_execute)

        mock_task = SWEBenchTask(
            instance_id="pallets__flask-5014",
            repo="pallets/flask",
            base_commit="abc123",
            problem_statement="Empty blueprint name causes silent failure",
        )
        mock_record = SWEBenchRecord(task=mock_task, ground_truth=SWEBenchGroundTruth())
        monkeypatch.setattr(ew_module.SWEBenchLoader, "get_mock_record", lambda *args, **kwargs: mock_record)
        monkeypatch.setattr(ew_module.SWEBenchLoader, "load_from_file", lambda *args, **kwargs: [mock_record])

        monkeypatch.setattr(ew_module.CommandRunner, "run", lambda *args, **kwargs: MagicMock(returncode=0, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "revert_workspace", lambda *args, **kwargs: None)
        monkeypatch.setattr(ew_module.PatchManager, "apply_patch", lambda *args, **kwargs: MagicMock(is_success=True, stdout="", stderr=""))
        monkeypatch.setattr(ew_module.PatchManager, "validate_patch", lambda *args, **kwargs: MagicMock(is_valid=True, error_message=None))

        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_internal",
            lambda *args, **kwargs: EvaluationResult(
                task_id="pallets__flask-5014",
                backend_name="internal",
                outcome=EvaluationOutcome.UNRESOLVED,
                tier=EvaluationTier.TIER_1_INTERNAL,
                verdict="FAIL",
                duration_seconds=0.1,
                details={},
            ),
        )
        monkeypatch.setattr(
            ew_module.TwoTierEvaluator,
            "evaluate_official",
            lambda *args, **kwargs: EvaluationResult(
                task_id="pallets__flask-5014",
                backend_name="official",
                outcome=EvaluationOutcome.UNRESOLVED,
                tier=EvaluationTier.TIER_2_OFFICIAL,
                verdict="FAIL",
                duration_seconds=0.1,
            ),
        )

        for cond in [ExperimentCondition.BASELINE, ExperimentCondition.RETRY_ONLY]:
            captured_coder_prompts.clear()
            worker = ExperimentWorker(
                task_id="pallets__flask-5014",
                condition=cond,
                experiment_id=f"exp-iso-{cond.value}",
                workspace_root=temp_memory_db.parent / f"ws_iso_{cond.value}",
                provider="mock",
                memory_db_path=temp_memory_db,
            )

            ws_mock = MagicMock()
            ws_mock.path = temp_memory_db.parent / f"mock_repo_{cond.value}"
            ws_mock.path.mkdir(parents=True, exist_ok=True)
            monkeypatch.setattr(ew_module.WorkspaceManager, "create_workspace", lambda *args, **kwargs: ws_mock)
            worker.config.max_recovery_attempts = 1
            res = worker.run()

            assert len(captured_coder_prompts) >= 1
            coder_prompt = captured_coder_prompts[0]
            assert "=== HISTORICAL EPISODIC MEMORY (ADVISORY CONTEXT) ===" not in coder_prompt
            assert "Should never be seen in baseline" not in coder_prompt
            assert res.attempt_history[0]["memory_retrieved"] is False
