"""Test execution, verification, and environment diagnostics for SWE-bench tasks."""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from evaluation.command_runner import CommandResult, CommandRunner
from evaluation.swebench_loader import SWEBenchTask
from evaluation.workspace import TaskWorkspace


class EnvironmentStatus(BaseModel):
    """Diagnostic outcome of the repository execution environment."""

    ready: bool
    docker_available: bool
    status: str  # "READY", "BLOCKED", "INFRASTRUCTURE_BLOCKED"
    details: str


class TestExecutionResult(BaseModel):
    """Structured test outcome captured from the test runner."""

    passed: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    error_tests: int = 0
    failures: List[str] = Field(default_factory=list)
    raw_stdout: str = ""
    raw_stderr: str = ""
    exit_code: int = 0
    duration_seconds: float = 0.0
    status_label: str = ""  # "PASS", "FAIL", "BLOCKED"


class SWEBenchRunner:
    """Executes verification tests in the workspace and extracts structured test outcomes."""

    def __init__(self, command_runner: Optional[CommandRunner] = None):
        self.runner = command_runner or CommandRunner()

    def check_docker_available(self) -> bool:
        """Detect whether Docker CLI is installed and the Docker daemon is accessible."""
        docker_bin = shutil.which("docker")
        if not docker_bin:
            return False
        try:
            res = self.runner.run(["docker", "info"], cwd=".", timeout=5)
            return res.is_success
        except Exception:
            return False

    def check_environment(self, workspace: TaskWorkspace, task: Optional[SWEBenchTask] = None) -> EnvironmentStatus:
        """Inspect whether the workspace environment is equipped to execute tests."""
        docker_ok = self.check_docker_available()

        # Check if local workspace has python tests or setup
        has_tests_dir = (workspace.path / "tests").exists() or (workspace.path / "testing").exists()
        has_pyproject = (workspace.path / "pyproject.toml").exists() or (workspace.path / "setup.py").exists()

        if not has_tests_dir and not has_pyproject and not (workspace.path / "src").exists():
            return EnvironmentStatus(
                ready=False,
                docker_available=docker_ok,
                status="INFRASTRUCTURE_BLOCKED",
                details="Workspace does not contain valid source or test directories.",
            )

        if not docker_ok:
            return EnvironmentStatus(
                ready=True,  # Local process execution can still proceed
                docker_available=False,
                status="READY",
                details="Local process execution active (Docker unavailable; executing in native Python host)",
            )

        return EnvironmentStatus(
            ready=True,
            docker_available=True,
            status="READY",
            details="Docker container / isolated environment available.",
        )

    def run_tests(
        self,
        workspace: TaskWorkspace,
        test_command: Optional[str | List[str]] = None,
        timeout: int = 120,
    ) -> TestExecutionResult:
        """Run tests within the isolated task workspace."""
        cmd = test_command or [sys.executable, "-m", "unittest", "discover", "tests", "-v"]

        cmd_res: CommandResult = self.runner.run(
            cmd=cmd,
            cwd=workspace.path,
            timeout=timeout,
        )

        return self.parse_test_output(cmd_res)

    def run_task_at_base_commit(
        self,
        workspace: TaskWorkspace,
        task: SWEBenchTask,
        test_targets: Optional[List[str]] = None,
        timeout: int = 120,
    ) -> TestExecutionResult:
        """Execute test evaluation on a real SWE-bench repository at the base commit."""
        # Determine appropriate test command based on repository layout
        if (workspace.path / "pytest.ini").exists() or (workspace.path / "pyproject.toml").exists():
            test_cmd = [sys.executable, "-m", "pytest", "-v"]
            if test_targets:
                test_cmd.extend(test_targets)
        elif (workspace.path / "tests").exists():
            if test_targets:
                patterns = [t.split("::")[-1].replace(".py", "") for t in test_targets if t]
                k_pattern = "*".join(patterns) if len(patterns) == 1 else " or ".join(patterns)
                test_cmd = [sys.executable, "-m", "unittest", "discover", "tests", "-v", "-k", k_pattern]
            else:
                test_cmd = [sys.executable, "-m", "unittest", "discover", "tests", "-v"]
        else:
            test_cmd = [sys.executable, "-m", "unittest", "-v"]
            if test_targets:
                patterns = [t.split("::")[-1].replace(".py", "") for t in test_targets if t]
                test_cmd.extend(["-k", "*".join(patterns) if len(patterns) == 1 else " or ".join(patterns)])

        cmd_res: CommandResult = self.runner.run(
            cmd=test_cmd,
            cwd=workspace.path,
            timeout=timeout,
        )

        res = self.parse_test_output(cmd_res)
        if cmd_res.timed_out:
            res.status_label = "BLOCKED"
        elif res.passed:
            res.status_label = "PASS"
        else:
            res.status_label = "FAIL"

        return res

    def parse_test_output(self, cmd_res: CommandResult) -> TestExecutionResult:
        combined = f"{cmd_res.stdout}\n{cmd_res.stderr}"

        # 1. Check Python unittest pattern:
        # Ran X tests in Ys
        # OK or FAILED (failures=1, errors=1)
        ran_match = re.search(r"Ran (\d+) tests? in", combined)
        total = int(ran_match.group(1)) if ran_match else 0

        failed_count = 0
        error_count = 0

        fail_match = re.search(r"failures=(\d+)", combined)
        if fail_match:
            failed_count = int(fail_match.group(1))

        err_match = re.search(r"errors=(\d+)", combined)
        if err_match:
            error_count = int(err_match.group(1))

        # 2. Check pytest pattern:
        # ================= 1 failed, 2 passed in 0.12s =================
        pytest_match = re.search(r"(\d+)\s+passed", combined)
        passed_py = int(pytest_match.group(1)) if pytest_match else 0

        pytest_fail_match = re.search(r"(\d+)\s+failed", combined)
        if pytest_fail_match:
            failed_count = max(failed_count, int(pytest_fail_match.group(1)))

        pytest_err_match = re.search(r"(\d+)\s+error", combined)
        if pytest_err_match:
            error_count = max(error_count, int(pytest_err_match.group(1)))

        if pytest_match or pytest_fail_match or pytest_err_match:
            total = max(total, passed_py + failed_count + error_count)

        passed = cmd_res.exit_code == 0 and failed_count == 0 and error_count == 0

        failures = []
        # Extract failure trace lines
        for match in re.finditer(r"(FAIL|ERROR|FAILED)\s*[:=]\s*([^\s\n]+)", combined):
            failures.append(f"{match.group(1)}: {match.group(2)}")

        passed_count = max(0, total - (failed_count + error_count)) if total > 0 else (1 if passed else 0)

        status_label = "PASS" if passed else "FAIL"

        return TestExecutionResult(
            passed=passed,
            total_tests=total,
            passed_tests=passed_count,
            failed_tests=failed_count,
            error_tests=error_count,
            failures=failures,
            raw_stdout=cmd_res.stdout,
            raw_stderr=cmd_res.stderr,
            exit_code=cmd_res.exit_code,
            duration_seconds=cmd_res.duration_seconds,
            status_label=status_label,
        )
