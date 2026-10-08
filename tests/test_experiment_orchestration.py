"""Unit and integration tests for DDIV experiment orchestration, child workers, and resumability."""

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.conditions import ExperimentCondition
from core.config import ExecutionMode
from core.experiment_orchestrator import ExperimentOrchestrator
from core.experiment_record import (
    ConditionJobStatus,
    ExperimentConditionRecord,
    ExperimentManifest,
)
from core.experiment_worker import ExperimentWorker


class TestExperimentOrchestration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.base_dir = self.tmp_path / "experiments"
        self.workspace_base = self.tmp_path / "workspaces"
        self.logs_base = self.tmp_path / "logs"

    def tearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_condition_definitions(self):
        """Verify ExperimentCondition mappings, attempt bounds, and ablation toggles."""
        b = ExperimentCondition.BASELINE
        r = ExperimentCondition.RETRY_ONLY
        f = ExperimentCondition.FULL_DDIV

        self.assertEqual(b.value, "baseline")
        self.assertEqual(r.value, "retry_only")
        self.assertEqual(f.value, "full_ddiv")

        self.assertEqual(b.max_attempts, 1)
        self.assertEqual(r.max_attempts, 3)
        self.assertEqual(f.max_attempts, 3)

        self.assertFalse(b.is_supervisor_enabled)
        self.assertFalse(r.is_supervisor_enabled)
        self.assertTrue(f.is_supervisor_enabled)

        self.assertFalse(b.is_diagnosis_enabled)
        self.assertFalse(r.is_diagnosis_enabled)
        self.assertTrue(f.is_diagnosis_enabled)

        self.assertFalse(b.is_intervention_enabled)
        self.assertFalse(r.is_intervention_enabled)
        self.assertTrue(f.is_intervention_enabled)

        self.assertFalse(b.is_memory_enabled)
        self.assertFalse(r.is_memory_enabled)
        self.assertTrue(f.is_memory_enabled)

        self.assertFalse(b.is_trust_enabled)
        self.assertFalse(r.is_trust_enabled)
        self.assertTrue(f.is_trust_enabled)

        self.assertEqual(b.to_execution_mode(), ExecutionMode.BASELINE)
        self.assertEqual(r.to_execution_mode(), ExecutionMode.RECOVERY_ONLY)
        self.assertEqual(f.to_execution_mode(), ExecutionMode.FULL_DDIV)

        self.assertEqual(ExperimentCondition.from_str("Baseline"), b)
        self.assertEqual(ExperimentCondition.from_str("retry-only"), r)
        self.assertEqual(ExperimentCondition.from_str("FULL_DDIV"), f)

    def test_record_and_manifest_serialization(self):
        """Verify atomic file persistence and round-trip parsing of records and manifests."""
        rec = ExperimentConditionRecord(
            experiment_id="exp_test_01",
            task_id="mock-task-1",
            condition=ExperimentCondition.BASELINE,
            status=ConditionJobStatus.COMPLETED,
            resolved=True,
            attempts=1,
            candidate_patch="diff --git a/foo b/foo...",
            execution_duration_seconds=1.23,
            workspace_path=str(self.tmp_path),
        )

        target_file = self.tmp_path / "record.json"
        rec.save_to_file(target_file)
        self.assertTrue(target_file.exists())

        loaded = ExperimentConditionRecord.load_from_file(target_file)
        self.assertEqual(loaded.task_id, "mock-task-1")
        self.assertEqual(loaded.condition, ExperimentCondition.BASELINE)
        self.assertTrue(loaded.resolved)
        self.assertEqual(loaded.attempts, 1)

        # Manifest
        manifest = ExperimentManifest(
            experiment_id="exp_test_01",
            tasks=["mock-task-1"],
            conditions=["baseline", "retry_only"],
        )
        manifest.update_job_status(
            "mock-task-1",
            ExperimentCondition.BASELINE,
            ConditionJobStatus.COMPLETED,
            result_file=str(target_file),
            resolved=True,
        )

        m_file = self.tmp_path / "manifest.json"
        manifest.save_to_file(m_file)
        self.assertTrue(m_file.exists())

        loaded_m = ExperimentManifest.load_from_file(m_file)
        self.assertTrue(loaded_m.is_job_completed("mock-task-1", ExperimentCondition.BASELINE))
        self.assertFalse(loaded_m.is_job_completed("mock-task-1", ExperimentCondition.RETRY_ONLY))

    def test_worker_execution_mock(self):
        """Test ExperimentWorker end-to-end in mock mode produces independent result record."""
        ws_root = self.workspace_base / "mock_test_ws"
        worker = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.BASELINE,
            experiment_id="exp_worker_test",
            workspace_root=ws_root,
            provider="mock",
        )

        record = worker.run()

        self.assertEqual(record.task_id, "mock-task-1")
        self.assertEqual(record.condition, ExperimentCondition.BASELINE)
        self.assertEqual(record.status, ConditionJobStatus.COMPLETED)
        self.assertEqual(record.attempts, 1)
        # Baseline stops on attempt 1 without retry
        self.assertFalse(record.resolved)
        self.assertIn("internal_evaluation", record.model_dump())
        self.assertIn("official_evaluation", record.model_dump())

        # Verify workspaces were created
        self.assertTrue((ws_root / "agent_ws").exists())
        self.assertTrue((ws_root / "eval_ws").exists())

        # Test FULL_DDIV recovers and resolves on attempt 2
        ws_ddiv = self.workspace_base / "mock_test_ddiv"
        worker_ddiv = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="exp_worker_test",
            workspace_root=ws_ddiv,
            provider="mock",
        )
        rec_ddiv = worker_ddiv.run()
        self.assertEqual(rec_ddiv.condition, ExperimentCondition.FULL_DDIV)
        self.assertEqual(rec_ddiv.status, ConditionJobStatus.COMPLETED)
        self.assertTrue(rec_ddiv.resolved)
        self.assertEqual(rec_ddiv.attempts, 2)

        # Test RETRY_ONLY executes blind retries without supervisor or interventions
        ws_retry = self.workspace_base / "mock_test_retry"
        worker_retry = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.RETRY_ONLY,
            experiment_id="exp_worker_test",
            workspace_root=ws_retry,
            provider="mock",
        )
        rec_retry = worker_retry.run()
        self.assertEqual(rec_retry.condition, ExperimentCondition.RETRY_ONLY)
        self.assertEqual(rec_retry.status, ConditionJobStatus.COMPLETED)
        self.assertFalse(rec_retry.resolved)
        self.assertEqual(rec_retry.attempts, 3)
        self.assertEqual(len(rec_retry.attempt_history), 3)
        for snap in rec_retry.attempt_history:
            self.assertEqual(snap.get("failure_category"), "UNRESOLVED_RETRY")
            self.assertEqual(snap.get("recovery_strategy"), "BLIND_RETRY")
            self.assertEqual(snap.get("supervisor_instructions"), "")

    def test_workspace_isolation_across_conditions(self):
        """Verify separate conditions operate in disjoint workspace folders."""
        ws_baseline = self.workspace_base / "exp_iso" / "task1__baseline"
        ws_ddiv = self.workspace_base / "exp_iso" / "task1__full_ddiv"

        w1 = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.BASELINE,
            experiment_id="exp_iso",
            workspace_root=ws_baseline,
            provider="mock",
        )
        w2 = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="exp_iso",
            workspace_root=ws_ddiv,
            provider="mock",
        )

        r1 = w1.run()
        r2 = w2.run()

        # Both completed
        self.assertEqual(r1.status, ConditionJobStatus.COMPLETED)
        self.assertEqual(r2.status, ConditionJobStatus.COMPLETED)

        # Create a unique file in baseline agent_ws
        test_marker = ws_baseline / "agent_ws" / "baseline_only_file.txt"
        test_marker.write_text("baseline data", encoding="utf-8")

        # Verify it does NOT exist in full_ddiv workspace
        self.assertTrue(test_marker.exists())
        self.assertFalse((ws_ddiv / "agent_ws" / "baseline_only_file.txt").exists())

    def test_orchestrator_timeout_handling(self):
        """Verify orchestrator terminates child process tree and records TIMEOUT on deadline."""
        orch = ExperimentOrchestrator(
            experiment_id="exp_timeout_test",
            tasks=["mock-task-1"],
            conditions=[ExperimentCondition.BASELINE],
            provider="mock",
            worker_timeout=1,  # 1 second timeout
            base_dir=self.base_dir,
            workspace_base=self.workspace_base,
            logs_base=self.logs_base,
        )

        # Mock subprocess.Popen to simulate a long-running process
        class HangingPopen:
            def __init__(self, *args, **kwargs):
                self.pid = 99999
                self.returncode = None

            def wait(self, timeout=None):
                time.sleep(0.1)
                raise subprocess.TimeoutExpired(cmd="mock_cmd", timeout=timeout)

            def kill(self):
                self.returncode = -9

        with patch("subprocess.Popen", side_effect=HangingPopen), \
             patch.object(orch, "_terminate_process_tree") as mock_term:
            summary = orch.run_all()
            mock_term.assert_called_once()

        res_file = orch.results_dir / f"result_mock-task-1__{ExperimentCondition.BASELINE.value}.json"
        self.assertTrue(res_file.exists())
        record = ExperimentConditionRecord.load_from_file(res_file)
        self.assertEqual(record.status, ConditionJobStatus.TIMEOUT)
        self.assertIn("timed out", record.error_message)

    def test_orchestrator_crash_recovery(self):
        """Verify orchestrator handles child process crash gracefully and continues."""
        orch = ExperimentOrchestrator(
            experiment_id="exp_crash_test",
            tasks=["mock-task-1"],
            conditions=[ExperimentCondition.BASELINE],
            provider="mock",
            worker_timeout=10,
            base_dir=self.base_dir,
            workspace_base=self.workspace_base,
            logs_base=self.logs_base,
        )

        class CrashingPopen:
            def __init__(self, *args, **kwargs):
                self.pid = 88888
                self.returncode = 1

            def wait(self, timeout=None):
                return 1

        with patch("subprocess.Popen", side_effect=CrashingPopen):
            summary = orch.run_all()

        res_file = orch.results_dir / f"result_mock-task-1__{ExperimentCondition.BASELINE.value}.json"
        self.assertTrue(res_file.exists())
        record = ExperimentConditionRecord.load_from_file(res_file)
        self.assertEqual(record.status, ConditionJobStatus.FAILED)
        self.assertEqual(record.worker_exit_code, 1)

    def test_orchestrator_resumability(self):
        """Verify orchestrator skips already completed jobs when resume is active."""
        orch = ExperimentOrchestrator(
            experiment_id="exp_resume_test",
            tasks=["mock-task-1", "mock-task-2"],
            conditions=[ExperimentCondition.BASELINE],
            provider="mock",
            worker_timeout=10,
            base_dir=self.base_dir,
            workspace_base=self.workspace_base,
            logs_base=self.logs_base,
            resume=True,
        )

        # Pre-seed mock-task-1 as completed
        completed_rec = ExperimentConditionRecord(
            experiment_id="exp_resume_test",
            task_id="mock-task-1",
            condition=ExperimentCondition.BASELINE,
            status=ConditionJobStatus.COMPLETED,
            resolved=True,
            attempts=1,
            workspace_path=str(self.tmp_path),
        )
        res_file_1 = orch.results_dir / f"result_mock-task-1__{ExperimentCondition.BASELINE.value}.json"
        completed_rec.save_to_file(res_file_1)
        orch.manifest.update_job_status(
            "mock-task-1",
            ExperimentCondition.BASELINE,
            ConditionJobStatus.COMPLETED,
            result_file=str(res_file_1),
            resolved=True,
        )
        orch.manifest.save_to_file(orch.manifest_path)

        # Mock worker execution for mock-task-2
        dispatched_cmds = []

        class TrackingPopen:
            def __init__(self, cmd, *args, **kwargs):
                self.pid = 77777
                self.returncode = 0
                dispatched_cmds.append(cmd)
                # Create result file as worker would
                out_idx = cmd.index("--output-file") + 1
                out_path = Path(cmd[out_idx])
                rec = ExperimentConditionRecord(
                    experiment_id="exp_resume_test",
                    task_id=cmd[cmd.index("--task-id") + 1],
                    condition=ExperimentCondition.from_str(cmd[cmd.index("--condition") + 1]),
                    status=ConditionJobStatus.COMPLETED,
                    resolved=True,
                    attempts=1,
                    workspace_path=str(out_path.parent),
                )
                rec.save_to_file(out_path)

            def wait(self, timeout=None):
                return 0

        with patch("subprocess.Popen", side_effect=TrackingPopen):
            summary = orch.run_all()

        # Assert only mock-task-2 was dispatched
        self.assertEqual(len(dispatched_cmds), 1)
        self.assertIn("mock-task-2", dispatched_cmds[0])
        self.assertNotIn("mock-task-1", dispatched_cmds[0])

    def test_orchestrator_summary_generation(self):
        """Verify summary generation across conditions."""
        orch = ExperimentOrchestrator(
            experiment_id="exp_sum_test",
            tasks=["mock-task-1"],
            conditions=[ExperimentCondition.BASELINE, ExperimentCondition.RETRY_ONLY],
            provider="mock",
            base_dir=self.base_dir,
            workspace_base=self.workspace_base,
            logs_base=self.logs_base,
        )

        # Create two sample result records
        for cond in [ExperimentCondition.BASELINE, ExperimentCondition.RETRY_ONLY]:
            r = ExperimentConditionRecord(
                experiment_id="exp_sum_test",
                task_id="mock-task-1",
                condition=cond,
                status=ConditionJobStatus.COMPLETED,
                resolved=(cond == ExperimentCondition.RETRY_ONLY),
                attempts=1 if cond == ExperimentCondition.BASELINE else 2,
                execution_duration_seconds=5.0,
                workspace_path=str(self.tmp_path),
            )
            r_path = orch.results_dir / f"result_mock-task-1__{cond.value}.json"
            r.save_to_file(r_path)

        summary = orch.generate_summary()
        self.assertEqual(summary["total_tasks"], 1)
        self.assertEqual(summary["conditions"]["baseline"]["resolved_count"], 0)
        self.assertEqual(summary["conditions"]["retry_only"]["resolved_count"], 1)
        self.assertEqual(summary["conditions"]["retry_only"]["resolution_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
