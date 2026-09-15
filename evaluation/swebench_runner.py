"""Test execution and verification runner for SWE-bench tasks and isolated workspaces."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from evaluation.command_runner import CommandResult, CommandRunner
from evaluation.workspace import TaskWorkspace


class TestExecutionResult(BaseModel):
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


class SWEBenchRunner:
    """Executes verification tests in the workspace and extracts structured test outcomes."""

    def __init__(self, command_runner: Optional[CommandRunner] = None):
        self.runner = command_runner or CommandRunner()

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

    def parse_test_output(self, cmd_res: CommandResult) -> TestExecutionResult:
        combined = f"{cmd_res.stdout}\n{cmd_res.stderr}"

        # Check for Python unittest pattern:
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

        passed = cmd_res.exit_code == 0 and failed_count == 0 and error_count == 0

        failures = []
        # Extract failure trace lines
        for match in re.finditer(r"(FAIL|ERROR):\s*([^\s]+)", combined):
            failures.append(f"{match.group(1)}: {match.group(2)}")

        passed_count = max(0, total - (failed_count + error_count)) if total > 0 else (1 if passed else 0)

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
        )
