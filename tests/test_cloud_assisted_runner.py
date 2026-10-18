"""
DDIV Phase 8.8.3: Offline Unit Tests for Cloud-Assisted Runner Safety Fixes.

Validates:
1. Deterministic batching and task filtering (--batch 1, 2, 3).
2. Strict checkpoint validation (valid resolved, complete failure, partial interruption, corrupt).
3. Cumulative token accounting with prompt/completion separation and process restart persistence.
4. Rate limit response header parsing and throttling logic.
5. Daily budget ceiling enforcement and graceful stop.
6. Fallback prevention (verifying gpt-oss-120b is never invoked).
7. Quota exhaustion handling without data corruption.
8. End-to-end offline resume behavior using mock providers.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from models.base import ModelConfig, ProviderResponse
from models.providers import ErrorCategory, OpenAICompatibleProvider
from scripts.run_quixbugs_cloud_assisted import (
    CumulativeTokenTracker,
    QuixBugsCloudAssistedRunner,
    RateLimitQuotaException,
    handle_rate_limit_headers,
    parse_header_duration,
    validate_checkpoint_result,
)


class TestCloudAssistedRunnerSafety(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="ddiv_test_cloud_runner_"))
        self.manifest_path = self.temp_dir / "unresolved_manifest.json"
        self.batch_manifest_path = self.temp_dir / "batch_manifest.json"

        # Create mock 27 tasks
        self.mock_tasks = []
        for i in range(1, 28):
            self.mock_tasks.append({
                "canonical_task_id": f"quixbugs-python-task_{i}",
                "program_name": f"task_{i}",
                "target_file": f"python_programs/task_{i}.py",
                "attempts_used_local": 3,
                "final_failure_category": "ASSERTION_FAILURE",
                "final_verdict": "UNRESOLVED",
                "patch_applied": True,
                "local_tokens": 5000 + i * 10,
                "local_duration_s": 30.0,
            })

        self.manifest_path.write_text(json.dumps({"tasks": self.mock_tasks}), encoding="utf-8")

        # Create mock batch manifest
        batch_data = {
            "batches": [
                {"batch_id": "batch_1", "tasks": self.mock_tasks[0:9]},
                {"batch_id": "batch_2", "tasks": self.mock_tasks[9:18]},
                {"batch_id": "batch_3", "tasks": self.mock_tasks[18:27]},
            ]
        }
        self.batch_manifest_path.write_text(json.dumps(batch_data), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_batch_partitioning_and_filtering(self):
        """Test that runner properly partitions into 3 deterministic batches of 9 tasks."""
        out_dir = self.temp_dir / "out"

        # Batch 1
        runner_b1 = QuixBugsCloudAssistedRunner(
            task_manifest_path=self.manifest_path,
            output_dir=out_dir,
            batch=1,
            batch_manifest_path=self.batch_manifest_path,
        )
        self.assertEqual(len(runner_b1.manifest_tasks), 9)
        self.assertEqual(runner_b1.manifest_tasks[0]["program_name"], "task_1")
        self.assertEqual(runner_b1.manifest_tasks[-1]["program_name"], "task_9")

        # Batch 2
        runner_b2 = QuixBugsCloudAssistedRunner(
            task_manifest_path=self.manifest_path,
            output_dir=out_dir,
            batch=2,
            batch_manifest_path=self.batch_manifest_path,
        )
        self.assertEqual(len(runner_b2.manifest_tasks), 9)
        self.assertEqual(runner_b2.manifest_tasks[0]["program_name"], "task_10")
        self.assertEqual(runner_b2.manifest_tasks[-1]["program_name"], "task_18")

        # Batch 3
        runner_b3 = QuixBugsCloudAssistedRunner(
            task_manifest_path=self.manifest_path,
            output_dir=out_dir,
            batch=3,
            batch_manifest_path=self.batch_manifest_path,
        )
        self.assertEqual(len(runner_b3.manifest_tasks), 9)
        self.assertEqual(runner_b3.manifest_tasks[0]["program_name"], "task_19")
        self.assertEqual(runner_b3.manifest_tasks[-1]["program_name"], "task_27")

        # Invalid batch raises
        with self.assertRaises(ValueError):
            QuixBugsCloudAssistedRunner(
                task_manifest_path=self.manifest_path,
                output_dir=out_dir,
                batch=4,
            )

    def test_checkpoint_validation_strict(self):
        """Test that only validated, complete results matching config are skipped."""
        task_dir = self.temp_dir / "task_1"
        task_dir.mkdir(parents=True, exist_ok=True)
        res_file = task_dir / "condition_result.json"
        diff_file = task_dir / "candidate_patch.diff"

        # 1. Non-existent file
        is_valid, _, reason = validate_checkpoint_result(
            self.temp_dir / "non_existent.json", "quixbugs-python-task_1", "task_1", 3
        )
        self.assertFalse(is_valid)

        # 2. Corrupt / empty file
        res_file.write_text("", encoding="utf-8")
        is_valid, _, reason = validate_checkpoint_result(
            res_file, "quixbugs-python-task_1", "task_1", 3
        )
        self.assertFalse(is_valid)
        self.assertIn("empty", reason.lower())

        # 3. Partial/interrupted failure (attempts_used=1 < max_attempts=3, resolved=False)
        partial_data = {
            "condition": "CLOUD_ASSISTED_DDIV",
            "task_id": "quixbugs-python-task_1",
            "program_name": "task_1",
            "resolved": False,
            "attempts_used": 1,
            "max_attempts": 3,
            "history": [{"attempt": 1, "resolved": False}],
        }
        res_file.write_text(json.dumps(partial_data), encoding="utf-8")
        is_valid, _, reason = validate_checkpoint_result(
            res_file, "quixbugs-python-task_1", "task_1", 3
        )
        self.assertFalse(is_valid)
        self.assertIn("partial", reason.lower())

        # 4. Valid complete failure (attempts_used=3 == max_attempts=3, resolved=False)
        complete_failure = {
            "condition": "CLOUD_ASSISTED_DDIV",
            "task_id": "quixbugs-python-task_1",
            "program_name": "task_1",
            "resolved": False,
            "attempts_used": 3,
            "max_attempts": 3,
            "history": [{"attempt": 1}, {"attempt": 2}, {"attempt": 3}],
        }
        res_file.write_text(json.dumps(complete_failure), encoding="utf-8")
        is_valid, data, reason = validate_checkpoint_result(
            res_file, "quixbugs-python-task_1", "task_1", 3
        )
        self.assertTrue(is_valid)
        self.assertIn("authoritative failure", reason.lower())

        # 5. Resolved result without candidate_patch.diff -> invalid
        resolved_data = {
            "condition": "CLOUD_ASSISTED_DDIV",
            "task_id": "quixbugs-python-task_1",
            "program_name": "task_1",
            "resolved": True,
            "attempts_used": 2,
            "max_attempts": 3,
            "history": [{"attempt": 1}, {"attempt": 2, "resolved": True}],
        }
        res_file.write_text(json.dumps(resolved_data), encoding="utf-8")
        if diff_file.exists():
            diff_file.unlink()
        is_valid, _, reason = validate_checkpoint_result(
            res_file, "quixbugs-python-task_1", "task_1", 3
        )
        self.assertFalse(is_valid)
        self.assertIn("missing candidate_patch.diff", reason.lower())

        # 6. Resolved result WITH candidate_patch.diff -> valid
        diff_file.write_text("--- a/test.py\n+++ b/test.py\n", encoding="utf-8")
        is_valid, data, reason = validate_checkpoint_result(
            res_file, "quixbugs-python-task_1", "task_1", 3
        )
        self.assertTrue(is_valid)
        self.assertTrue(data["resolved"])

    def test_cumulative_token_accounting_and_persistence(self):
        """Test granular token accounting and persistence across process restarts."""
        persist_file = self.temp_dir / "tokens.json"
        tracker = CumulativeTokenTracker(persist_file)

        # Record Locator call
        tracker.record(
            task_id="quixbugs-python-task_1",
            program_name="task_1",
            attempt=0,
            role="Locator",
            provider="gemini",
            model="gemini-3.1-flash-lite",
            prompt_tokens=1500,
            completion_tokens=200,
        )

        # Record Coder call
        tracker.record(
            task_id="quixbugs-python-task_1",
            program_name="task_1",
            attempt=1,
            role="Coder",
            provider="ollama",
            model="qwen2.5-coder:7b",
            prompt_tokens=2000,
            completion_tokens=150,
        )

        # Record Groq Supervisor call
        tracker.record(
            task_id="quixbugs-python-task_1",
            program_name="task_1",
            attempt=1,
            role="Supervisor",
            provider="groq",
            model="qwen/qwen3.8-27b",
            prompt_tokens=2400,
            completion_tokens=300,
        )

        # Verify task breakdown
        bd = tracker.get_task_breakdown("quixbugs-python-task_1")
        self.assertEqual(bd["prompt_tokens"], 1500 + 2000 + 2400)
        self.assertEqual(bd["completion_tokens"], 200 + 150 + 300)
        self.assertEqual(bd["total_tokens"], 5900 + 650)
        self.assertEqual(bd["by_provider"]["groq"]["total"], 2700)
        self.assertEqual(bd["by_provider"]["gemini"]["total"], 1700)
        self.assertEqual(bd["by_provider"]["ollama"]["total"], 2150)

        # Persist to disk
        tracker.persist()
        self.assertTrue(persist_file.exists())

        # Simulate process restart in session 2
        tracker2 = CumulativeTokenTracker(persist_file)
        self.assertEqual(tracker2.session_count, 2)
        self.assertEqual(tracker2.cumulative_by_provider["groq"]["total"], 2700)
        self.assertEqual(tracker2.cumulative_by_provider["gemini"]["total"], 1700)

        # New session tokens start at 0
        self.assertEqual(tracker2.get_session_provider_total("groq"), 0)

        # Record in session 2
        tracker2.record(
            task_id="quixbugs-python-task_2",
            program_name="task_2",
            attempt=1,
            role="Supervisor",
            provider="groq",
            model="qwen/qwen3.8-27b",
            prompt_tokens=1000,
            completion_tokens=100,
        )
        self.assertEqual(tracker2.get_session_provider_total("groq"), 1100)
        self.assertEqual(tracker2.cumulative_by_provider["groq"]["total"], 2700 + 1100)

    def test_rate_limit_header_parsing(self):
        """Test duration parsing and dynamic header throttling."""
        self.assertAlmostEqual(parse_header_duration("250ms"), 0.25)
        self.assertAlmostEqual(parse_header_duration("5s"), 5.0)
        self.assertAlmostEqual(parse_header_duration("1.5s"), 1.5)
        self.assertAlmostEqual(parse_header_duration("1m30s"), 90.0)

        # When remaining tokens are below threshold (e.g. 1500 < 3000)
        headers = {
            "x-ratelimit-remaining-tokens": "1500",
            "x-ratelimit-reset-tokens": "100ms",
        }
        with patch("time.sleep") as mock_sleep:
            slept = handle_rate_limit_headers(headers, default_delay=0.0, min_token_headroom=3000)
            mock_sleep.assert_called_once()
            self.assertGreaterEqual(slept, 0.6)  # 0.1s + 0.5s buffer

        # When retry-after is present
        headers_retry = {"retry-after": "3"}
        with patch("time.sleep") as mock_sleep:
            slept = handle_rate_limit_headers(headers_retry, default_delay=0.0)
            mock_sleep.assert_called_once()
            self.assertGreaterEqual(slept, 3.5)

    def test_daily_budget_ceiling_enforcement(self):
        """Test that runner raises RateLimitQuotaException when daily ceiling is reached."""
        out_dir = self.temp_dir / "out_budget"
        runner = QuixBugsCloudAssistedRunner(
            task_manifest_path=self.manifest_path,
            output_dir=out_dir,
            batch=1,
            max_daily_groq_tokens=5000,
            max_daily_gemini_tokens=2000,
        )

        # Under limit: should not raise
        runner._check_budget_limits("Supervisor", "groq", est_tokens=3000)

        # Record consumption of 4500 Groq tokens
        runner.token_tracker.record(
            "task_1", "task_1", 1, "Supervisor", "groq", "qwen", 4000, 500
        )

        # Next check with est_tokens=1000 would exceed 5000: should raise
        with self.assertRaises(RateLimitQuotaException):
            runner._check_budget_limits("Supervisor", "groq", est_tokens=1000)

    def test_fallback_prevention_guarantee(self):
        """Test that OpenAICompatibleProvider strictly obeys disable_fallback=True on 429."""
        cfg = ModelConfig(
            name="Supervisor",
            model_id="qwen/qwen3.8-27b",
            provider="groq",
            api_key="mock",
            disable_fallback=True,
            max_retries=0,
        )
        prov = OpenAICompatibleProvider(cfg)

        with patch("models.providers.OpenAICompatibleProvider._get_client") as mock_client_factory:
            mock_client = MagicMock()
            mock_client_factory.return_value = mock_client

            err_429 = Exception("429 Rate limit exceeded")
            setattr(err_429, "status_code", 429)
            mock_client.chat.completions.create.side_effect = err_429

            resp = prov.generate("Test prompt")

            # Must fail with RATE_LIMITED
            self.assertEqual(resp.error_category, ErrorCategory.RATE_LIMITED.value)

            # CRITICAL: Verify create was NEVER called with 'openai/gpt-oss-120b'
            for call in mock_client.chat.completions.create.call_args_list:
                call_kwargs = call[1] if len(call) > 1 else {}
                self.assertNotEqual(call_kwargs.get("model"), "openai/gpt-oss-120b")

    def test_offline_resume_skips_completed_tasks(self):
        """End-to-end offline test verifying resume skips valid results and processes new tasks."""
        out_dir = self.temp_dir / "out_resume"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Pre-seed task_1 as already completed
        t1_dir = out_dir / "task_1"
        t1_dir.mkdir(parents=True, exist_ok=True)
        (t1_dir / "candidate_patch.diff").write_text("patch diff", encoding="utf-8")
        (t1_dir / "condition_result.json").write_text(
            json.dumps({
                "condition": "CLOUD_ASSISTED_DDIV",
                "task_id": "quixbugs-python-task_1",
                "program_name": "task_1",
                "resolved": True,
                "attempts_used": 1,
                "max_attempts": 3,
                "total_tokens": 3000,
                "prompt_tokens": 2500,
                "completion_tokens": 500,
                "history": [{"attempt": 1, "resolved": True, "duration_seconds": 10.0}],
            }),
            encoding="utf-8",
        )

        # Mock providers
        mock_loc = MagicMock()
        mock_loc.config.model_id = "gemini-3.1-flash-lite"
        mock_loc.generate.return_value = ProviderResponse(
            raw_text="Fault in line 2", model_id="gemini-3.1-flash-lite", prompt_tokens=100, completion_tokens=20
        )

        mock_sup = MagicMock()
        mock_sup.config.model_id = "qwen/qwen3.8-27b"
        mock_sup.generate.return_value = ProviderResponse(
            raw_text="Supervisor guidance", model_id="qwen/qwen3.8-27b", prompt_tokens=200, completion_tokens=30
        )

        mock_test = MagicMock()
        mock_test.config.model_id = "qwen/qwen3.8-27b"
        mock_test.generate.return_value = ProviderResponse(
            raw_text="Critique", model_id="qwen/qwen3.8-27b", prompt_tokens=150, completion_tokens=25
        )

        mock_code = MagicMock()
        mock_code.config.model_id = "qwen2.5-coder:7b"
        mock_code.generate.return_value = ProviderResponse(
            raw_text='{"reasoning_summary": "fix", "modifications": []}',
            model_id="qwen2.5-coder:7b",
            prompt_tokens=300,
            completion_tokens=40,
        )

        # Run Batch 1 (has task_1 through task_9)
        runner = QuixBugsCloudAssistedRunner(
            task_manifest_path=self.manifest_path,
            output_dir=out_dir,
            batch=1,
            batch_manifest_path=self.batch_manifest_path,
            locator_provider=mock_loc,
            supervisor_provider=mock_sup,
            tester_provider=mock_test,
            coder_provider_instance=mock_code,
            pacing_delay=0.0,
        )

        # Mock adapter methods so tests don't touch actual filesystem quixbugs data
        with patch.object(runner.adapter, "get_task") as mock_get_task, \
             patch.object(runner.adapter, "create_agent_workspace"), \
             patch.object(runner.adapter, "evaluate_patch") as mock_eval:

            mock_task_obj = MagicMock()
            mock_task_obj.program_name = "task_2"
            mock_task_obj.problem_name = "task_2"
            mock_task_obj.task_id = "quixbugs-python-task_2"
            mock_task_obj.target_file = "python_programs/task_2.py"
            mock_get_task.return_value = mock_task_obj

            mock_eval_res = MagicMock()
            mock_eval_res.resolved = True
            mock_eval_res.candidate_patch_applied = True
            mock_eval_res.all_passed = True
            mock_eval_res.evaluation_verdict = "PASSED"
            mock_eval_res.failure_category = "NONE"
            mock_eval_res.failure_summary = ""
            mock_eval.return_value = mock_eval_res

            # Run only task_1 and task_2 for speed
            runner.manifest_tasks = runner.manifest_tasks[0:2]
            summary = runner.run_all()

            # Task 1 must be skipped from checkpoint
            self.assertEqual(summary["skipped_checkpoint_tasks"], 1)
            self.assertEqual(summary["completed_tasks"], 2)
            self.assertIn("task_1", summary["results"])
            self.assertIn("task_2", summary["results"])

            # Verify Locator was called for task_2, but NOT for task_1
            # Locator was called only 1 time total (for task_2)
            self.assertEqual(mock_loc.generate.call_count, 1)

    def test_daily_budget_persists_across_process_restarts_on_same_date(self):
        """Prove that daily token budgets CANNOT reset merely because the process restarts."""
        persist_file = self.temp_dir / "daily_persist_test.json"

        # Session 1: Process runs and consumes 65,000 Groq tokens today
        tracker_s1 = CumulativeTokenTracker(persist_file)
        tracker_s1.record(
            task_id="quixbugs-python-task_1",
            program_name="task_1",
            attempt=1,
            role="Supervisor",
            provider="groq",
            model="qwen/qwen3.8-27b",
            prompt_tokens=60000,
            completion_tokens=5000,
        )
        tracker_s1.persist()

        # Session 2: Process terminates and restarts on the SAME DATE
        # Instantiate runner with max_daily_groq_tokens = 100,000
        out_dir = self.temp_dir / "out_s2"
        out_dir.mkdir(parents=True, exist_ok=True)
        # Copy token persistence to runner's output dir
        shutil.copy(persist_file, out_dir / "cumulative_token_usage.json")

        runner_s2 = QuixBugsCloudAssistedRunner(
            task_manifest_path=self.manifest_path,
            output_dir=out_dir,
            batch=1,
            max_daily_groq_tokens=100000,
        )

        # Verify today's Groq tokens are already 65,000 upon restart
        today_groq = runner_s2.token_tracker.get_daily_provider_total("groq")
        self.assertEqual(today_groq, 65000)

        # Check under ceiling: 65,000 + 20,000 = 85,000 <= 100,000 -> passes
        runner_s2._check_budget_limits("Supervisor", "groq", est_tokens=20000)

        # Check over ceiling: 65,000 + 40,000 = 105,000 > 100,000 -> must raise RateLimitQuotaException
        with self.assertRaises(RateLimitQuotaException) as cm:
            runner_s2._check_budget_limits("Supervisor", "groq", est_tokens=40000)
        self.assertIn("Daily Groq token ceiling exceeded", str(cm.exception))

        # Check different date (simulating tomorrow): usage starts at 0 for that date
        tomorrow_groq = runner_s2.token_tracker.get_daily_provider_total("groq", "2099-01-01")
        self.assertEqual(tomorrow_groq, 0)

    def test_token_conservation_invariants_and_reconciliation(self):
        """Verify mathematical token conservation: prompt + completion == total == by_role == by_provider."""
        persist_file = self.temp_dir / "reconciliation_tokens.json"
        tracker = CumulativeTokenTracker(persist_file)

        # Record multiple calls across roles and providers
        calls = [
            ("quixbugs-python-bitcount", "bitcount", 0, "Locator", "gemini", "gemini-3.1-flash-lite", 1540, 180),
            ("quixbugs-python-bitcount", "bitcount", 1, "Coder", "ollama", "qwen2.5-coder:7b", 2100, 160),
            ("quixbugs-python-bitcount", "bitcount", 1, "Tester", "groq", "qwen/qwen3.8-27b", 1650, 220),
            ("quixbugs-python-bitcount", "bitcount", 1, "Supervisor", "groq", "qwen/qwen3.8-27b", 2300, 310),
            ("quixbugs-python-bitcount", "bitcount", 2, "Coder", "ollama", "qwen2.5-coder:7b", 2250, 175),
            ("quixbugs-python-bitcount", "bitcount", 2, "Tester", "groq", "qwen/qwen3.8-27b", 1700, 240),
            ("quixbugs-python-depth_first_search", "depth_first_search", 0, "Locator", "gemini", "gemini-3.1-flash-lite", 1420, 150),
            ("quixbugs-python-depth_first_search", "depth_first_search", 1, "Coder", "ollama", "qwen2.5-coder:7b", 1950, 140),
        ]

        expected_prompt_sum = sum(c[6] for c in calls)
        expected_compl_sum = sum(c[7] for c in calls)
        expected_total_sum = expected_prompt_sum + expected_compl_sum

        for c in calls:
            tracker.record(c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7])

        # 1. Test Task-Level Breakdown Invariants
        bd = tracker.get_task_breakdown("quixbugs-python-bitcount")
        task_prompt = bd["prompt_tokens"]
        task_compl = bd["completion_tokens"]
        task_total = bd["total_tokens"]

        # Invariant 1: prompt + compl == total
        self.assertEqual(task_prompt + task_compl, task_total)

        # Invariant 2: sum(roles.total) == task_total
        role_total_sum = sum(r["total"] for r in bd["by_role"].values())
        self.assertEqual(role_total_sum, task_total)

        # Invariant 3: sum(providers.total) == task_total
        prov_total_sum = sum(p["total"] for p in bd["by_provider"].values())
        self.assertEqual(prov_total_sum, task_total)

        # Invariant 4: sum(roles.prompt) == task_prompt == sum(providers.prompt)
        self.assertEqual(sum(r["prompt"] for r in bd["by_role"].values()), task_prompt)
        self.assertEqual(sum(p["prompt"] for p in bd["by_provider"].values()), task_prompt)

        # Invariant 5: sum(roles.completion) == task_compl == sum(providers.completion)
        self.assertEqual(sum(r["completion"] for r in bd["by_role"].values()), task_compl)
        self.assertEqual(sum(p["completion"] for p in bd["by_provider"].values()), task_compl)

        # 2. Test Cumulative-Level Invariants
        tracker.persist()
        data = json.loads(persist_file.read_text(encoding="utf-8"))

        grand_total = data["grand_total_tokens"]
        self.assertEqual(grand_total, expected_total_sum)

        prov_grand = sum(p["total"] for p in data["totals_by_provider"].values())
        role_grand = sum(r["total"] for r in data["totals_by_role"].values())
        self.assertEqual(prov_grand, expected_total_sum)
        self.assertEqual(role_grand, expected_total_sum)

    def test_multi_restart_quota_exhaustion_preservation(self):
        """Test that quota halt cleanly preserves completed tasks across restarts without corruption."""
        out_dir = self.temp_dir / "out_quota_restart"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Setup mock locator that triggers RATE_LIMITED on 2nd task
        mock_loc = MagicMock()
        mock_loc.config.model_id = "gemini-3.1-flash-lite"

        call_idx = 0
        def fake_generate(prompt, **kwargs):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return ProviderResponse(
                    raw_text="Fault in line 1", model_id="gemini-3.1-flash-lite", prompt_tokens=100, completion_tokens=20
                )
            else:
                return ProviderResponse(
                    raw_text="", model_id="gemini-3.1-flash-lite", error="429 Too Many Requests", error_category="RATE_LIMITED"
                )

        mock_loc.generate.side_effect = fake_generate

        mock_sup = MagicMock()
        mock_sup.config.model_id = "qwen/qwen3.8-27b"
        mock_test = MagicMock()
        mock_test.config.model_id = "qwen/qwen3.8-27b"
        mock_code = MagicMock()
        mock_code.config.model_id = "qwen2.5-coder:7b"
        mock_code.generate.return_value = ProviderResponse(
            raw_text='{"reasoning_summary": "fix", "modifications": []}',
            model_id="qwen2.5-coder:7b",
            prompt_tokens=200,
            completion_tokens=30,
        )

        runner = QuixBugsCloudAssistedRunner(
            task_manifest_path=self.manifest_path,
            output_dir=out_dir,
            batch=1,
            batch_manifest_path=self.batch_manifest_path,
            locator_provider=mock_loc,
            supervisor_provider=mock_sup,
            tester_provider=mock_test,
            coder_provider_instance=mock_code,
            pacing_delay=0.0,
        )

        with patch.object(runner.adapter, "get_task") as mock_get_task, \
             patch.object(runner.adapter, "create_agent_workspace"), \
             patch.object(runner.adapter, "evaluate_patch") as mock_eval:

            def get_fake_task(tid):
                m = MagicMock()
                m.task_id = tid
                m.program_name = tid.replace("quixbugs-python-", "")
                m.problem_name = m.program_name
                m.target_file = f"python_programs/{m.program_name}.py"
                return m

            mock_get_task.side_effect = get_fake_task

            mock_eval_res = MagicMock()
            mock_eval_res.resolved = True
            mock_eval_res.candidate_patch_applied = True
            mock_eval_res.all_passed = True
            mock_eval_res.evaluation_verdict = "PASSED"
            mock_eval_res.failure_category = "NONE"
            mock_eval.return_value = mock_eval_res

            # Run with task_1 and task_2
            runner.manifest_tasks = runner.manifest_tasks[0:2]
            summary = runner.run_all()

            # First task succeeded; second task halted due to rate limit
            self.assertEqual(summary["status"], "STOPPED_QUOTA_EXHAUSTED")
            self.assertEqual(summary["completed_tasks"], 1)
            self.assertIn("task_1", summary["results"])
            self.assertNotIn("task_2", summary["results"])

            # Verify no partial or corrupt result was written for task_2
            t2_result_file = out_dir / "task_2" / "condition_result.json"
            self.assertFalse(t2_result_file.exists())


if __name__ == "__main__":
    unittest.main()

