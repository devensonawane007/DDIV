"""SWE-bench evaluation infrastructure with formal distinction between official harness and internal targeted evaluator."""

from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from evaluation.command_runner import CommandResult, CommandRunner
from evaluation.patch_manager import PatchManager, PatchValidationResult
from evaluation.swebench_loader import SWEBenchRecord
from evaluation.workspace import TaskWorkspace


class OfficialHarnessStatus(BaseModel):
    """Diagnostic outcome of official SWE-bench evaluation harness availability."""

    available: bool
    docker_available: bool
    swebench_package_available: bool
    status: str  # "AVAILABLE" or "UNAVAILABLE"
    details: str


class OfficialHarnessChecker:
    """Probes the host environment for the authoritative SWE-bench evaluation harness."""

    def __init__(self, command_runner: Optional[CommandRunner] = None):
        self.runner = command_runner or CommandRunner()

    def check_harness_availability(self) -> OfficialHarnessStatus:
        """Probe for Docker daemon and the official 'swebench' Python package."""
        # 1. Check docker CLI and daemon
        docker_bin = shutil.which("docker")
        docker_ok = False
        if docker_bin:
            try:
                res = self.runner.run(["docker", "info"], cwd=".", timeout=5)
                docker_ok = res.is_success
            except Exception:
                docker_ok = False

        # 2. Check swebench package
        swebench_ok = False
        try:
            import importlib.util
            spec = importlib.util.find_spec("swebench")
            swebench_ok = spec is not None
        except Exception:
            swebench_ok = False

        if docker_ok and swebench_ok:
            return OfficialHarnessStatus(
                available=True,
                docker_available=True,
                swebench_package_available=True,
                status="AVAILABLE",
                details="Official swebench harness and Docker daemon are ready.",
            )

        missing = []
        if not swebench_ok:
            missing.append("'swebench' python package not installed")
        if not docker_ok:
            missing.append("Docker daemon unreachable or not installed")

        return OfficialHarnessStatus(
            available=False,
            docker_available=docker_ok,
            swebench_package_available=swebench_ok,
            status="UNAVAILABLE",
            details=f"Official harness cannot run: {'; '.join(missing)}.",
        )


class CleanBaseHealthResult(BaseModel):
    """Result of running sanity checks on the pristine base checkout before attempts start."""

    task_id: str
    clean_base_passed: bool = True
    tested_p2p_tests: List[str] = Field(default_factory=list)
    failed_p2p_tests: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    raw_output: str = ""
    duration_seconds: float = 0.0


class InternalEvaluationResult(BaseModel):
    """Observation outcome of evaluator-side verification on a clean evaluation workspace."""

    task_id: str
    candidate_patch_applied: bool
    candidate_patch_error: Optional[str] = None
    test_patch_applied: bool
    test_patch_error: Optional[str] = None
    fail_to_pass_results: Dict[str, bool] = Field(default_factory=dict)
    pass_to_pass_results: Dict[str, bool] = Field(default_factory=dict)
    all_f2p_passed: bool = False
    all_p2p_passed: bool = False
    internal_resolved: bool = False
    evaluation_verdict: str = "UNRESOLVED_INTERNALLY"  # "RESOLVED_INTERNALLY" or "UNRESOLVED_INTERNALLY"
    duration_seconds: float = 0.0
    raw_stdout: str = ""
    raw_stderr: str = ""
    exit_code: int = 0
    # Structured Failure Evidence
    failed_f2p_tests: List[str] = Field(default_factory=list)
    failed_p2p_tests: List[str] = Field(default_factory=list)
    failure_type: str = "UNKNOWN"
    failure_summary: str = ""
    traceback: str = ""
    likely_files: List[str] = Field(default_factory=list)
    likely_symbols: List[str] = Field(default_factory=list)
    clean_base_passed: bool = True
    clean_base_error: Optional[str] = None


class InternalSWEBenchEvaluator:
    """Evaluates candidate patches against ground truth in a pristine evaluation workspace.
    
    NOTE: This is the internal research evaluator for fast and offline feedback.
    The authoritative benchmark evaluation must come from the official SWE-bench harness.
    """

    def __init__(self, patch_manager: Optional[PatchManager] = None, command_runner: Optional[CommandRunner] = None):
        self.patch_mgr = patch_manager or PatchManager()
        self.runner = command_runner or CommandRunner()

    def _resolve_test_target(self, test_name: str, test_patch: str, workspace_path: Path) -> str:
        """Resolve short test names (e.g. test_homomorphism) to full node IDs if needed."""
        if "/" in test_name or "\\" in test_name or test_name.endswith(".py"):
            return test_name

        test_files = []
        if test_patch:
            for line in test_patch.splitlines():
                if line.startswith("diff --git a/") or line.startswith("--- a/"):
                    parts = line.split()
                    if len(parts) >= 2:
                        p = parts[1].replace("a/", "").strip()
                        if p.endswith(".py") and p not in test_files:
                            test_files.append(p)

        for tf in test_files:
            fpath = workspace_path / tf
            if fpath.exists():
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    if test_name in content:
                        return f"{tf}::{test_name}"
                except Exception:
                    pass

        for p in workspace_path.glob("**/test_*.py"):
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                if test_name in content:
                    rel = str(p.relative_to(workspace_path)).replace("\\", "/")
                    return f"{rel}::{test_name}"
            except Exception:
                pass

        return test_name

    def evaluate_candidate_patch(
        self,
        workspace: TaskWorkspace,
        record: SWEBenchRecord,
        candidate_patch: str,
        max_p2p_tests: int = 10,
        timeout: int = 180,
        clean_base_passed: bool = True,
        clean_base_error: Optional[str] = None,
    ) -> InternalEvaluationResult:
        """Execute ground-truth verification on a pristine evaluation workspace."""
        start_time = time.time()
        task_id = record.task.instance_id

        # 1. Apply Candidate Patch to Clean Workspace
        cand_apply_res = self.patch_mgr.apply_patch(workspace.path, candidate_patch)
        if not cand_apply_res.is_success:
            return InternalEvaluationResult(
                task_id=task_id,
                candidate_patch_applied=False,
                candidate_patch_error=cand_apply_res.stderr or cand_apply_res.stdout,
                test_patch_applied=False,
                duration_seconds=time.time() - start_time,
                raw_stderr=cand_apply_res.stderr,
                raw_stdout=cand_apply_res.stdout,
                exit_code=cand_apply_res.exit_code,
                evaluation_verdict="UNRESOLVED_INTERNALLY (Candidate patch application failed)",
                clean_base_passed=clean_base_passed,
                clean_base_error=clean_base_error,
            )

        # 2. Apply Evaluator Ground-Truth Test Patch
        test_patch = record.ground_truth.test_patch
        if test_patch and test_patch.strip():
            tp_res = self.patch_mgr.apply_patch(workspace.path, test_patch)
            if not tp_res.is_success:
                return InternalEvaluationResult(
                    task_id=task_id,
                    candidate_patch_applied=True,
                    test_patch_applied=False,
                    test_patch_error=tp_res.stderr or tp_res.stdout,
                    duration_seconds=time.time() - start_time,
                    raw_stderr=tp_res.stderr,
                    raw_stdout=tp_res.stdout,
                    exit_code=tp_res.exit_code,
                    evaluation_verdict="UNRESOLVED_INTERNALLY (Test patch application failed)",
                    clean_base_passed=clean_base_passed,
                    clean_base_error=clean_base_error,
                )
            test_patch_applied = True
        else:
            test_patch_applied = True

        # 3. Determine Test Runner Command
        has_pytest = False
        try:
            import importlib.util
            has_pytest = importlib.util.find_spec("pytest") is not None
        except Exception:
            has_pytest = bool(shutil.which("pytest"))

        base_cmd = [sys.executable, "-m", "pytest", "-v"] if has_pytest else [sys.executable, "-m", "unittest", "-v"]

        # 4. Execute FAIL_TO_PASS test cases
        f2p_tests = record.ground_truth.fail_to_pass
        f2p_results: Dict[str, bool] = {}
        combined_stdout = []
        combined_stderr = []
        last_exit = 0

        for test_name in f2p_tests:
            resolved_target = self._resolve_test_target(test_name, test_patch, workspace.path)
            if has_pytest:
                cmd = base_cmd + [resolved_target]
            else:
                dot_test = resolved_target.replace(".py", "").replace("/", ".").replace("\\", ".").replace("::", ".")
                cmd = base_cmd + [dot_test]
            cmd_res = self.runner.run(cmd=cmd, cwd=workspace.path, timeout=timeout)
            combined_stdout.append(f"--- F2P: {test_name} ({resolved_target}) ---\n{cmd_res.stdout}")
            if cmd_res.stderr:
                combined_stderr.append(cmd_res.stderr)
            last_exit = cmd_res.exit_code

            # Determine pass/fail
            passed = cmd_res.is_success and "PASSED" in cmd_res.stdout and "FAILED" not in cmd_res.stdout
            if not has_pytest:
                passed = cmd_res.is_success and "OK" in (cmd_res.stdout + cmd_res.stderr)
            f2p_results[test_name] = passed

        # 5. Execute PASS_TO_PASS regression test cases (subset to avoid timeout)
        p2p_tests = record.ground_truth.pass_to_pass[:max_p2p_tests]
        p2p_results: Dict[str, bool] = {}

        for test_name in p2p_tests:
            resolved_target = self._resolve_test_target(test_name, test_patch, workspace.path)
            if has_pytest:
                cmd = base_cmd + [resolved_target]
            else:
                dot_test = resolved_target.replace(".py", "").replace("/", ".").replace("\\", ".").replace("::", ".")
                cmd = base_cmd + [dot_test]
            cmd_res = self.runner.run(cmd=cmd, cwd=workspace.path, timeout=timeout)
            combined_stdout.append(f"--- P2P: {test_name} ---\n{cmd_res.stdout}")
            if cmd_res.stderr:
                combined_stderr.append(cmd_res.stderr)
            last_exit = max(last_exit, cmd_res.exit_code)

            passed = cmd_res.is_success and "PASSED" in cmd_res.stdout and "FAILED" not in cmd_res.stdout
            if not has_pytest:
                passed = cmd_res.is_success and "OK" in (cmd_res.stdout + cmd_res.stderr)
            p2p_results[test_name] = passed

        all_f2p = len(f2p_results) > 0 and all(f2p_results.values())
        all_p2p = len(p2p_results) == 0 or all(p2p_results.values())
        resolved = all_f2p and all_p2p

        failed_f2p = [t for t, p in f2p_results.items() if not p]
        failed_p2p = [t for t, p in p2p_results.items() if not p]

        raw_out = "\n".join(combined_stdout)
        raw_err = "\n".join(combined_stderr)
        tb, likely_f, likely_s = self._extract_traceback_and_symbols(raw_out, raw_err)

        if resolved:
            f_type = "NONE"
            f_summary = "All FAIL_TO_PASS and PASS_TO_PASS tests verified successfully."
        elif not clean_base_passed and failed_p2p:
            f_type = "ENVIRONMENT_FAILURE"
            f_summary = f"Pre-existing test failure on clean base: {failed_p2p}"
        elif failed_f2p and failed_p2p:
            f_type = "F2P_FAILURE_AND_P2P_REGRESSION"
            f_summary = f"FAIL_TO_PASS tests failed ({len(failed_f2p)}) and PASS_TO_PASS regressed ({len(failed_p2p)})."
        elif failed_f2p:
            f_type = "F2P_FAILURE"
            f_summary = f"FAIL_TO_PASS tests failed: {failed_f2p}."
        elif failed_p2p:
            f_type = "P2P_REGRESSION"
            f_summary = f"PASS_TO_PASS regression detected: {failed_p2p}."
        else:
            f_type = "TEST_INFRASTRUCTURE_FAILURE"
            f_summary = "Test execution terminated with non-zero status without recognized test outcomes."

        verdict = "RESOLVED_INTERNALLY" if resolved else "UNRESOLVED_INTERNALLY"
        if not all_f2p:
            verdict += " (FAIL_TO_PASS tests failed)"
        elif not all_p2p:
            verdict += " (PASS_TO_PASS regression detected)"

        duration = time.time() - start_time
        return InternalEvaluationResult(
            task_id=task_id,
            candidate_patch_applied=True,
            test_patch_applied=test_patch_applied,
            fail_to_pass_results=f2p_results,
            pass_to_pass_results=p2p_results,
            all_f2p_passed=all_f2p,
            all_p2p_passed=all_p2p,
            internal_resolved=resolved,
            evaluation_verdict=verdict,
            duration_seconds=duration,
            raw_stdout=raw_out,
            raw_stderr=raw_err,
            exit_code=0 if resolved else 1,
            failed_f2p_tests=failed_f2p,
            failed_p2p_tests=failed_p2p,
            failure_type=f_type,
            failure_summary=f_summary,
            traceback=tb,
            likely_files=likely_f,
            likely_symbols=likely_s,
            clean_base_passed=clean_base_passed,
            clean_base_error=clean_base_error,
        )

    def _extract_traceback_and_symbols(self, stdout: str, stderr: str) -> tuple[str, list[str], list[str]]:
        """Extract traceback snippet, referenced files, and symbols from test run output."""
        full_text = stdout + "\n" + stderr
        traceback_lines: list[str] = []
        files: list[str] = []
        symbols: list[str] = []

        in_tb = False
        for line in full_text.splitlines():
            if "Traceback (most recent call last):" in line:
                in_tb = True
                traceback_lines.append(line)
            elif in_tb:
                traceback_lines.append(line)
                if line and not line.startswith(" ") and not line.startswith("\t"):
                    in_tb = False

        tb_text = "\n".join(traceback_lines[:60])

        for m in re.finditer(r'File "([^"]+\.py)", line \d+(?:, in (\w+))?', full_text):
            fpath = m.group(1).replace("\\", "/")
            if "/test_" not in fpath and not fpath.startswith("tests/"):
                if fpath not in files:
                    files.append(fpath)
            sym = m.group(2)
            if sym and sym not in symbols and not sym.startswith("<"):
                symbols.append(sym)

        return tb_text, files[:5], symbols[:5]

    def check_clean_base_health(
        self,
        workspace: TaskWorkspace,
        record: SWEBenchRecord,
        max_p2p_tests: int = 5,
        timeout: int = 60,
    ) -> CleanBaseHealthResult:
        """Run PASS_TO_PASS sanity checks on the pristine base checkout before attempts start."""
        start_time = time.time()
        task_id = record.task.instance_id

        # 1. Apply test patch if present to expose the test cases
        test_patch = record.ground_truth.test_patch
        if test_patch and test_patch.strip():
            tp_res = self.patch_mgr.apply_patch(workspace.path, test_patch)
            if not tp_res.is_success:
                self.patch_mgr.revert_workspace(workspace.path)
                return CleanBaseHealthResult(
                    task_id=task_id,
                    clean_base_passed=False,
                    error_message=f"Test patch failed to apply to clean base: {tp_res.stderr or tp_res.stdout}",
                    duration_seconds=time.time() - start_time,
                )

        # 2. Determine Test Runner Command
        has_pytest = False
        try:
            import importlib.util
            has_pytest = importlib.util.find_spec("pytest") is not None
        except Exception:
            has_pytest = bool(shutil.which("pytest"))

        base_cmd = [sys.executable, "-m", "pytest", "-v"] if has_pytest else [sys.executable, "-m", "unittest", "-v"]

        # 3. Run a subset of PASS_TO_PASS tests on pristine base
        p2p_tests = record.ground_truth.pass_to_pass[:max_p2p_tests]
        failed_tests: list[str] = []
        combined_output: list[str] = []

        for test_name in p2p_tests:
            resolved_target = self._resolve_test_target(test_name, test_patch, workspace.path)
            if has_pytest:
                cmd = base_cmd + [resolved_target]
            else:
                dot_test = resolved_target.replace(".py", "").replace("/", ".").replace("\\", ".").replace("::", ".")
                cmd = base_cmd + [dot_test]
            cmd_res = self.runner.run(cmd=cmd, cwd=workspace.path, timeout=timeout)
            combined_output.append(cmd_res.stdout)
            passed = cmd_res.is_success and "PASSED" in cmd_res.stdout and "FAILED" not in cmd_res.stdout
            if not has_pytest:
                passed = cmd_res.is_success and "OK" in (cmd_res.stdout + cmd_res.stderr)
            if not passed:
                failed_tests.append(test_name)

        # 4. Clean up workspace back to pristine HEAD
        self.patch_mgr.revert_workspace(workspace.path)

        clean_passed = len(failed_tests) == 0
        return CleanBaseHealthResult(
            task_id=task_id,
            clean_base_passed=clean_passed,
            tested_p2p_tests=p2p_tests,
            failed_p2p_tests=failed_tests,
            error_message=f"Pre-existing test failures on clean base: {failed_tests}" if not clean_passed else None,
            raw_output="\n".join(combined_output[:3]),
            duration_seconds=time.time() - start_time,
        )
