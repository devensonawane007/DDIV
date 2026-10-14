"""Unit tests for DDIV launch safety, manifest protection, consistency checks, history preservation, and batch aggregation."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from core.conditions import ExperimentCondition
from core.experiment_orchestrator import ExperimentOrchestrator
from core.experiment_record import ConditionJobStatus, ExperimentConditionRecord, ExperimentManifest


class TestLaunchSafety:
    """Verifies operational launch safeguards without live API calls."""

    def test_01_manifest_reset_guard_raises_without_force_rerun(self, tmp_path):
        """Omitting resume or passing resume=False on an existing experiment must raise RuntimeError unless force_rerun=True."""
        base_dir = tmp_path / "experiments"
        exp_id = "test_guard_exp"
        ws_base = tmp_path / "workspaces"
        logs_base = tmp_path / "logs"

        # Create initial experiment manifest
        orch1 = ExperimentOrchestrator(
            experiment_id=exp_id,
            tasks=["mock-task-1"],
            conditions=["baseline"],
            provider="mock",
            base_dir=base_dir,
            workspace_base=ws_base,
            logs_base=logs_base,
            resume=True,
        )
        assert orch1.manifest_path.exists()

        # Attempt to re-initialize with resume=False without force_rerun -> MUST raise RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            ExperimentOrchestrator(
                experiment_id=exp_id,
                tasks=["mock-task-1"],
                conditions=["baseline"],
                provider="mock",
                base_dir=base_dir,
                workspace_base=ws_base,
                logs_base=logs_base,
                resume=False,
                force_rerun=False,
            )
        assert "Cannot reset an existing experiment without --force-rerun" in str(exc_info.value)

    def test_02_manifest_reset_with_force_rerun_creates_backup(self, tmp_path):
        """Passing force_rerun=True on an existing manifest backs up the existing manifest before resetting."""
        base_dir = tmp_path / "experiments"
        exp_id = "test_force_rerun_exp"
        ws_base = tmp_path / "workspaces"
        logs_base = tmp_path / "logs"

        orch1 = ExperimentOrchestrator(
            experiment_id=exp_id,
            tasks=["mock-task-1"],
            conditions=["baseline"],
            provider="mock",
            base_dir=base_dir,
            workspace_base=ws_base,
            logs_base=logs_base,
            resume=True,
        )
        orch1.manifest.update_job_status("mock-task-1", "baseline", ConditionJobStatus.COMPLETED)
        orch1.manifest.save_to_file(orch1.manifest_path)

        # Re-initialize with force_rerun=True
        orch2 = ExperimentOrchestrator(
            experiment_id=exp_id,
            tasks=["mock-task-1"],
            conditions=["baseline"],
            provider="mock",
            base_dir=base_dir,
            workspace_base=ws_base,
            logs_base=logs_base,
            resume=False,
            force_rerun=True,
        )
        # Check that backup manifest exists
        backup_files = list((base_dir / exp_id).glob("manifest.bak.*.json"))
        assert len(backup_files) >= 1
        bak_data = json.loads(backup_files[0].read_text(encoding="utf-8"))
        assert "mock-task-1__baseline" in bak_data["jobs"]
        assert bak_data["jobs"]["mock-task-1__baseline"]["status"] == "COMPLETED"

    def test_03_consistency_check_redispatches_when_result_corrupted(self, tmp_path):
        """If manifest says COMPLETED but result file is corrupted or missing, orchestrator must re-dispatch."""
        base_dir = tmp_path / "experiments"
        exp_id = "test_inconsistency_exp"
        ws_base = tmp_path / "workspaces"
        logs_base = tmp_path / "logs"

        orch = ExperimentOrchestrator(
            experiment_id=exp_id,
            tasks=["mock-task-1"],
            conditions=["baseline"],
            provider="mock",
            base_dir=base_dir,
            workspace_base=ws_base,
            logs_base=logs_base,
            resume=True,
        )
        # Set manifest to COMPLETED
        orch.manifest.update_job_status("mock-task-1", "baseline", ConditionJobStatus.COMPLETED)
        orch.manifest.save_to_file(orch.manifest_path)

        # Write corrupted result file
        res_file = orch.results_dir / "result_mock-task-1__baseline.json"
        res_file.write_text("{invalid json", encoding="utf-8")

        # Run orchestrator in mock mode - should re-dispatch, detect corrupted file, and produce valid record
        summary = orch.run_all()
        assert summary["conditions"]["baseline"]["completed_runs"] == 1
        # Result file should now be valid JSON with COMPLETED
        rec = json.loads(res_file.read_text(encoding="utf-8"))
        assert rec["status"] == "COMPLETED"

    def test_04_history_archiving_on_redispatch_of_failed_job(self, tmp_path):
        """When an incomplete/failed job is re-dispatched under resume, the old result file is archived to history/."""
        base_dir = tmp_path / "experiments"
        exp_id = "test_history_archive_exp"
        ws_base = tmp_path / "workspaces"
        logs_base = tmp_path / "logs"

        orch = ExperimentOrchestrator(
            experiment_id=exp_id,
            tasks=["mock-task-1"],
            conditions=["baseline"],
            provider="mock",
            base_dir=base_dir,
            workspace_base=ws_base,
            logs_base=logs_base,
            resume=True,
        )
        # Set job to FAILED and write a failed result file
        orch.manifest.update_job_status("mock-task-1", "baseline", ConditionJobStatus.FAILED)
        orch.manifest.save_to_file(orch.manifest_path)

        res_file = orch.results_dir / "result_mock-task-1__baseline.json"
        failed_rec = {
            "experiment_id": exp_id,
            "task_id": "mock-task-1",
            "condition": "baseline",
            "status": "FAILED",
            "error_message": "Original failure message",
            "attempts": 0,
        }
        res_file.write_text(json.dumps(failed_rec), encoding="utf-8")

        # Now run orchestrator with resume=True -> should archive the failed record to history/ before dispatch
        summary = orch.run_all()
        assert summary["conditions"]["baseline"]["completed_runs"] == 1

        history_dir = base_dir / exp_id / "history"
        assert history_dir.exists()
        history_files = list(history_dir.glob("result_mock-task-1__baseline.attempt_*.json"))
        assert len(history_files) == 1
        archived_data = json.loads(history_files[0].read_text(encoding="utf-8"))
        assert archived_data["status"] == "FAILED"
        assert archived_data["error_message"] == "Original failure message"

    def test_05_batch_isolation_and_aggregation(self, tmp_path):
        """7 separate batch directories remain isolated, and aggregate script combines all 60 jobs without modifying sources."""
        batches = []
        total_created = 0

        for b in range(1, 8):
            b_dir = tmp_path / f"benchmark_v2_1_batch_{b}"
            res_dir = b_dir / "results"
            res_dir.mkdir(parents=True)
            tasks_cnt = 3 if b < 7 else 2

            for t in range(1, tasks_cnt + 1):
                tid = f"repo__task-b{b}-t{t}"
                for cond in ["baseline", "retry_only", "full_ddiv"]:
                    rec = {
                        "experiment_id": f"benchmark_v2_1_batch_{b}",
                        "task_id": tid,
                        "condition": cond,
                        "status": "COMPLETED",
                        "resolved": (cond == "full_ddiv" and t == 1),
                        "workflow_completed": True,
                        "attempts": 1,
                        "execution_duration_seconds": 15.0,
                    }
                    rf = res_dir / f"result_{tid}__{cond}.json"
                    rf.write_text(json.dumps(rec), encoding="utf-8")
                    total_created += 1

        assert total_created == 60

        out_report = tmp_path / "aggregated_report.md"
        dirs = [str(tmp_path / f"benchmark_v2_1_batch_{b}" / "results") for b in range(1, 8)]
        cmd = ["python", "scripts/aggregate_experiment_report.py", "--dir"] + dirs + ["--output", str(out_report), "--detailed"]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        assert out_report.exists()
        content = out_report.read_text(encoding="utf-8")
        assert "DDIV Research Experiment Evaluation Report" in content
        # Verify 60 jobs present in report
        assert "repo__task-b1-t1" in content
        assert "repo__task-b7-t2" in content

    def test_06_launch_gate_dual_model_quota_validation(self):
        """Pre-launch gate check requires explicit, positive, sufficient quotas for both models."""
        from scripts.launch_gate_check import check_gate

        # 1. Missing quotas -> NO-GO
        assert check_gate(1, None, None) is False

        # 2. Negative or zero quotas -> NO-GO
        assert check_gate(1, -100, 150000) is False
        assert check_gate(1, 170000, 0) is False

        # 3. Asymmetric quotas: Sufficient GPT, missing/insufficient Qwen -> NO-GO
        assert check_gate(1, 200000, None) is False
        assert check_gate(1, 200000, 50000) is False  # Batch 1 needs 114,321

        # 4. Asymmetric quotas: Missing/insufficient GPT, sufficient Qwen -> NO-GO
        assert check_gate(1, None, 200000) is False
        assert check_gate(1, 100000, 200000) is False  # Batch 1 needs 161,522

        # 5. Dual sufficient quotas -> GO (Batch 1 needs GPT: 161,522, Qwen: 114,321)
        assert check_gate(1, 161522, 114321) is True
        assert check_gate(1, 170000, 120000) is True

    def test_07_history_archiving_avoids_filename_collisions(self, tmp_path, monkeypatch):
        """Repeated archiving within the same second or with identical timestamps appends an incrementing counter."""
        from datetime import datetime, timezone

        base_dir = tmp_path / "experiments"
        exp_id = "test_collision_exp"
        ws_base = tmp_path / "workspaces"
        logs_base = tmp_path / "logs"

        orch = ExperimentOrchestrator(
            experiment_id=exp_id,
            tasks=["mock-task-1"],
            conditions=["baseline"],
            provider="mock",
            base_dir=base_dir,
            workspace_base=ws_base,
            logs_base=logs_base,
            resume=True,
        )

        res_file = orch.results_dir / "result_mock-task-1__baseline.json"
        res_file.write_text(json.dumps({"attempt": 1}), encoding="utf-8")

        # Freeze the timestamp
        fixed_dt = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)
        class MockDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_dt

        monkeypatch.setattr("core.experiment_orchestrator.datetime.datetime", MockDateTime)

        # First run: should archive attempt 1 and write new completed result
        orch.run_all()

        history_dir = base_dir / exp_id / "history"
        assert history_dir.exists()
        history_files = sorted(history_dir.glob("*.json"))
        assert len(history_files) == 1
        assert history_files[0].name == "result_mock-task-1__baseline.attempt_20261012_120000.json"

        # Now force another re-dispatch with the same frozen timestamp
        # Invalidate the current result file so it is re-dispatched
        res_file.write_text(json.dumps({"attempt": 2, "status": "FAILED"}), encoding="utf-8")
        orch.manifest.update_job_status("mock-task-1", "baseline", ConditionJobStatus.FAILED)
        orch.manifest.save_to_file(orch.manifest_path)

        orch.run_all()

        history_files = sorted(history_dir.glob("*.json"))
        assert len(history_files) == 2
        file_names = [f.name for f in history_files]
        assert "result_mock-task-1__baseline.attempt_20261012_120000.json" in file_names
        assert "result_mock-task-1__baseline.attempt_20261012_120000_1.json" in file_names

    def test_08_force_rerun_preserves_completed_result_to_history(self, tmp_path):
        """Under force_rerun=True, pre-existing completed result files are archived to history/ before re-execution."""
        base_dir = tmp_path / "experiments"
        exp_id = "test_force_rerun_archive_exp"
        ws_base = tmp_path / "workspaces"
        logs_base = tmp_path / "logs"

        # Initial completed run
        orch1 = ExperimentOrchestrator(
            experiment_id=exp_id,
            tasks=["mock-task-1"],
            conditions=["baseline"],
            provider="mock",
            base_dir=base_dir,
            workspace_base=ws_base,
            logs_base=logs_base,
            resume=True,
        )
        orch1.run_all()

        res_file = orch1.results_dir / "result_mock-task-1__baseline.json"
        assert res_file.exists()
        rec1 = json.loads(res_file.read_text(encoding="utf-8"))
        assert rec1["status"] == "COMPLETED"

        # Force rerun
        orch2 = ExperimentOrchestrator(
            experiment_id=exp_id,
            tasks=["mock-task-1"],
            conditions=["baseline"],
            provider="mock",
            base_dir=base_dir,
            workspace_base=ws_base,
            logs_base=logs_base,
            resume=False,
            force_rerun=True,
        )
        orch2.run_all()

        history_dir = base_dir / exp_id / "history"
        assert history_dir.exists()
        archived_files = list(history_dir.glob("result_mock-task-1__baseline.attempt_*.json"))
        assert len(archived_files) >= 1
        archived_rec = json.loads(archived_files[0].read_text(encoding="utf-8"))
        assert archived_rec["status"] == "COMPLETED"

    def test_09_aggregation_deduplicates_active_records_and_reports_malformed(self, tmp_path):
        """Aggregate report deduplicates across overlapping directories keeping latest record, and logs warnings for malformed JSON."""
        dir1 = tmp_path / "batch_1" / "results"
        dir2 = tmp_path / "batch_2" / "results"
        dir1.mkdir(parents=True)
        dir2.mkdir(parents=True)

        # Duplicate task in both dirs with different timestamps
        rec_older = {
            "task_id": "test__task-1",
            "condition": "baseline",
            "status": "COMPLETED",
            "resolved": False,
            "completed_at": "2026-10-12T10:00:00Z",
            "attempts": 1,
            "execution_duration_seconds": 10.0,
        }
        rec_newer = {
            "task_id": "test__task-1",
            "condition": "baseline",
            "status": "COMPLETED",
            "resolved": True,
            "completed_at": "2026-10-12T12:00:00Z",
            "attempts": 2,
            "execution_duration_seconds": 20.0,
        }
        (dir1 / "result_test__task-1__baseline.json").write_text(json.dumps(rec_older), encoding="utf-8")
        (dir2 / "result_test__task-1__baseline.json").write_text(json.dumps(rec_newer), encoding="utf-8")

        # Malformed JSON in dir1
        corrupt_file = dir1 / "result_corrupt__baseline.json"
        corrupt_file.write_text("{broken json...", encoding="utf-8")

        out_report = tmp_path / "report.md"
        cmd = [
            "python",
            "scripts/aggregate_experiment_report.py",
            "--dir",
            str(dir1),
            str(dir2),
            "--output",
            str(out_report),
            "--detailed",
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        assert out_report.exists()

        # Check stderr for warning about duplicate and malformed file
        assert "Duplicate record for test__task-1 [baseline]" in proc.stderr
        assert "Malformed or unreadable record" in proc.stderr

        # Check that the newer record (resolved=True, attempts=2) was retained in aggregated report
        content = out_report.read_text(encoding="utf-8")
        assert "test__task-1" in content
        assert "YES" in content  # resolved is YES from newer record
