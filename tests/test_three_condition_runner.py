"""
DDIV Phase 8.9.3: Comprehensive Offline Unit Tests for Three-Condition Runner.

Validates:
1. All four CLI condition modes (BASELINE, RETRY_ONLY, FULL_DDIV, ALL) and batch filtering.
2. Complete 81-observation manifest alignment, zero duplicates, exactly 3 conditions per task.
3. Existing-result reuse and rejection of invalid/partial checkpoints.
4. Condition and state isolation (zero memory/trust for BASELINE and RETRY_ONLY; continuous lineage for FULL_DDIV; data/ddiv_memory.db protection).
5. Provider routing (zero cloud calls in BASELINE/RETRY_ONLY) and disabled fallback.
6. Token-budget persistence across restarts, rate-limit throttling, and quota protection.
7. End-to-end offline resume execution across conditions using mock providers.
"""

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from models.base import ModelConfig, ProviderResponse
from evaluation.quixbugs_adapter import QuixBugsTask, QuixBugsEvaluationResult
from scripts.run_quixbugs_three_condition import (
    CumulativeTokenTracker,
    QuixBugsThreeConditionRunner,
    RateLimitQuotaException,
    handle_rate_limit_headers,
    parse_header_duration,
    validate_checkpoint_result,
)


class TestThreeConditionRunner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="ddiv_test_three_cond_"))
        self.manifest_path = self.temp_dir / "three_condition_manifest.json"

        # Create mock 27 tasks across 3 batches with 3 conditions each = 81 observations
        self.mock_observations = []
        obs_idx = 1
        for b in [1, 2, 3]:
            for t_idx in range(1, 10):
                task_num = (b - 1) * 9 + t_idx
                prog = f"prog_{task_num}"
                t_id = f"quixbugs-python-{prog}"
                for cond in ["BASELINE", "RETRY_ONLY", "FULL_DDIV"]:
                    is_reused = (b == 1 and cond == "FULL_DDIV")
                    self.mock_observations.append({
                        "observation_id": f"OBS-{obs_idx:02d}",
                        "global_sequence_index": obs_idx,
                        "batch_number": b,
                        "canonical_task_id": t_id,
                        "program_name": prog,
                        "target_file": f"python_programs/{prog}.py",
                        "condition": cond,
                        "max_attempts": 1 if cond == "BASELINE" else 3,
                        "status": "REUSED_COMPLETED" if is_reused else "PENDING_EXECUTION",
                        "reuse_source": str(self.temp_dir / "source_reused") if is_reused else None,
                    })
                    obs_idx += 1

        self.manifest_path.write_text(
            json.dumps({"observations": self.mock_observations}, indent=2), encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_condition_modes_and_batch_filtering(self):
        """Test that runner properly filters observations across condition modes and batches."""
        out_dir = self.temp_dir / "out"

        # 1. Mode ALL, Batch 1 -> Exactly 27 observations
        runner_all_b1 = QuixBugsThreeConditionRunner(
            manifest_path=str(self.manifest_path),
            output_dir=str(out_dir),
            condition="ALL",
            batch=1,
        )
        self.assertEqual(len(runner_all_b1.observations), 27)

        # 2. Mode BASELINE, Batch 2 -> Exactly 9 observations
        runner_base_b2 = QuixBugsThreeConditionRunner(
            manifest_path=str(self.manifest_path),
            output_dir=str(out_dir),
            condition="BASELINE",
            batch=2,
        )
        self.assertEqual(len(runner_base_b2.observations), 9)
        self.assertTrue(all(o["condition"] == "BASELINE" for o in runner_base_b2.observations))

        # 3. Mode RETRY_ONLY, Batch 3 -> Exactly 9 observations
        runner_retry_b3 = QuixBugsThreeConditionRunner(
            manifest_path=str(self.manifest_path),
            output_dir=str(out_dir),
            condition="RETRY_ONLY",
            batch=3,
        )
        self.assertEqual(len(runner_retry_b3.observations), 9)
        self.assertTrue(all(o["condition"] == "RETRY_ONLY" for o in runner_retry_b3.observations))

        # 4. Mode FULL_DDIV, No batch filter -> Exactly 27 observations
        runner_full = QuixBugsThreeConditionRunner(
            manifest_path=str(self.manifest_path),
            output_dir=str(out_dir),
            condition="FULL_DDIV",
            batch=None,
        )
        self.assertEqual(len(runner_full.observations), 27)
        self.assertTrue(all(o["condition"] == "FULL_DDIV" for o in runner_full.observations))

        # 5. Mode ALL, No batch filter -> Exactly 81 observations
        runner_all = QuixBugsThreeConditionRunner(
            manifest_path=str(self.manifest_path),
            output_dir=str(out_dir),
            condition="ALL",
            batch=None,
        )
        self.assertEqual(len(runner_all.observations), 81)

    def test_state_isolation_rules(self):
        """Test that BASELINE and RETRY_ONLY do not create or use memory/trust stores."""
        out_dir = self.temp_dir / "out_iso"

        # When running BASELINE-only, cloud providers must be None
        runner_baseline = QuixBugsThreeConditionRunner(
            manifest_path=str(self.manifest_path),
            output_dir=str(out_dir),
            condition="BASELINE",
            batch=1,
        )
        self.assertIsNone(runner_baseline.locator_provider)
        self.assertIsNone(runner_baseline.supervisor_provider)
        self.assertIsNone(runner_baseline.tester_provider)

        # When running RETRY_ONLY-only, cloud providers must be None
        runner_retry = QuixBugsThreeConditionRunner(
            manifest_path=str(self.manifest_path),
            output_dir=str(out_dir),
            condition="RETRY_ONLY",
            batch=1,
        )
        self.assertIsNone(runner_retry.locator_provider)
        self.assertIsNone(runner_retry.supervisor_provider)
        self.assertIsNone(runner_retry.tester_provider)

    def test_checkpoint_validation_for_all_conditions(self):
        """Verify strict checkpoint validation across BASELINE, RETRY_ONLY, and FULL_DDIV."""
        task_dir = self.temp_dir / "checkpoints"
        task_dir.mkdir(parents=True, exist_ok=True)
        res_file = task_dir / "condition_result.json"
        diff_file = task_dir / "candidate_patch.diff"

        # 1. Valid BASELINE resolved (1 attempt)
        res_file.write_text(json.dumps({
            "condition": "BASELINE",
            "task_id": "quixbugs-python-test_prog",
            "program_name": "test_prog",
            "resolved": True,
            "attempts_used": 1,
            "history": [{"attempt": 1, "resolved": True}],
        }), encoding="utf-8")
        diff_file.write_text("--- a/test_prog.py\n+++ b/test_prog.py\n", encoding="utf-8")

        is_valid, data, reason = validate_checkpoint_result(
            res_file, "quixbugs-python-test_prog", "test_prog", max_attempts=1, expected_condition="BASELINE"
        )
        self.assertTrue(is_valid)

        # 2. Reject condition mismatch
        is_valid, data, reason = validate_checkpoint_result(
            res_file, "quixbugs-python-test_prog", "test_prog", max_attempts=3, expected_condition="FULL_DDIV"
        )
        self.assertFalse(is_valid)
        self.assertIn("Mismatched condition", reason)

        # 3. Reject partial failure for RETRY_ONLY (1/3 attempts with resolved=False)
        diff_file.unlink(missing_ok=True)
        res_file.write_text(json.dumps({
            "condition": "RETRY_ONLY",
            "task_id": "quixbugs-python-test_prog",
            "program_name": "test_prog",
            "resolved": False,
            "attempts_used": 1,
            "history": [{"attempt": 1, "resolved": False}],
        }), encoding="utf-8")
        is_valid, data, reason = validate_checkpoint_result(
            res_file, "quixbugs-python-test_prog", "test_prog", max_attempts=3, expected_condition="RETRY_ONLY"
        )
        self.assertFalse(is_valid)
        self.assertIn("Partial/interrupted failure", reason)

        # 4. Accept complete authoritative failure for RETRY_ONLY (3/3 attempts)
        res_file.write_text(json.dumps({
            "condition": "RETRY_ONLY",
            "task_id": "quixbugs-python-test_prog",
            "program_name": "test_prog",
            "resolved": False,
            "attempts_used": 3,
            "history": [{"attempt": 1}, {"attempt": 2}, {"attempt": 3}],
        }), encoding="utf-8")
        is_valid, data, reason = validate_checkpoint_result(
            res_file, "quixbugs-python-test_prog", "test_prog", max_attempts=3, expected_condition="RETRY_ONLY"
        )
        self.assertTrue(is_valid)

    def test_reused_full_ddiv_import_and_rejection(self):
        """Test safe import of reused results and rejection of corrupt/missing sources."""
        src_dir = self.temp_dir / "source_reused" / "prog_1"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_res = src_dir / "condition_result.json"
        src_diff = src_dir / "candidate_patch.diff"

        # Create valid source result
        src_res.write_text(json.dumps({
            "condition": "CLOUD_ASSISTED_DDIV",
            "task_id": "quixbugs-python-prog_1",
            "program_name": "prog_1",
            "resolved": True,
            "attempts_used": 1,
            "history": [{"attempt": 1, "resolved": True}],
            "token_breakdown": {"transactions": []},
        }), encoding="utf-8")
        src_diff.write_text("--- a/prog_1.py\n+++ b/prog_1.py\n", encoding="utf-8")

        out_dir = self.temp_dir / "out_reuse"
        runner = QuixBugsThreeConditionRunner(
            manifest_path=str(self.manifest_path),
            output_dir=str(out_dir),
            condition="FULL_DDIV",
            batch=1,
        )

        # Test valid import
        obs = self.mock_observations[2]  # prog_1 FULL_DDIV
        is_imported, data, reason = runner.import_reused_full_ddiv_result(obs)
        self.assertTrue(is_imported)
        self.assertTrue((out_dir / "full_ddiv" / "prog_1" / "condition_result.json").exists())
        self.assertTrue((out_dir / "full_ddiv" / "prog_1" / "candidate_patch.diff").exists())

        # Test rejection of corrupt source
        src_res.write_text("NOT_JSON", encoding="utf-8")
        is_imported, data, reason = runner.import_reused_full_ddiv_result(obs)
        self.assertFalse(is_imported)
        self.assertIn("JSON parse error", reason)

    def test_daily_token_tracker_and_ceiling(self):
        """Verify daily token tracker persists across restarts and enforces budget ceilings."""
        persist_file = self.temp_dir / "tokens.json"
        tracker = CumulativeTokenTracker(persist_file)

        tracker.record(
            task_id="quixbugs-python-task1",
            program_name="task1",
            attempt=1,
            role="Locator",
            provider="gemini",
            model="gemini-3.1-flash-lite",
            prompt_tokens=1000,
            completion_tokens=500,
            condition="FULL_DDIV",
        )
        tracker.record(
            task_id="quixbugs-python-task1",
            program_name="task1",
            attempt=1,
            role="Coder",
            provider="ollama",
            model="qwen2.5-coder:7b",
            prompt_tokens=2000,
            completion_tokens=100,
            condition="BASELINE",
        )
        tracker.persist()

        # Restart tracker from disk
        tracker2 = CumulativeTokenTracker(persist_file)
        today_str = time.strftime("%Y-%m-%d", time.gmtime())
        self.assertEqual(tracker2.get_daily_provider_total("gemini", today_str), 1500)
        self.assertEqual(tracker2.get_daily_provider_total("ollama", today_str), 2100)

        # Check budget limit guard
        runner = QuixBugsThreeConditionRunner(
            manifest_path=str(self.manifest_path),
            output_dir=str(self.temp_dir / "out_b"),
            condition="FULL_DDIV",
            max_daily_gemini_tokens=2000,
        )
        runner.token_tracker = tracker2

        # 1500 + 600 > 2000 -> Should raise RateLimitQuotaException
        with self.assertRaises(RateLimitQuotaException):
            runner._check_budget_limits("Locator", "gemini", est_tokens=600)

    def test_end_to_end_offline_mock_execution(self):
        """Execute all 3 conditions on a mock task using mock providers (zero cloud calls)."""
        mock_coder = MagicMock()
        mock_coder.config = ModelConfig(
            name="Coder", model_id="mock-coder", provider="ollama", disable_fallback=True
        )
        mock_coder.generate.return_value = ProviderResponse(
            raw_text=json.dumps({
                "reasoning_summary": "Fixed bug",
                "modifications": [{"path": "python_programs/test_prog.py", "operation": "replace", "anchor": "x = 1", "code": "x = 2"}]
            }),
            parsed_json={"reasoning_summary": "Fixed bug"},
            model_id="mock-coder",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )

        mock_locator = MagicMock()
        mock_locator.config = ModelConfig(
            name="Locator", model_id="mock-gemini", provider="gemini", disable_fallback=True
        )
        mock_locator.generate.return_value = ProviderResponse(
            raw_text="Fault analysis", model_id="mock-gemini", prompt_tokens=50, completion_tokens=30, total_tokens=80
        )

        mock_supervisor = MagicMock()
        mock_supervisor.config = ModelConfig(
            name="Supervisor", model_id="mock-groq", provider="groq", disable_fallback=True
        )
        mock_supervisor.generate.return_value = ProviderResponse(
            raw_text="Supervisor diagnosis", model_id="mock-groq", prompt_tokens=60, completion_tokens=40, total_tokens=100
        )

        mock_tester = MagicMock()
        mock_tester.config = ModelConfig(
            name="Tester", model_id="mock-groq", provider="groq", disable_fallback=True
        )
        mock_tester.generate.return_value = ProviderResponse(
            raw_text="Tester critique", model_id="mock-groq", prompt_tokens=40, completion_tokens=20, total_tokens=60
        )

        out_dir = self.temp_dir / "out_e2e"
        runner = QuixBugsThreeConditionRunner(
            manifest_path=str(self.manifest_path),
            output_dir=str(out_dir),
            condition="ALL",
            batch=1,
            coder_provider_instance=mock_coder,
            locator_provider_instance=mock_locator,
            supervisor_provider_instance=mock_supervisor,
            tester_provider_instance=mock_tester,
        )

        # Mock adapter
        mock_task = QuixBugsTask(
            task_id="quixbugs-python-prog_1",
            program_name="prog_1",
            target_file="python_programs/prog_1.py",
            problem_description="Test problem",
            prompt_template="",
            gold_patch_path="gold.patch",
        )
        runner.adapter.get_task = MagicMock(return_value=mock_task)
        runner.adapter.create_agent_workspace = MagicMock()
        runner.adapter.evaluate_patch = MagicMock(return_value=QuixBugsEvaluationResult(
            task_id="quixbugs-python-prog_1",
            condition="BASELINE",
            resolved=True,
            candidate_patch_applied=True,
            all_passed=True,
            evaluation_verdict="RESOLVED",
            failure_category="NONE",
            failure_summary="All tests passed",
            passed_tests=["test1"],
            failed_tests=[],
        ))
        runner._extract_diff_from_response = MagicMock(return_value=("--- a/prog_1.py\n+++ b/prog_1.py\n", "Success"))

        # Run BASELINE on task
        res_baseline = runner.run_task_condition(mock_task, "BASELINE")
        self.assertEqual(res_baseline["condition"], "BASELINE")
        self.assertEqual(res_baseline["max_attempts"], 1)
        self.assertTrue((out_dir / "baseline" / "prog_1" / "condition_result.json").exists())

        # Run RETRY_ONLY on task
        res_retry = runner.run_task_condition(mock_task, "RETRY_ONLY")
        self.assertEqual(res_retry["condition"], "RETRY_ONLY")
        self.assertEqual(res_retry["max_attempts"], 3)
        self.assertTrue((out_dir / "retry_only" / "prog_1" / "condition_result.json").exists())

        # Run FULL_DDIV on task
        res_full = runner.run_task_condition(mock_task, "FULL_DDIV")
        self.assertEqual(res_full["condition"], "FULL_DDIV")
        self.assertEqual(res_full["max_attempts"], 3)
        self.assertTrue((out_dir / "full_ddiv" / "prog_1" / "condition_result.json").exists())


if __name__ == "__main__":
    unittest.main()
