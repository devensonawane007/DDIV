"""SWE-bench Verified dataset loader and task metadata representation with strict agent/evaluator separation."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SWEBenchTask(BaseModel):
    """Agent-facing task object containing only publicly visible problem description and metadata.
    
    CRITICAL: This object must NEVER contain benchmark ground truth (gold_patch, test_patch,
    FAIL_TO_PASS, PASS_TO_PASS).
    """

    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    hints_text: Optional[str] = ""
    created_at: Optional[str] = ""
    version: Optional[str] = ""
    environment_setup_commit: Optional[str] = ""


class SWEBenchGroundTruth(BaseModel):
    """Evaluator-only ground truth solution and verification specifications."""

    gold_patch: str = ""
    test_patch: str = ""
    fail_to_pass: List[str] = Field(default_factory=list)
    pass_to_pass: List[str] = Field(default_factory=list)


class SWEBenchRecord(BaseModel):
    """Internal combined record uniting agent-safe task definition and evaluator ground truth."""

    task: SWEBenchTask
    ground_truth: SWEBenchGroundTruth


class SWEBenchLoader:
    """Loads SWE-bench Verified tasks from Parquet, JSON, or JSONL files."""

    def __init__(self, cache_dir: str | Path = "data/swebench"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load_from_file(self, file_path: str | Path) -> List[SWEBenchRecord]:
        """Load benchmark records from a local .parquet, .json, or .jsonl file."""
        path = Path(file_path)
        if not path.exists():
            return []

        records: List[SWEBenchRecord] = []

        if path.suffix == ".parquet":
            try:
                import pandas as pd
            except ImportError as e:
                raise ImportError(
                    "Parquet dataset loading requires 'pandas' and 'pyarrow'. "
                    "Please install them via: pip install pandas pyarrow"
                ) from e

            df = pd.read_parquet(path)
            for row_dict in df.to_dict(orient="records"):
                records.append(self._parse_record_dict(row_dict))

        elif path.suffix == ".jsonl":
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        records.append(self._parse_record_dict(data))
        else:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        records.append(self._parse_record_dict(item))
                elif isinstance(data, dict):
                    records.append(self._parse_record_dict(data))

        return records

    def get_mock_record(self, task_id: str = "mock-swebench-task-1") -> SWEBenchRecord:
        """Provide a complete mock SWE-bench record with separate task and ground truth."""
        task = SWEBenchTask(
            instance_id=task_id,
            repo="mock-org/calculator",
            base_commit="HEAD",
            problem_statement=(
                "Fix Division by Zero Handling in Calculator.\n"
                "When calling Calculator.divide(a, 0), the method does not validate "
                "the denominator and causes an unhandled exception instead of raising ValueError('Cannot divide by zero')."
            ),
            hints_text="Inspect Calculator.divide in src/calculator.py and raise ValueError if b == 0.",
            created_at="2024-01-01T00:00:00Z",
            version="1.0.0",
            environment_setup_commit="HEAD",
        )
        ground_truth = SWEBenchGroundTruth(
            gold_patch=(
                "diff --git a/src/calculator.py b/src/calculator.py\n"
                "--- a/src/calculator.py\n"
                "+++ b/src/calculator.py\n"
                "@@ -5,2 +5,4 @@\n"
                "     def divide(self, a, b):\n"
                "+        if b == 0:\n"
                "+            raise ValueError('Cannot divide by zero')\n"
                "         return a / b\n"
            ),
            test_patch="",
            fail_to_pass=["tests/test_calculator.py::TestCalculator::test_divide_by_zero"],
            pass_to_pass=[
                "tests/test_calculator.py::TestCalculator::test_add",
                "tests/test_calculator.py::TestCalculator::test_divide_normal",
            ],
        )
        return SWEBenchRecord(task=task, ground_truth=ground_truth)

    def get_mock_task(self, task_id: str = "mock-swebench-task-1") -> SWEBenchTask:
        """Provide a standard agent-safe mock SWE-bench task for offline testing."""
        return self.get_mock_record(task_id=task_id).task

    def _normalize_string_list(self, val: Any) -> List[str]:
        """Safely normalize strings, lists, numpy arrays, or JSON arrays into a list of strings."""
        if val is None:
            return []
        if isinstance(val, (list, tuple, set)):
            return [str(x) for x in val if x is not None and str(x).strip()]
        if hasattr(val, "tolist"):  # NumPy ndarray or pandas Series element
            return [str(x) for x in val.tolist() if x is not None and str(x).strip()]
        if isinstance(val, str):
            s = val.strip()
            if not s or s == "[]":
                return []
            if s.startswith("[") and s.endswith("]"):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        return [str(x) for x in parsed if x is not None and str(x).strip()]
                except Exception:
                    try:
                        parsed = ast.literal_eval(s)
                        if isinstance(parsed, (list, tuple, set)):
                            return [str(x) for x in parsed if x is not None and str(x).strip()]
                    except Exception:
                        pass
            return [s]
        return []

    def _safe_str(self, val: Any) -> str:
        """Safely convert value to string without 'nan' or 'None' artifacts."""
        if val is None:
            return ""
        # Handle pandas / float NaN
        if isinstance(val, float):
            import math
            if math.isnan(val):
                return ""
        s = str(val)
        return "" if s.lower() == "nan" else s

    def _parse_record_dict(self, data: Dict[str, Any]) -> SWEBenchRecord:
        """Parse raw dictionary into strictly separated task and ground_truth components."""
        # 1. Agent-safe Task
        task = SWEBenchTask(
            instance_id=self._safe_str(data.get("instance_id", "unknown_task")),
            repo=self._safe_str(data.get("repo", "unknown_repo")),
            base_commit=self._safe_str(data.get("base_commit", "")),
            problem_statement=self._safe_str(data.get("problem_statement", "")),
            hints_text=self._safe_str(data.get("hints_text", "")),
            created_at=self._safe_str(data.get("created_at", "")),
            version=self._safe_str(data.get("version", "")),
            environment_setup_commit=self._safe_str(data.get("environment_setup_commit", "")),
        )

        # 2. Evaluator-only Ground Truth
        gold_patch = self._safe_str(data.get("patch", data.get("gold_patch", "")))
        test_patch = self._safe_str(data.get("test_patch", ""))
        fail_to_pass = self._normalize_string_list(data.get("FAIL_TO_PASS", data.get("fail_to_pass", [])))
        pass_to_pass = self._normalize_string_list(data.get("PASS_TO_PASS", data.get("pass_to_pass", [])))

        ground_truth = SWEBenchGroundTruth(
            gold_patch=gold_patch,
            test_patch=test_patch,
            fail_to_pass=fail_to_pass,
            pass_to_pass=pass_to_pass,
        )

        return SWEBenchRecord(task=task, ground_truth=ground_truth)
