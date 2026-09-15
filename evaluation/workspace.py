"""Isolated workspace management for safe code execution."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from evaluation.command_runner import CommandRunner


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

    def __init__(self, base_workspace_dir: str | Path = "data/workspaces"):
        self.base_dir = Path(base_workspace_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.runner = CommandRunner()

    def create_workspace(self, task_id: str, init_git: bool = True) -> TaskWorkspace:
        """Create a dedicated, isolated task folder."""
        # Sanitize task_id for directory name
        safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in task_id)
        ws_dir = self.base_dir / f"run_{safe_id}_{os.getpid()}"
        ws_dir.mkdir(parents=True, exist_ok=True)

        if init_git:
            # Initialize git repository inside the sandbox
            self.runner.run(["git", "init"], cwd=ws_dir)
            self.runner.run(["git", "config", "user.name", "DDIV Agent"], cwd=ws_dir)
            self.runner.run(["git", "config", "user.email", "ddiv@agent.local"], cwd=ws_dir)

        return TaskWorkspace(workspace_path=ws_dir, task_id=task_id, is_temp=True)

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
