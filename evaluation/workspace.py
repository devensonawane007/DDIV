"""Isolated workspace management for safe code execution and SWE-bench repository checkouts."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

from evaluation.command_runner import CommandResult, CommandRunner


class CheckoutResult(BaseModel):
    """Result of a git repository clone and checkout operation."""

    success: bool
    repo: str
    expected_commit: str
    actual_commit: str = ""
    duration_seconds: float = 0.0
    exit_code: int = 0
    error: Optional[str] = None


class TaskWorkspace:
    """Represents an isolated working directory for a single task run."""

    def __init__(self, workspace_path: Path, task_id: str, is_temp: bool = True):
        self.path = workspace_path
        self.task_id = task_id
        self.is_temp = is_temp

    def exists(self) -> bool:
        return self.path.exists()

    def cleanup(self) -> None:
        if self.is_temp and self.path.exists():
            import stat

            def _onerror(func, path, exc_info):
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception:
                    pass

            try:
                shutil.rmtree(self.path, onerror=_onerror)
            except Exception:
                pass

    def __enter__(self) -> TaskWorkspace:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


class WorkspaceManager:
    """Creates and provisions isolated task workspaces without modifying the main DDIV repo."""

    def __init__(self, base_workspace_dir: str | Path = "data/workspaces", repos_cache_dir: str | Path = "data/repos"):
        self.base_dir = Path(base_workspace_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.repos_cache_dir = Path(repos_cache_dir)
        self.repos_cache_dir.mkdir(parents=True, exist_ok=True)
        self.runner = CommandRunner()

    def create_workspace(self, task_id: str, init_git: bool = True, subfolder: Optional[str] = None) -> TaskWorkspace:
        """Create a dedicated, isolated task folder."""
        # Sanitize task_id for directory name
        safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in task_id)
        if subfolder:
            subfolder_path = Path(subfolder)
            if subfolder_path.name in (safe_id, task_id):
                ws_dir = self.base_dir / subfolder_path
            else:
                ws_dir = self.base_dir / subfolder_path / safe_id
        else:
            ws_dir = self.base_dir / f"run_{safe_id}_{os.getpid()}"
        ws_dir.mkdir(parents=True, exist_ok=True)

        if init_git and not (ws_dir / ".git").exists():
            # Initialize git repository inside the sandbox
            self.runner.run(["git", "init"], cwd=ws_dir)
            self.runner.run(["git", "config", "user.name", "DDIV Agent"], cwd=ws_dir)
            self.runner.run(["git", "config", "user.email", "ddiv@agent.local"], cwd=ws_dir)

        return TaskWorkspace(workspace_path=ws_dir, task_id=task_id, is_temp=True)

    def checkout_repository(
        self,
        workspace: TaskWorkspace,
        repo: str,
        base_commit: str,
        timeout: int = 300,
    ) -> CheckoutResult:
        """Clone or fetch a repository into the workspace and checkout the exact base commit."""
        start_time = time.time()
        if not base_commit or not base_commit.strip():
            return CheckoutResult(
                success=False,
                repo=repo,
                expected_commit="",
                actual_commit="",
                duration_seconds=time.time() - start_time,
                exit_code=1,
                error="Target base_commit cannot be empty",
            )

        remote_url = f"https://github.com/{repo}.git" if not repo.startswith("http") else repo

        # Ensure directory exists
        workspace.path.mkdir(parents=True, exist_ok=True)

        # 1. Initialize git if not already initialized
        if not (workspace.path / ".git").exists():
            init_res = self.runner.run(["git", "init"], cwd=workspace.path, timeout=30)
            if not init_res.is_success:
                return CheckoutResult(
                    success=False,
                    repo=repo,
                    expected_commit=base_commit,
                    duration_seconds=time.time() - start_time,
                    exit_code=init_res.exit_code,
                    error=f"git init failed: {init_res.stderr}",
                )

        # Configure user
        self.runner.run(["git", "config", "user.name", "DDIV Evaluator"], cwd=workspace.path, timeout=10)
        self.runner.run(["git", "config", "user.email", "evaluator@ddiv.local"], cwd=workspace.path, timeout=10)

        # Set or update origin remote
        remotes_res = self.runner.run(["git", "remote"], cwd=workspace.path, timeout=10)
        if "origin" not in remotes_res.stdout:
            self.runner.run(["git", "remote", "add", "origin", remote_url], cwd=workspace.path, timeout=10)
        else:
            self.runner.run(["git", "remote", "set-url", "origin", remote_url], cwd=workspace.path, timeout=10)

        # 2. Fetch the target base_commit
        fetch_res = self.runner.run(
            ["git", "fetch", "--depth", "1", "origin", base_commit],
            cwd=workspace.path,
            timeout=timeout,
        )

        # Fallback to general fetch if shallow commit fetch is rejected
        if not fetch_res.is_success:
            fetch_res = self.runner.run(
                ["git", "fetch", "origin", base_commit],
                cwd=workspace.path,
                timeout=timeout,
            )
            if not fetch_res.is_success:
                # Last resort fallback: fetch recent history
                fetch_res = self.runner.run(
                    ["git", "fetch", "--depth", "50", "origin"],
                    cwd=workspace.path,
                    timeout=timeout,
                )

        if not fetch_res.is_success:
            return CheckoutResult(
                success=False,
                repo=repo,
                expected_commit=base_commit,
                duration_seconds=time.time() - start_time,
                exit_code=fetch_res.exit_code,
                error=f"git fetch failed for {remote_url} at {base_commit}: {fetch_res.stderr}",
            )

        # 3. Checkout the base commit and reset to pristine state
        self.runner.run(["git", "reset", "--hard"], cwd=workspace.path, timeout=30)
        self.runner.run(["git", "clean", "-fd"], cwd=workspace.path, timeout=30)
        checkout_res = self.runner.run(
            ["git", "checkout", "-f", base_commit],
            cwd=workspace.path,
            timeout=60,
        )
        self.runner.run(["git", "reset", "--hard", base_commit], cwd=workspace.path, timeout=30)
        self.runner.run(["git", "clean", "-fd"], cwd=workspace.path, timeout=30)

        if not checkout_res.is_success:
            return CheckoutResult(
                success=False,
                repo=repo,
                expected_commit=base_commit,
                duration_seconds=time.time() - start_time,
                exit_code=checkout_res.exit_code,
                error=f"git checkout failed for commit {base_commit}: {checkout_res.stderr}",
            )

        # 4. Verify actual checked out commit matches expected base_commit
        rev_res = self.runner.run(["git", "rev-parse", "HEAD"], cwd=workspace.path, timeout=10)
        actual_commit = rev_res.stdout.strip()
        duration = time.time() - start_time

        if not rev_res.is_success or not actual_commit or not base_commit:
            return CheckoutResult(
                success=False,
                repo=repo,
                expected_commit=base_commit,
                actual_commit=actual_commit,
                duration_seconds=duration,
                exit_code=rev_res.exit_code if not rev_res.is_success else 1,
                error=f"Failed to resolve HEAD commit: {rev_res.stderr or 'Empty commit hash'}",
            )

        if actual_commit.startswith(base_commit) or base_commit.startswith(actual_commit):
            return CheckoutResult(
                success=True,
                repo=repo,
                expected_commit=base_commit,
                actual_commit=actual_commit,
                duration_seconds=duration,
                exit_code=0,
            )
        else:
            return CheckoutResult(
                success=False,
                repo=repo,
                expected_commit=base_commit,
                actual_commit=actual_commit,
                duration_seconds=duration,
                exit_code=1,
                error=f"Base commit mismatch: expected {base_commit}, got {actual_commit}",
            )

    def provision_mock_task(self, workspace: TaskWorkspace) -> None:
        """Populate a workspace with a reproducible mock test case (Calculator example)."""
        src_dir = workspace.path / "src"
        tests_dir = workspace.path / "tests"
        src_dir.mkdir(parents=True, exist_ok=True)
        tests_dir.mkdir(parents=True, exist_ok=True)

        # Initial source with flaw (missing zero division check or error handling)
        calc_code = (
            "class Calculator:\n"
            "    def add(self, a, b):\n"
            "        return a + b\n\n"
            "    def divide(self, a, b):\n"
            "        return a / b\n"
        )
        (src_dir / "calculator.py").write_text(calc_code, encoding="utf-8")

        # Test expecting ValueError on divide by zero
        test_code = (
            "import unittest\n"
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))\n"
            "from calculator import Calculator\n\n"
            "class TestCalculator(unittest.TestCase):\n"
            "    def setUp(self):\n"
            "        self.calc = Calculator()\n\n"
            "    def test_add(self):\n"
            "        self.assertEqual(self.calc.add(2, 3), 5)\n\n"
            "    def test_divide_normal(self):\n"
            "        self.assertEqual(self.calc.divide(10, 2), 5)\n\n"
            "    def test_divide_by_zero(self):\n"
            "        with self.assertRaises(ValueError):\n"
            "            self.calc.divide(10, 0)\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n"
        )
        (tests_dir / "test_calculator.py").write_text(test_code, encoding="utf-8")

        # Commit initial baseline state to git
        self.runner.run(["git", "add", "."], cwd=workspace.path)
        self.runner.run(["git", "commit", "-m", "Initial commit"], cwd=workspace.path)

