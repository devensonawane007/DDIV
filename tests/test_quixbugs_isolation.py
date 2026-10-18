"""Comprehensive Ground-Truth Isolation and Leakage Tests for QuixBugs Integration.

Tests:
1. Synthetic canary oracle secrets embedded in fixtures are 100% absent from agent workspaces.
2. All 40 real QuixBugs tasks create clean agent workspaces containing ONLY buggy source code.
3. Path traversal (../../), absolute paths, and external symlinks are strictly blocked by context builder.
4. Model-facing agents (Coder, Locator, Tester, Supervisor) have zero shell or file-read tools.
5. Evaluator diagnostics, sanitized tracebacks, and failure summaries redact expected oracle literals.
6. Evaluator imports candidate workspace code, not original repository or reference implementations.
7. Malicious candidate patches attempting file I/O, subprocess, or unauthorized paths fail closed.
8. Workspace creation fails closed and purges directory if any test or oracle asset is detected.
9. Memory sanitization strips reference tokens and prevents oracle leaks into prompts.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
import pytest

from core.experiment_worker import sanitize_text, sanitize_memory_record
from memory.schemas import MemoryRecord
from agents.base import BaseAgent
from agents.coder import CoderAgent
from agents.locator import LocatorAgent
from agents.tester import TesterAgent
TesterAgent.__test__ = False
from agents.supervisor import SupervisorAgent
from evaluation.context_builder import TargetedContextBuilder
from evaluation.quixbugs_adapter import (
    QuixBugsAdapter,
    QuixBugsTask,
    QuixBugsEvaluationResult,
    QuixBugsBaselineResult,
    sanitize_evaluator_output,
    validate_patch_security,
    GRAPH_BASED_ALGORITHMS,
    PROTECTED_REFERENCE_DIRS,
)


CANARY_ORACLE_SECRET = "SYNTHETIC_ORACLE_CANARY_VALUE_987654321"
CANARY_INPUT_SECRET = "SYNTHETIC_INPUT_CANARY_ARG_123456789"


@pytest.fixture
def synthetic_secret_quixbugs(tmp_path: Path) -> Path:
    """Create a synthetic QuixBugs repo containing synthetic canary secrets in test and JSON files."""
    qb = tmp_path / "quixbugs_canary"
    (qb / "python_programs").mkdir(parents=True)
    (qb / "python_testcases").mkdir(parents=True)
    (qb / "json_testcases").mkdir(parents=True)
    (qb / "correct_python_programs").mkdir(parents=True)

    # Buggy program: algo_secret
    prog = qb / "python_programs/algo_secret.py"
    prog.write_text("def algo_secret(x):\n    return 'wrong_output'\n", encoding="utf-8")

    # Correct reference program: algo_secret (MUST BE PROTECTED)
    cprog = qb / "correct_python_programs/algo_secret.py"
    cprog.write_text(f"def algo_secret(x):\n    return '{CANARY_ORACLE_SECRET}'\n", encoding="utf-8")

    # JSON testcases containing canary secrets
    json_file = qb / "json_testcases/algo_secret.json"
    json_file.write_text(
        f'[["{CANARY_INPUT_SECRET}"], "{CANARY_ORACLE_SECRET}"]\n',
        encoding="utf-8",
    )

    # Test file importing from json or testing assertion against canary secret
    test_file = qb / "python_testcases/test_algo_secret.py"
    test_file.write_text(
        "import pytest\n"
        "from python_programs.algo_secret import algo_secret\n\n"
        "def test_canary_oracle():\n"
        f"    expected = '{CANARY_ORACLE_SECRET}'\n"
        f"    assert algo_secret('{CANARY_INPUT_SECRET}') == expected\n",
        encoding="utf-8",
    )

    (qb / "conftest.py").write_text("# synthetic conftest\n", encoding="utf-8")
    return qb


class TestQuixBugsIsolation:
    """Rigorous test suite verifying ground-truth isolation across all boundaries."""

    def test_01_synthetic_oracle_secret_absence_from_agent_workspace(self, synthetic_secret_quixbugs: Path, tmp_path: Path):
        """Verify that synthetic canary secrets in testcases/JSON are completely absent from agent workspace."""
        adapter = QuixBugsAdapter(quixbugs_root=synthetic_secret_quixbugs)
        ws_dir = tmp_path / "agent_ws_secret"

        adapter.create_agent_workspace("quixbugs-python-algo_secret", ws_dir, init_git=True)

        # 1. Target file must exist
        target = ws_dir / "python_programs/algo_secret.py"
        assert target.is_file()

        # 2. Exhaustive scan of every file and directory in agent workspace
        for root, dirs, files in os.walk(ws_dir):
            for d in dirs:
                # No test, json, or reference directories
                assert "test" not in d.lower(), f"Forbidden directory '{d}' found in agent workspace!"
                assert "correct" not in d.lower(), f"Forbidden directory '{d}' found in agent workspace!"

            for f in files:
                assert not f.endswith(".json"), f"Forbidden JSON test fixture '{f}' found in agent workspace!"
                assert "test" not in f.lower(), f"Forbidden test file '{f}' found in agent workspace!"
                assert "correct" not in f.lower(), f"Forbidden reference file '{f}' found in agent workspace!"

                # Check file contents for canary secrets
                f_path = Path(root) / f
                content = f_path.read_text(encoding="utf-8", errors="replace")
                assert CANARY_ORACLE_SECRET not in content, f"LEAKAGE: Canary oracle secret found in {f}!"
                assert CANARY_INPUT_SECRET not in content, f"LEAKAGE: Canary input secret found in {f}!"

    def test_02_all_40_real_quixbugs_agent_workspaces_are_oracle_free(self, tmp_path: Path):
        """Verify that creating agent workspaces for all 40 real QuixBugs tasks produces strictly isolated workspaces."""
        adapter = QuixBugsAdapter(quixbugs_root="D:/DDIV/data/quixbugs")
        if not adapter.is_available():
            pytest.skip("QuixBugs dataset not available at D:/DDIV/data/quixbugs")

        tasks = adapter.discover_tasks()
        assert len(tasks) == 40

        for task in tasks:
            ws_dir = tmp_path / f"agent_ws_{task.program_name}"
            adapter.create_agent_workspace(task.task_id, ws_dir, init_git=False)

            # Workspace must contain ONLY python_programs/<prog>.py (+ node.py if graph)
            expected_files = {f"python_programs/{task.program_name}.py"}
            if task.result_metadata.get("is_graph_based"):
                expected_files.add("python_programs/node.py")

            found_files = set()
            for root, dirs, files in os.walk(ws_dir):
                for f in files:
                    rel_p = str((Path(root) / f).relative_to(ws_dir)).replace("\\", "/")
                    found_files.add(rel_p)

            assert found_files == expected_files, (
                f"Task '{task.task_id}' workspace contains unexpected files: {found_files - expected_files}"
            )

            # Ensure zero test files, zero JSON files, zero reference files
            assert not (ws_dir / "python_testcases").exists()
            assert not (ws_dir / "json_testcases").exists()
            assert not (ws_dir / "correct_python_programs").exists()
            assert not (ws_dir / "conftest.py").exists()

    def test_03_path_traversal_and_symlink_defense_in_context_builder(self, synthetic_secret_quixbugs: Path, tmp_path: Path):
        """Verify that context builder blocks ../ path traversal, absolute paths, and external symlinks."""
        adapter = QuixBugsAdapter(quixbugs_root=synthetic_secret_quixbugs)
        ws_dir = tmp_path / "ws_traversal_test"
        adapter.create_agent_workspace("quixbugs-python-algo_secret", ws_dir, init_git=False)

        # 1. Attempt relative path traversal pointing to json_testcases
        traversal_path = "../../quixbugs_canary/json_testcases/algo_secret.json"
        # 2. Attempt absolute path pointing to test file
        abs_path = str((synthetic_secret_quixbugs / "python_testcases/test_algo_secret.py").resolve())
        # 3. Create a malicious symlink inside workspace pointing to external secret
        link_path = ws_dir / "python_programs/link_to_secret.py"
        try:
            link_path.symlink_to(synthetic_secret_quixbugs / "correct_python_programs/algo_secret.py")
        except (OSError, NotImplementedError):
            pass

        builder = TargetedContextBuilder(char_budget=10000)
        located_files = [
            traversal_path,
            abs_path,
            "python_programs/link_to_secret.py",
            "python_programs/algo_secret.py",
        ]

        ctx = builder.build_context(ws_dir, located_files)

        assert CANARY_ORACLE_SECRET not in ctx.formatted_source_code, "LEAKAGE: Canary oracle secret leaked via traversal!"
        assert CANARY_INPUT_SECRET not in ctx.formatted_source_code, "LEAKAGE: Canary input secret leaked via traversal!"
        assert CANARY_ORACLE_SECRET not in ctx.formatted_tests_context, "LEAKAGE: Canary oracle leaked in test context!"
        assert "algo_secret" in ctx.formatted_source_code

    def test_04_model_facing_agent_permissions_audit(self):
        """Verify that DDIV agents (Coder, Locator, Tester, Supervisor) have NO shell or file tools."""
        for agent_cls in (CoderAgent, LocatorAgent, TesterAgent, SupervisorAgent):
            assert issubclass(agent_cls, BaseAgent)
            assert not hasattr(agent_cls, "tools")
            assert not hasattr(agent_cls, "run_command")
            assert not hasattr(agent_cls, "execute_shell")
            assert not hasattr(agent_cls, "read_file")

    def test_05_logs_and_recovery_diagnostics_sanitization_no_oracle_leak(self, synthetic_secret_quixbugs: Path, tmp_path: Path):
        """Verify that raw pytest assertion values and expected answers are sanitized before returning to agent."""
        adapter = QuixBugsAdapter(quixbugs_root=synthetic_secret_quixbugs)
        ws_dir = tmp_path / "ws_diag_test"
        adapter.create_agent_workspace("quixbugs-python-algo_secret", ws_dir, init_git=True)
        task = adapter.get_task("quixbugs-python-algo_secret")

        noop_patch = (
            "--- a/python_programs/algo_secret.py\n"
            "+++ b/python_programs/algo_secret.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+# no-op comment\n"
            " def algo_secret(x):\n"
            "     return 'wrong_output'\n"
        )

        res = adapter.evaluate_patch(ws_dir, task, noop_patch)

        assert not res.resolved
        assert res.failure_category == "ASSERTION_FAILURE"
        assert CANARY_ORACLE_SECRET not in res.sanitized_stdout, "LEAKAGE: Canary oracle found in sanitized_stdout!"
        assert CANARY_ORACLE_SECRET not in res.sanitized_stderr, "LEAKAGE: Canary oracle found in sanitized_stderr!"
        assert CANARY_ORACLE_SECRET not in res.failure_summary, "LEAKAGE: Canary oracle found in failure_summary!"
        assert "AssertionError" in res.sanitized_stdout
        assert "ORACLE_REDACTED" in res.sanitized_stdout
        assert res.oracle_redacted is True

    def test_06_evaluator_imports_candidate_code_not_repository_or_gold(self, synthetic_secret_quixbugs: Path, tmp_path: Path):
        """Verify that evaluation imports code from candidate workspace, not the upstream repo or reference dir."""
        adapter = QuixBugsAdapter(quixbugs_root=synthetic_secret_quixbugs)
        ws_dir = tmp_path / "ws_candidate_exec"
        adapter.create_agent_workspace("quixbugs-python-algo_secret", ws_dir, init_git=True)
        task = adapter.get_task("quixbugs-python-algo_secret")

        solution_patch = (
            "--- a/python_programs/algo_secret.py\n"
            "+++ b/python_programs/algo_secret.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def algo_secret(x):\n"
            "-    return 'wrong_output'\n"
            f"+    return '{CANARY_ORACLE_SECRET}'\n"
        )

        res = adapter.evaluate_patch(ws_dir, task, solution_patch)
        assert res.candidate_patch_applied
        assert res.resolved is True
        assert res.all_passed is True
        assert res.evaluation_verdict == "RESOLVED"

    def test_07_malicious_patch_security_gate_fails_closed(self, synthetic_secret_quixbugs: Path, tmp_path: Path):
        """Verify that patches attempting file I/O, subprocess, or editing non-target files are rejected."""
        adapter = QuixBugsAdapter(quixbugs_root=synthetic_secret_quixbugs)
        ws_dir = tmp_path / "ws_sec_test"
        adapter.create_agent_workspace("quixbugs-python-algo_secret", ws_dir, init_git=True)
        task = adapter.get_task("quixbugs-python-algo_secret")

        # 1. Patch attempting to edit an unauthorized test file
        patch_bad_file = (
            "--- a/python_testcases/test_algo_secret.py\n"
            "+++ b/python_testcases/test_algo_secret.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-# something\n"
            "+def test_canary(): assert True\n"
        )
        res1 = adapter.evaluate_patch(ws_dir, task, patch_bad_file)
        assert not res1.candidate_patch_applied
        assert res1.failure_category == "SECURITY_VIOLATION"

        # 2. Patch attempting file I/O to read external JSON
        patch_file_io = (
            "--- a/python_programs/algo_secret.py\n"
            "+++ b/python_programs/algo_secret.py\n"
            "@@ -1,2 +1,3 @@\n"
            " def algo_secret(x):\n"
            "+    data = open('json_testcases/algo_secret.json').read()\n"
            "     return 'wrong_output'\n"
        )
        res2 = adapter.evaluate_patch(ws_dir, task, patch_file_io)
        assert not res2.candidate_patch_applied
        assert res2.failure_category == "SECURITY_VIOLATION"

        # 3. Patch attempting subprocess execution
        patch_subprocess = (
            "--- a/python_programs/algo_secret.py\n"
            "+++ b/python_programs/algo_secret.py\n"
            "@@ -1,2 +1,3 @@\n"
            " def algo_secret(x):\n"
            "+    import subprocess; subprocess.run(['cat', 'secret'])\n"
            "     return 'wrong_output'\n"
        )
        res3 = adapter.evaluate_patch(ws_dir, task, patch_subprocess)
        assert not res3.candidate_patch_applied
        assert res3.failure_category == "SECURITY_VIOLATION"

    def test_08_fail_closed_gate_on_workspace_contamination(self, synthetic_secret_quixbugs: Path, tmp_path: Path, monkeypatch):
        """Verify that workspace creation fails closed and purges the workspace if contamination occurs."""
        adapter = QuixBugsAdapter(quixbugs_root=synthetic_secret_quixbugs)
        ws_dir = tmp_path / "ws_contam_test"

        orig_copy = shutil.copy2

        def malicious_copy(src, dst):
            orig_copy(src, dst)
            corrupted = Path(dst).parent.parent / "python_testcases"
            corrupted.mkdir(parents=True, exist_ok=True)
            (corrupted / "leaked_test.py").write_text("leaked", encoding="utf-8")

        monkeypatch.setattr(shutil, "copy2", malicious_copy)

        with pytest.raises(RuntimeError, match="CRITICAL ISOLATION BREACH"):
            adapter.create_agent_workspace("quixbugs-python-algo_secret", ws_dir, init_git=False)

        assert not (ws_dir / "python_testcases").exists()

    def test_09_memory_sanitization_strips_reference_tokens(self):
        """Verify that memory sanitization and text sanitization strip benchmark reference tokens."""
        raw_text = "Retrieved gold_patch and test_patch for FAIL_TO_PASS condition PASS_TO_PASS"
        cleaned = sanitize_text(raw_text)
        assert "gold_patch" not in cleaned
        assert "test_patch" not in cleaned
        assert "FAIL_TO_PASS" not in cleaned
        assert "[REDACTED_REF]" in cleaned

        rec = MemoryRecord(
            task_id="test_task",
            repository="test_repo",
            issue_summary="test issue with gold_patch",
            result="FAILED",
            diagnosis="fault found in test_patch",
            failure_evidence=["Evidence: FAIL_TO_PASS failed"],
            failed_tests=["test_foo PASS_TO_PASS"],
            metadata={"gold_patch_ref": "secret", "safe_meta": "allowed"},
        )
        cleaned_rec = sanitize_memory_record(rec)
        assert "gold_patch" not in cleaned_rec.issue_summary
        assert "test_patch" not in cleaned_rec.diagnosis
        assert "FAIL_TO_PASS" not in cleaned_rec.failure_evidence[0]
        assert "gold_patch_ref" not in cleaned_rec.metadata
        assert cleaned_rec.metadata["safe_meta"] == "allowed"
