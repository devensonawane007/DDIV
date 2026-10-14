"""Synthetic unit tests for provider failure propagation and status accounting.

Zero live provider or network calls are made. All models and agents are mocked.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

from agents.base import AgentExecutionResult
from agents.coder import CoderAgent
from agents.patch_critic import PatchCriticAgent
from agents.supervisor import SupervisorAgent, SupervisorDecision
from agents.tester import TesterAgent as _TesterAgent
from agents.test_understanding import TestUnderstandingAgent as _TestUnderstandingAgent
from core.conditions import ExperimentCondition
from core.experiment_orchestrator import ExperimentOrchestrator
from core.experiment_record import (
    ConditionJobStatus,
    ExperimentConditionRecord,
    ExperimentManifest,
)
from core.experiment_worker import ExperimentWorker, _is_quota_exhausted

# Prevent pytest from attempting to discover agents as test classes
_TesterAgent.__test__ = False
_TestUnderstandingAgent.__test__ = False


def _make_mock_result(
    agent_id: str,
    success: bool,
    error: Optional[str] = None,
    error_code: Optional[str] = None,
    output: Any = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    latency_seconds: float = 0.1,
    model_id: str = "mock-model",
    provider: str = "groq",
) -> AgentExecutionResult:
    return AgentExecutionResult(
        task_id="mock-task-1",
        run_id="mock-run-1",
        agent_id=agent_id,
        attempt=1,
        success=success,
        output=output,
        error=error,
        error_code=error_code,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_seconds=latency_seconds,
        model_id=model_id,
        provider=provider,
    )


class TestProviderFailurePropagation(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.workspace_base = self.tmp_path / "workspaces"

    def tearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_quota_exhausted_detection_helper(self):
        """Verify _is_quota_exhausted correctly flags rate limits, 429, TPD, and quota keywords."""
        self.assertTrue(_is_quota_exhausted("429", "Rate limit reached"))
        self.assertTrue(_is_quota_exhausted("RATE_LIMIT_EXCEEDED", "Tokens per day exceeded"))
        self.assertTrue(_is_quota_exhausted(None, "TPD limit 200000 reached"))
        self.assertTrue(_is_quota_exhausted("RESOURCE_EXHAUSTED", "Quota exceeded"))
        self.assertFalse(_is_quota_exhausted("500", "Internal Server Error"))
        self.assertFalse(_is_quota_exhausted("503", "Service Unavailable"))
        self.assertFalse(_is_quota_exhausted("TIMEOUT", "Request timed out after 30s"))
        self.assertFalse(_is_quota_exhausted(None, None))

    def test_coder_429_aborts_quota_exhausted(self):
        """Verify Coder 429 rate limit aborts immediately with ABORTED_QUOTA_EXHAUSTED."""
        ws_root = self.workspace_base / "test_coder_429"
        worker = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="exp_coder_429",
            workspace_root=ws_root,
            provider="mock",
        )

        mock_coder_res = _make_mock_result(
            agent_id="Coder",
            success=False,
            error="Rate limit reached: 429 Tokens Per Day (TPD) exceeded for model",
            error_code="RATE_LIMIT_EXCEEDED",
            prompt_tokens=1500,
            completion_tokens=0,
            total_tokens=1500,
            latency_seconds=0.4,
            model_id="mock-coder",
            provider="groq",
        )

        with patch.object(CoderAgent, "execute", return_value=mock_coder_res):
            record = worker.run()

        self.assertEqual(record.status, ConditionJobStatus.ABORTED_QUOTA_EXHAUSTED)
        self.assertFalse(record.resolved)
        self.assertFalse(record.workflow_completed)
        self.assertFalse(record.patch_generated)
        self.assertFalse(record.patch_applied)
        self.assertEqual(record.failed_stage, "Coder")
        self.assertEqual(record.error_code, "RATE_LIMIT_EXCEEDED")
        self.assertIsNotNone(record.provider_failure)
        self.assertTrue(record.provider_failure.get("quota_exhausted"))
        self.assertEqual(record.worker_exit_code, 3)
        self.assertEqual(record.attempts, 1)  # Aborted on attempt 1 without redundant attempts
        self.assertEqual(len(record.attempt_history), 1)
        self.assertEqual(record.attempt_history[0]["verdict"], "ABORTED_QUOTA_EXHAUSTED")
        self.assertIn("429 Tokens Per Day", record.attempt_history[0]["coder_error_detail"])

    def test_supervisor_429_aborts_quota_exhausted(self):
        """Verify Supervisor 429 rate limit sets ABORTED_QUOTA_EXHAUSTED and breaks cleanly."""
        ws_root = self.workspace_base / "test_sup_429"
        worker = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="exp_sup_429",
            workspace_root=ws_root,
            provider="mock",
        )

        mock_sup_res = _make_mock_result(
            agent_id="Supervisor",
            success=False,
            error="Rate limit reached: 429 TPD limit reached on supervisor model",
            error_code="RATE_LIMIT_EXCEEDED",
            prompt_tokens=2200,
            completion_tokens=0,
            total_tokens=2200,
            latency_seconds=0.5,
            model_id="mock-supervisor",
            provider="groq",
        )

        with patch.object(SupervisorAgent, "execute", return_value=mock_sup_res):
            record = worker.run()

        self.assertEqual(record.status, ConditionJobStatus.ABORTED_QUOTA_EXHAUSTED)
        self.assertFalse(record.resolved)
        self.assertFalse(record.workflow_completed)
        self.assertEqual(record.failed_stage, "Supervisor")
        self.assertEqual(record.error_code, "SUPERVISOR_QUOTA_EXHAUSTED")
        self.assertIsNotNone(record.provider_failure)
        self.assertTrue(record.provider_failure.get("quota_exhausted"))
        self.assertEqual(record.worker_exit_code, 3)
        self.assertEqual(record.attempts, 1)
        self.assertIn("429 TPD limit", record.attempt_history[0].get("supervisor_error", ""))

    def test_supervisor_transient_retry_and_fallback(self):
        """Verify Supervisor transient 503 error performs bounded retry and falls back to clean blind attempt."""
        ws_root = self.workspace_base / "test_sup_transient"
        worker = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="exp_sup_transient",
            workspace_root=ws_root,
            provider="mock",
        )

        mock_503_res = _make_mock_result(
            agent_id="Supervisor",
            success=False,
            error="503 Service Unavailable from backend",
            error_code="SERVICE_UNAVAILABLE",
            prompt_tokens=100,
            completion_tokens=0,
            total_tokens=100,
            latency_seconds=0.2,
            model_id="mock-supervisor",
            provider="groq",
        )

        call_count = 0

        def mock_sup_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # Initial call and 1 retry both fail with 503
                return mock_503_res
            # Subsequent calls (Attempt 2) succeed
            return _make_mock_result(
                agent_id="Supervisor",
                success=True,
                output=SupervisorDecision(
                    detected_failure="F2",
                    recovery_strategy="A2",
                    diagnosis="Recovered on attempt 2",
                    intervention_instructions="Fix logic",
                    avoid_previous_mistake="Avoid recursion",
                    should_retry=False,
                ),
                prompt_tokens=500,
                completion_tokens=100,
                total_tokens=600,
                latency_seconds=0.3,
                model_id="mock-supervisor",
                provider="groq",
            )

        with patch("time.sleep", return_value=None):
            with patch.object(SupervisorAgent, "execute", side_effect=mock_sup_execute):
                record = worker.run()

        # Did not abort prematurely; executed Attempt 2 via fallback
        self.assertGreaterEqual(record.attempts, 2)
        # Attempt 1 recorded the transient error and fallback
        att1 = record.attempt_history[0]
        self.assertIn("503 Service Unavailable", att1.get("supervisor_transient_error", ""))
        self.assertEqual(att1.get("recovery_strategy"), "BLIND_RETRY_FALLBACK")
        self.assertEqual(att1.get("failure_category"), "SUPERVISOR_UNAVAILABLE_TRANSIENT")

    def test_auxiliary_agent_errors_captured(self):
        """Verify TestUnderstanding, Tester, and PatchCritic errors are recorded in attempt history."""
        ws_root = self.workspace_base / "test_aux_errors"
        worker = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="exp_aux_errors",
            workspace_root=ws_root,
            provider="mock",
        )

        rca_err_res = _make_mock_result(
            agent_id="TestUnderstanding",
            success=False,
            error="TestUnderstanding model timeout",
            error_code="TIMEOUT",
            latency_seconds=0.1,
        )
        tester_err_res = _make_mock_result(
            agent_id="Tester",
            success=False,
            error="Tester model bad response",
            error_code="BAD_RESPONSE",
            latency_seconds=0.1,
        )
        critic_err_res = _make_mock_result(
            agent_id="PatchCritic",
            success=False,
            error="PatchCritic model internal error",
            error_code="INTERNAL_ERROR",
            latency_seconds=0.1,
        )

        with patch.object(_TestUnderstandingAgent, "execute", return_value=rca_err_res):
            with patch.object(_TesterAgent, "execute", return_value=tester_err_res):
                with patch.object(PatchCriticAgent, "execute", return_value=critic_err_res):
                    record = worker.run()

        att = record.attempt_history[0]
        self.assertEqual(att.get("test_understanding_error"), "TestUnderstanding model timeout")
        self.assertEqual(att.get("test_understanding_error_code"), "TIMEOUT")
        self.assertEqual(att.get("tester_error"), "Tester model bad response")
        self.assertEqual(att.get("tester_error_code"), "BAD_RESPONSE")

    def test_record_serialization_and_roundtrip(self):
        """Verify ExperimentConditionRecord persists and restores all new error and status fields."""
        rec = ExperimentConditionRecord(
            experiment_id="exp_test_fields",
            task_id="mock-task-1",
            condition=ExperimentCondition.FULL_DDIV,
            status=ConditionJobStatus.ABORTED_QUOTA_EXHAUSTED,
            resolved=False,
            workflow_completed=False,
            patch_generated=False,
            patch_applied=False,
            failed_stage="Coder",
            error_code="RATE_LIMIT_EXCEEDED",
            provider_failure={
                "stage": "Coder",
                "error_code": "RATE_LIMIT_EXCEEDED",
                "error_message": "Rate limit exceeded (TPD)",
                "attempt": 1,
                "quota_exhausted": True,
            },
            worker_exit_code=3,
            attempts=1,
            attempt_history=[{"attempt": 1, "verdict": "ABORTED_QUOTA_EXHAUSTED"}],
            candidate_patch="",
            execution_duration_seconds=5.43,
            workspace_path=str(self.tmp_path),
            error_message="Rate limit exceeded (TPD)",
        )

        target_file = self.tmp_path / "quota_record.json"
        rec.save_to_file(target_file)
        self.assertTrue(target_file.exists())

        loaded = ExperimentConditionRecord.load_from_file(target_file)
        self.assertEqual(loaded.status, ConditionJobStatus.ABORTED_QUOTA_EXHAUSTED)
        self.assertFalse(loaded.workflow_completed)
        self.assertFalse(loaded.patch_generated)
        self.assertFalse(loaded.patch_applied)
        self.assertEqual(loaded.failed_stage, "Coder")
        self.assertEqual(loaded.error_code, "RATE_LIMIT_EXCEEDED")
        self.assertIsNotNone(loaded.provider_failure)
        self.assertTrue(loaded.provider_failure.get("quota_exhausted"))
        self.assertEqual(loaded.worker_exit_code, 3)

    def test_orchestrator_manifest_status_propagation(self):
        """Verify ExperimentManifest tracks ABORTED_QUOTA_EXHAUSTED and PROVIDER_ERROR without marking completed."""
        manifest = ExperimentManifest(
            experiment_id="exp_manifest_test",
            tasks=["task_1", "task_2", "task_3"],
            conditions=["baseline", "retry_only", "full_ddiv"],
        )

        # Job 1: Completed
        manifest.update_job_status(
            "task_1",
            ExperimentCondition.BASELINE,
            ConditionJobStatus.COMPLETED,
            resolved=True,
        )
        # Job 2: Quota Exhausted
        manifest.update_job_status(
            "task_2",
            ExperimentCondition.FULL_DDIV,
            ConditionJobStatus.ABORTED_QUOTA_EXHAUSTED,
            error="Rate limit 429",
        )
        # Job 3: Provider Error
        manifest.update_job_status(
            "task_3",
            ExperimentCondition.RETRY_ONLY,
            ConditionJobStatus.PROVIDER_ERROR,
            error="503 Service Unavailable",
        )

        self.assertTrue(manifest.is_job_completed("task_1", ExperimentCondition.BASELINE))
        self.assertFalse(manifest.is_job_completed("task_2", ExperimentCondition.FULL_DDIV))
        self.assertFalse(manifest.is_job_completed("task_3", ExperimentCondition.RETRY_ONLY))

        self.assertEqual(
            manifest.jobs[manifest.job_key("task_2", ExperimentCondition.FULL_DDIV)]["status"],
            "ABORTED_QUOTA_EXHAUSTED",
        )
        self.assertEqual(
            manifest.jobs[manifest.job_key("task_3", ExperimentCondition.RETRY_ONLY)]["status"],
            "PROVIDER_ERROR",
        )

    def test_worker_exit_codes(self):
        """Verify mapping from terminal status to exit code protocol."""
        ws_root = self.workspace_base / "test_exit_codes"

        # Test PROVIDER_ERROR produces exit code 2
        worker_provider_err = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.BASELINE,
            experiment_id="exp_exit_code",
            workspace_root=ws_root,
            provider="mock",
        )
        mock_500_res = _make_mock_result(
            agent_id="Coder",
            success=False,
            error="500 Internal Server Error",
            error_code="INTERNAL_SERVER_ERROR",
            latency_seconds=0.1,
            model_id="mock-coder",
            provider="groq",
        )
        with patch.object(CoderAgent, "execute", return_value=mock_500_res):
            rec_prov = worker_provider_err.run()

        self.assertEqual(rec_prov.status, ConditionJobStatus.PROVIDER_ERROR)
        self.assertEqual(rec_prov.worker_exit_code, 2)

    def test_supervisor_unrecoverable_provider_error_produces_provider_error(self):
        """Verify Supervisor unrecoverable 401/403/404 produces PROVIDER_ERROR and breaks without retry."""
        ws_root = self.workspace_base / "test_sup_unrecoverable"
        worker = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="exp_sup_unrecoverable",
            workspace_root=ws_root,
            provider="mock",
        )
        mock_401_res = _make_mock_result(
            agent_id="Supervisor",
            success=False,
            error="401 Unauthorized: Invalid API Key",
            error_code="INVALID_API_KEY",
            latency_seconds=0.1,
            model_id="mock-supervisor",
            provider="groq",
        )
        with patch.object(SupervisorAgent, "execute", return_value=mock_401_res):
            rec = worker.run()

        self.assertEqual(rec.status, ConditionJobStatus.PROVIDER_ERROR)
        self.assertEqual(rec.worker_exit_code, 2)
        self.assertEqual(rec.failed_stage, "Supervisor")
        self.assertFalse(rec.workflow_completed)
        self.assertEqual(rec.attempts, 1)

    def test_supervisor_transient_fallback_marks_degraded_execution(self):
        """Verify fallback on supervisor transient failure explicitly records degraded_execution."""
        ws_root = self.workspace_base / "test_sup_degraded"
        worker = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="exp_sup_degraded",
            workspace_root=ws_root,
            provider="mock",
        )
        mock_503_res = _make_mock_result(
            agent_id="Supervisor",
            success=False,
            error="503 Service Unavailable",
            error_code="SERVICE_UNAVAILABLE",
            latency_seconds=0.1,
        )
        call_count = 0

        def mock_sup(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return mock_503_res
            return _make_mock_result(
                agent_id="Supervisor",
                success=True,
                output=SupervisorDecision(
                    detected_failure="F2",
                    recovery_strategy="A2",
                    diagnosis="Diagnosed",
                    intervention_instructions="Fix logic",
                    avoid_previous_mistake="None",
                    should_retry=False,
                ),
            )

        with patch("time.sleep", return_value=None):
            with patch.object(SupervisorAgent, "execute", side_effect=mock_sup):
                rec = worker.run()

        self.assertTrue(rec.degraded_execution)
        self.assertIn("Supervisor transient failure", rec.degraded_reason or "")
        # Attempt 1 failed supervisor and marked degraded
        self.assertTrue(rec.attempt_history[0].get("degraded_execution"))
        # Attempt 2 ran under degraded guidance and marked degraded
        self.assertTrue(rec.attempt_history[1].get("degraded_execution"))


if __name__ == "__main__":
    unittest.main()
