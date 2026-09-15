"""SWE-bench Verified dataset loader and task metadata representation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SWEBenchTask(BaseModel):
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    hints_text: Optional[str] = ""
    created_at: Optional[str] = ""
    test_patch: Optional[str] = ""
    version: Optional[str] = ""
    environment_setup_commit: Optional[str] = ""
    fail_to_pass: List[str] = Field(default_factory=list)
    pass_to_pass: List[str] = Field(default_factory=list)


class SWEBenchLoader:
    """Loads SWE-bench Verified tasks from local JSON/JSONL or online dataset."""

    def __init__(self, cache_dir: str | Path = "data/swebench"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load_from_file(self, file_path: str | Path) -> List[SWEBenchTask]:
        """Load tasks from a local json or jsonl file."""
        path = Path(file_path)
        if not path.exists():
            return []

        tasks: List[SWEBenchTask] = []
        if path.suffix == ".jsonl":
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        tasks.append(self._parse_task_dict(data))
        else:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        tasks.append(self._parse_task_dict(item))
                elif isinstance(data, dict):
                    tasks.append(self._parse_task_dict(data))
        return tasks

    def get_mock_task(self, task_id: str = "mock-swebench-task-1") -> SWEBenchTask:
        """Provide a standard built-in mock SWE-bench task for offline testing."""
        return SWEBenchTask(
            instance_id=task_id,
            repo="mock-org/calculator",
            base_commit="HEAD",
            problem_statement=(
                "Fix Division by Zero Handling in Calculator.\n"
                "When calling Calculator.divide(a, 0), the method does not validate "
                "the denominator and causes an unhandled exception instead of raising ValueError('Cannot divide by zero')."
            ),
            hints_text="Inspect Calculator.divide in src/calculator.py and raise ValueError if b == 0.",
            fail_to_pass=["tests/test_calculator.py::TestCalculator::test_divide_by_zero"],
            pass_to_pass=[
                "tests/test_calculator.py::TestCalculator::test_add",
                "tests/test_calculator.py::TestCalculator::test_divide_normal",
            ],
        )

    def _parse_task_dict(self, data: Dict[str, Any]) -> SWEBenchTask:
        # Normalize fail_to_pass / pass_to_pass if json-encoded string
        f2p = data.get("FAIL_TO_PASS", data.get("fail_to_pass", []))
        if isinstance(f2p, str):
            try:
                f2p = json.loads(f2p)
            except Exception:
                f2p = [f2p]

        p2p = data.get("PASS_TO_PASS", data.get("pass_to_pass", []))
        if isinstance(p2p, str):
            try:
                p2p = json.loads(p2p)
            except Exception:
                p2p = [p2p]

        return SWEBenchTask(
            instance_id=data.get("instance_id", "unknown_task"),
            repo=data.get("repo", "unknown_repo"),
            base_commit=data.get("base_commit", ""),
            problem_statement=data.get("problem_statement", ""),
            hints_text=data.get("hints_text", ""),
            test_patch=data.get("test_patch", ""),
            fail_to_pass=f2p,
            pass_to_pass=p2p,
            version=data.get("version", ""),
        )
