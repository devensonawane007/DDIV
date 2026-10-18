"""QuixBugs Python Benchmark Adapter for DDIV.

Provides task discovery, ground-truth isolated workspace creation, reference solution protection,
and offline evaluation for the QuixBugs Python program repair benchmark.

Architecture:
- QuixBugsTask: Normalized task metadata specification.
- QuixBugsEvaluationResult: Detailed evaluation outcome report with sanitized diagnostics.
- QuixBugsBaselineResult: Pre-repair defect reproduction and baseline eligibility evidence.
- QuixBugsAdapter: Central service for discovery, provisioning, and evaluation.

Ground-Truth Isolation Policy:
- Agent workspace contains EXCLUSIVELY the buggy target implementation (and node.py for graph tasks).
- Test modules (python_testcases/) and JSON test data (json_testcases/) remain STRICTLY evaluator-side.
- Reference implementations (correct_python_programs/) are NEVER exposed to agents, prompts, or logs.
- Evaluation runs from the evaluator boundary; candidate imports resolve to the agent workspace.
- Assertion diffs and expected oracle literals are redacted before diagnostics reach recovery loops.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from evaluation.command_runner import CommandResult, CommandRunner
from evaluation.patch_manager import PatchManager, PatchValidationResult


GRAPH_BASED_ALGORITHMS: Set[str] = {
    "breadth_first_search",
    "depth_first_search",
    "detect_cycle",
    "minimum_spanning_tree",
    "reverse_linked_list",
    "shortest_path_length",
    "shortest_path_lengths",
    "shortest_paths",
    "topological_ordering",
}

# Formal asset classification constants
AGENT_VISIBLE_SOURCE: str = "python_programs/{prog_name}.py"
AGENT_VISIBLE_SUPPORT: str = "python_programs/node.py"
EVALUATOR_ONLY_TEST_DIR: str = "python_testcases"
EVALUATOR_ONLY_JSON_DIR: str = "json_testcases"
PROTECTED_REFERENCE_DIRS: Tuple[str, ...] = (
    "correct_python_programs",
    "correct_java_programs",
    "java_programs",
    "java_testcases",
)


def sanitize_evaluator_output(raw_stdout: str, raw_stderr: str) -> Tuple[str, str]:
    """Strip or redact oracle literals, input/expected dumps, and assertion values.

    Preserves:
    - Test function identity (e.g. test_bucketsort)
    - Exception types (e.g. AssertionError, IndexError, TypeError, ZeroDivisionError)
    - Line numbers in candidate code where failures occur
    - Overall summary counts (passed, failed)

    Redacts:
    - Parametrized test arguments (e.g. [input_data1-expected1] -> [case_test])
    - Local variable dumps (e.g. input_data = ..., expected = ...)
    - Assertion operands and diff outputs (e.g. assert [...] == [...])
    - Paths to reference solution directories (correct_python_programs)
    """
    def _clean_stream(text: str) -> str:
        if not text:
            return ""
        lines: List[str] = []
        in_assertion_diff = False

        for line in text.splitlines():
            # 1. Redact test parametrization labels: e.g. [input_data1-5] -> [case_test]
            cleaned_line = re.sub(r"\[input(?:_data)?\d*-[^\]\r\n]+\]", "[case_test]", line)

            # 2. Redact input_data / expected variable dump
            if re.search(r"\b(expected|input_data)\s*=", cleaned_line):
                lines.append("    [INPUT_AND_EXPECTED_ORACLE_REDACTED]")
                continue

            # 3. Redact assertion statements and values
            if "AssertionError: assert" in cleaned_line or (cleaned_line.strip().startswith("E ") and "assert " in cleaned_line):
                lines.append("E       AssertionError: candidate output did not match expected output [ORACLE_REDACTED]")
                in_assertion_diff = True
                continue

            # 4. If in assertion diff block, suppress detailed diff lines until non-diff line
            if in_assertion_diff:
                if cleaned_line.startswith("E ") or cleaned_line.strip() == "E":
                    continue
                else:
                    in_assertion_diff = False

            # 5. Redact references to protected directories
            for ref_dir in PROTECTED_REFERENCE_DIRS:
                cleaned_line = cleaned_line.replace(ref_dir, "[REDACTED_REFERENCE]")
            cleaned_line = cleaned_line.replace("json_testcases", "[REDACTED_TESTCASES]")

            lines.append(cleaned_line)

        return "\n".join(lines)

    return _clean_stream(raw_stdout), _clean_stream(raw_stderr)


def validate_patch_security(patch_text: str, allowed_files: List[str]) -> Tuple[bool, str]:
    """Perform security and AST check on candidate patch.

    Guarantees:
    - Patch can ONLY touch allowed agent-visible files (e.g. python_programs/<prog>.py).
    - Added code cannot contain file I/O (open), subprocess, or dangerous OS calls
      attempting to probe evaluator directories at runtime.
    """
    for line in patch_text.splitlines():
        if line.startswith("+++ b/"):
            dest_file = line[6:].strip().replace("\\", "/")
            if dest_file not in allowed_files:
                return False, f"SECURITY VIOLATION: Patch attempts to modify unauthorized file: '{dest_file}'"

    added_lines = [
        line[1:] for line in patch_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    code_block = "\n".join(added_lines)

    forbidden_tokens = ["open(", "subprocess", "os.system", "shutil", "builtins", "__import__", "socket", "urllib"]
    for tok in forbidden_tokens:
        if tok in code_block:
            return False, f"SECURITY VIOLATION: Forbidden operation '{tok}' detected in candidate patch."

    return True, "Patch security check passed."


class QuixBugsTask(BaseModel):
    """Normalized task representation for a single QuixBugs repair task."""

    benchmark: str = "quixbugs"
    task_id: str
    program_name: str
    language: str = "python"
    target_file: str
    agent_visible_files: List[str] = Field(default_factory=list)
    evaluator_test_files: List[str] = Field(default_factory=list)
    evaluator_support_files: List[str] = Field(default_factory=list)
    test_files: List[str] = Field(default_factory=list)
    support_files: List[str] = Field(default_factory=list)
    test_command: List[str] = Field(default_factory=list)
    workspace_policy: str = "two_workspace_ground_truth_isolation"
    problem_description: str
    baseline_status: str = "NOT_RUN"
    eligibility_status: str = "UNKNOWN"
    result_metadata: Dict[str, Any] = Field(default_factory=dict)


class QuixBugsEvaluationResult(BaseModel):
    """Result of evaluating a candidate patch against a QuixBugs task."""

    task_id: str
    benchmark: str = "quixbugs"
    candidate_patch_applied: bool
    candidate_patch_error: Optional[str] = None
    total_tests: int = 0
    passed_tests: List[str] = Field(default_factory=list)
    failed_tests: List[str] = Field(default_factory=list)
    inconclusive_tests: List[str] = Field(default_factory=list)
    fail_to_pass: Dict[str, bool] = Field(default_factory=dict)
    pass_to_pass: Dict[str, bool] = Field(default_factory=dict)
    all_passed: bool = False
    resolved: bool = False
    evaluation_verdict: str = "UNRESOLVED"
    duration_seconds: float = 0.0
    exit_code: int = 0
    raw_stdout: str = ""
    raw_stderr: str = ""
    sanitized_stdout: str = ""
    sanitized_stderr: str = ""
    oracle_redacted: bool = True
    failure_category: str = "NONE"
    failure_summary: str = ""


class QuixBugsBaselineResult(BaseModel):
    """Result of establishing baseline defect reproduction on unpatched code."""

    task_id: str
    total_tests: int = 0
    passed_tests: List[str] = Field(default_factory=list)
    failed_tests: List[str] = Field(default_factory=list)
    inconclusive_tests: List[str] = Field(default_factory=list)
    has_reproduced_defect: bool = False
    has_environment_failure: bool = False
    is_timeout: bool = False
    eligibility_status: str = "UNKNOWN"
    error_message: Optional[str] = None
    raw_output: str = ""
    sanitized_output: str = ""
    duration_seconds: float = 0.0


class QuixBugsAdapter:
    """Discovers, provisions, and evaluates QuixBugs Python repair tasks with strict ground-truth isolation."""

    def __init__(
        self,
        quixbugs_root: str | Path = "data/quixbugs",
        command_runner: Optional[CommandRunner] = None,
        patch_manager: Optional[PatchManager] = None,
    ):
        self.quixbugs_root = Path(quixbugs_root).resolve()
        self.runner = command_runner or CommandRunner()
        self.patch_mgr = patch_manager or PatchManager(self.runner)

    def is_available(self) -> bool:
        """Check whether the QuixBugs Python dataset is available on disk."""
        if not self.quixbugs_root.is_dir():
            return False
        py_prog = self.quixbugs_root / "python_programs"
        py_test = self.quixbugs_root / "python_testcases"
        return py_prog.is_dir() and py_test.is_dir()

    def discover_tasks(self) -> List[QuixBugsTask]:
        """Scan the dataset and discover all valid Python programs and their test modules.

        Returns a deterministic, sorted list of QuixBugsTask specifications with strict
        asset classification (agent-visible vs evaluator-only).
        """
        if not self.is_available():
            return []

        py_prog_dir = self.quixbugs_root / "python_programs"
        py_test_dir = self.quixbugs_root / "python_testcases"
        json_dir = self.quixbugs_root / "json_testcases"

        candidate_files = sorted(
            [
                p for p in py_prog_dir.glob("*.py")
                if not p.name.endswith("_test.py") and p.name != "node.py"
            ],
            key=lambda p: p.stem,
        )

        tasks: List[QuixBugsTask] = []
        for p in candidate_files:
            prog_name = p.stem
            test_file = py_test_dir / f"test_{prog_name}.py"
            if not test_file.exists():
                continue

            task_id = f"quixbugs-python-{prog_name}"
            target_rel = f"python_programs/{prog_name}.py"
            test_rel = f"python_testcases/test_{prog_name}.py"

            is_graph = prog_name in GRAPH_BASED_ALGORITHMS

            # Agent visible assets: strictly target file (+ node.py for graph algorithms)
            agent_visible = [target_rel]
            if is_graph:
                agent_visible.append("python_programs/node.py")

            # Evaluator only test files
            evaluator_tests = [test_rel]

            # Evaluator only support files (fixtures, conftest, json oracle data)
            evaluator_support: List[str] = ["conftest.py"]
            support_files: List[str] = ["conftest.py"]
            if is_graph:
                evaluator_support.append("python_testcases/node.py")
                support_files.extend(["python_programs/node.py", "python_testcases/node.py"])
            else:
                evaluator_support.append("python_testcases/load_testdata.py")
                support_files.append("python_testcases/load_testdata.py")
                json_file = json_dir / f"{prog_name}.json"
                if json_file.exists():
                    evaluator_support.append(f"json_testcases/{prog_name}.json")
                    support_files.append(f"json_testcases/{prog_name}.json")

            desc = (
                f"Repair the implementation of '{prog_name}' in '{target_rel}' "
                f"so that all required specification tests pass without introducing regressions."
            )

            test_cmd = [
                sys.executable,
                "-m",
                "pytest",
                "-v",
                "--tb=short",
                test_rel,
            ]

            tasks.append(
                QuixBugsTask(
                    task_id=task_id,
                    program_name=prog_name,
                    target_file=target_rel,
                    agent_visible_files=agent_visible,
                    evaluator_test_files=evaluator_tests,
                    evaluator_support_files=evaluator_support,
                    test_files=evaluator_tests,
                    support_files=support_files,
                    test_command=test_cmd,
                    problem_description=desc,
                    result_metadata={
                        "is_graph_based": is_graph,
                        "has_json_testdata": (json_dir / f"{prog_name}.json").exists(),
                    },
                )
            )

        return tasks

    def get_task(self, task_id: str) -> Optional[QuixBugsTask]:
        """Look up a specific task by task_id or program_name."""
        for task in self.discover_tasks():
            if task.task_id == task_id or task.program_name == task_id:
                return task
        return None

    def create_agent_workspace(
        self,
        task_id: str,
        dest_dir: str | Path,
        init_git: bool = True,
    ) -> Path:
        """Create an isolated, agent-safe workspace containing ONLY buggy source code.

        CRITICAL ISOLATION GUARANTEES:
        - Only python_programs/<prog>.py and python_programs/node.py (for graph tasks) are copied.
        - Test files (python_testcases/) and oracle data (json_testcases/) are NEVER copied.
        - Reference solutions (correct_python_programs/) are NEVER copied.
        - Fails closed if any test, JSON, or reference file/directory appears in dest_dir.
        - Fails closed if any symlink points outside dest_dir.
        """
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(f"QuixBugs task not found: {task_id}")

        dest = Path(dest_dir).resolve()
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)

        # 1. Copy ONLY agent-visible files
        for rel_file in task.agent_visible_files:
            src = self.quixbugs_root / rel_file
            if not src.exists():
                raise FileNotFoundError(f"Required agent-visible source file not found: {src}")
            dst = dest / rel_file
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        # 2. Strict Fail-Closed Isolation Audit Gate
        for root, dirs, files in os.walk(dest):
            for d in dirs:
                dl = d.lower()
                if "correct" in dl:
                    shutil.rmtree(dest, ignore_errors=True)
                    raise RuntimeError(f"CRITICAL ISOLATION BREACH: Reference directory '{d}' detected in agent workspace!")
                if dl == "tests" or dl.startswith("test_") or "testcase" in dl or dl.endswith("_test"):
                    shutil.rmtree(dest, ignore_errors=True)
                    raise RuntimeError(f"CRITICAL ISOLATION BREACH: Test directory '{d}' detected in agent workspace!")

            for f in files:
                fl = f.lower()
                if "correct" in fl:
                    shutil.rmtree(dest, ignore_errors=True)
                    raise RuntimeError(f"CRITICAL ISOLATION BREACH: Reference file '{f}' detected in agent workspace!")
                if (
                    fl.startswith("test_")
                    or fl.endswith("_test.py")
                    or "testcase" in fl
                    or fl == "conftest.py"
                    or fl.endswith(".json")
                ):
                    shutil.rmtree(dest, ignore_errors=True)
                    raise RuntimeError(f"CRITICAL ISOLATION BREACH: Evaluator/oracle asset '{f}' leaked into agent workspace!")

                # Symlink defense
                f_path = Path(root) / f
                if f_path.is_symlink():
                    resolved_target = f_path.resolve()
                    if not resolved_target.is_relative_to(dest):
                        shutil.rmtree(dest, ignore_errors=True)
                        raise RuntimeError(f"CRITICAL ISOLATION BREACH: Symlink '{f}' escaping workspace boundary detected!")

        # 3. Initialize git repository if requested
        if init_git:
            self.runner.run(["git", "init", "-q"], cwd=dest)
            self.runner.run(["git", "config", "user.name", "DDIV Agent"], cwd=dest)
            self.runner.run(["git", "config", "user.email", "ddiv@antigravity.local"], cwd=dest)
            self.runner.run(["git", "add", "."], cwd=dest)
            self.runner.run(["git", "commit", "-q", "-m", "Initial buggy QuixBugs checkout (isolated agent workspace)"], cwd=dest)

        return dest

    def create_task_workspace(
        self,
        task_id: str,
        dest_dir: str | Path,
        init_git: bool = True,
    ) -> Path:
        """Backward-compatibility wrapper ensuring all task workspaces enforce ground-truth isolation."""
        return self.create_agent_workspace(task_id, dest_dir, init_git)

    def create_evaluator_workspace(
        self,
        task_id: str,
        dest_dir: str | Path,
    ) -> Path:
        """Create an evaluator-only workspace containing test modules and test data fixtures."""
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(f"QuixBugs task not found: {task_id}")

        dest = Path(dest_dir).resolve()
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)

        for tf in task.evaluator_test_files:
            src = self.quixbugs_root / tf
            dst = dest / tf
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        for sf in task.evaluator_support_files:
            src = self.quixbugs_root / sf
            if src.exists():
                dst = dest / sf
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        return dest

    @staticmethod
    def parse_pytest_output(stdout: str, stderr: str) -> Tuple[List[str], List[str], List[str]]:
        """Parse pytest stdout to extract lists of passed, failed, and inconclusive test cases."""
        passed: List[str] = []
        failed: List[str] = []
        inconclusive: List[str] = []

        combined = f"{stdout}\n{stderr}"
        for line in combined.splitlines():
            line_str = line.strip()
            match = re.search(r"^(\S*::\S+)\s+(PASSED|FAILED|ERROR|XFAIL|XPASS)", line_str)
            if match:
                node_id = match.group(1).replace("\\", "/")
                # Anonymize parametrized arguments in node_id: e.g. [input_data0-5] -> [case_0]
                node_id = re.sub(r"\[input(?:_data)?\d*-[^\]\r\n]+\]", "[case]", node_id)
                status = match.group(2)
                if status == "PASSED":
                    if node_id not in passed:
                        passed.append(node_id)
                elif status in ("FAILED", "XPASS"):
                    if node_id not in failed:
                        failed.append(node_id)
                elif status in ("ERROR", "XFAIL"):
                    if node_id not in inconclusive:
                        inconclusive.append(node_id)

        # Fallback summary parsing if individual lines were not formatted as expected
        if not passed and not failed:
            passed_summary = re.search(r"(\d+)\s+passed", combined)
            failed_summary = re.search(r"(\d+)\s+failed", combined)
            error_summary = re.search(r"(\d+)\s+error", combined)
            if passed_summary:
                p_cnt = int(passed_summary.group(1))
                passed.extend([f"test_case_{i+1}" for i in range(p_cnt)])
            if failed_summary:
                f_cnt = int(failed_summary.group(1))
                failed.extend([f"failed_case_{i+1}" for i in range(f_cnt)])
            if error_summary:
                e_cnt = int(error_summary.group(1))
                inconclusive.extend([f"error_case_{i+1}" for i in range(e_cnt)])

        in_summary = False
        for line in combined.splitlines():
            if "short test summary info" in line:
                in_summary = True
                continue
            if in_summary:
                if line.startswith("FAILED "):
                    parts = line.split()
                    if len(parts) >= 2:
                        node_id = parts[1].replace("\\", "/")
                        node_id = re.sub(r"\[input(?:_data)?\d*-[^\]\r\n]+\]", "[case]", node_id)
                        if node_id not in failed:
                            failed.append(node_id)
                elif line.startswith("ERROR "):
                    parts = line.split()
                    if len(parts) >= 2:
                        node_id = parts[1].replace("\\", "/")
                        node_id = re.sub(r"\[input(?:_data)?\d*-[^\]\r\n]+\]", "[case]", node_id)
                        if node_id not in inconclusive:
                            inconclusive.append(node_id)

        return passed, failed, inconclusive

    def evaluate_patch(
        self,
        workspace_path: str | Path,
        task: QuixBugsTask,
        candidate_patch: str,
        baseline_results: Optional[Dict[str, bool]] = None,
        timeout: int = 15,
    ) -> QuixBugsEvaluationResult:
        """Evaluate a candidate patch inside an isolated QuixBugs workspace.

        Security & Ground-Truth Isolation Enforcements:
        - Pre-execution validation verifies candidate patch format and unified diff syntax.
        - Security validation ensures patch modifies ONLY permitted source files and
          forbids file I/O, subprocess, and network calls (preventing sandbox probing).
        - Pytest executes in an isolated external Python subprocess from a temporary working
          directory with candidate workspace prepended to sys.path, ensuring candidate code is tested
          without copying tests into the agent workspace and completely preventing persistent sys.path
          or sys.modules module-cache contamination in the parent process.
        - All output streams (stdout, stderr, summaries) are sanitized to eliminate raw
          expected oracle values before returning to model-facing recovery loops.
        """
        start_time = time.time()
        ws = Path(workspace_path).resolve()

        # 1. Reject empty or whitespace-only patch
        if not candidate_patch or not candidate_patch.strip():
            return QuixBugsEvaluationResult(
                task_id=task.task_id,
                candidate_patch_applied=False,
                candidate_patch_error="Candidate patch is empty or whitespace only.",
                evaluation_verdict="UNRESOLVED (Empty patch)",
                failure_category="EMPTY_PATCH",
                failure_summary="Empty or whitespace-only patch submitted.",
                duration_seconds=time.time() - start_time,
            )

        # 2. Validate unified diff format
        val_res = self.patch_mgr.validate_patch(candidate_patch)
        if not val_res.is_valid:
            return QuixBugsEvaluationResult(
                task_id=task.task_id,
                candidate_patch_applied=False,
                candidate_patch_error=val_res.error_message,
                evaluation_verdict="UNRESOLVED (Invalid patch format)",
                failure_category="PATCH_FORMAT_INVALID",
                failure_summary=f"Unified diff validation failed: {val_res.error_message}",
                duration_seconds=time.time() - start_time,
            )

        # 3. Patch Security Validation (prevent unauthorized file edits or file-probing payloads)
        allowed_files = list(task.agent_visible_files)
        is_safe, sec_msg = validate_patch_security(candidate_patch, allowed_files)
        if not is_safe:
            return QuixBugsEvaluationResult(
                task_id=task.task_id,
                candidate_patch_applied=False,
                candidate_patch_error=sec_msg,
                evaluation_verdict="UNRESOLVED (Security violation)",
                failure_category="SECURITY_VIOLATION",
                failure_summary=sec_msg,
                duration_seconds=time.time() - start_time,
            )

        # 4. Apply Candidate Patch to Workspace
        apply_res = self.patch_mgr.apply_patch(ws, candidate_patch)
        if not apply_res.is_success:
            return QuixBugsEvaluationResult(
                task_id=task.task_id,
                candidate_patch_applied=False,
                candidate_patch_error=apply_res.stderr or apply_res.stdout,
                evaluation_verdict="UNRESOLVED (Patch application failed)",
                raw_stdout=apply_res.stdout,
                raw_stderr=apply_res.stderr,
                exit_code=apply_res.exit_code,
                failure_category="PATCH_APPLICATION_FAILED",
                failure_summary="git apply failed to apply candidate patch to workspace.",
                duration_seconds=time.time() - start_time,
            )

        # 5. Execute Authoritative Test Suite from Evaluator Boundary
        test_rel = task.test_files[0] if task.test_files else f"python_testcases/test_{task.program_name}.py"
        test_abs = str((self.quixbugs_root / test_rel).resolve())
        py_test_dir = str((self.quixbugs_root / "python_testcases").resolve())
        qb_root_str = str(self.quixbugs_root)
        ws_str = str(ws)

        with tempfile.TemporaryDirectory() as td:
            runner_code = (
                "import sys, pytest\n"
                f"sys.path.insert(0, {repr(ws_str)})\n"
                f"sys.path.insert(1, {repr(py_test_dir)})\n"
                f"sys.path.insert(2, {repr(qb_root_str)})\n"
                f"sys.exit(pytest.main(['-v', '--tb=short', '--import-mode=append', {repr(test_abs)}]))\n"
            )

            env = os.environ.copy()
            env["PYTHONPATH"] = os.pathsep.join([ws_str, py_test_dir, qb_root_str])

            try:
                res = subprocess.run(
                    [sys.executable, "-c", runner_code],
                    cwd=td,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                )
                raw_stdout = res.stdout
                raw_stderr = res.stderr
                exit_code = res.returncode
                timed_out = False
            except subprocess.TimeoutExpired as te:
                raw_stdout = str(te.stdout or "")
                raw_stderr = str(te.stderr or "")
                exit_code = -1
                timed_out = True
            except Exception as e:
                raw_stdout = ""
                raw_stderr = str(e)
                exit_code = -2
                timed_out = False

        duration = time.time() - start_time

        # 6. Sanitize Diagnostics
        san_stdout, san_stderr = sanitize_evaluator_output(raw_stdout, raw_stderr)

        if timed_out:
            return QuixBugsEvaluationResult(
                task_id=task.task_id,
                candidate_patch_applied=True,
                total_tests=0,
                evaluation_verdict="UNRESOLVED (Timeout)",
                duration_seconds=duration,
                exit_code=exit_code,
                raw_stdout=raw_stdout,
                raw_stderr=raw_stderr,
                sanitized_stdout=san_stdout,
                sanitized_stderr=san_stderr,
                oracle_redacted=True,
                failure_category="TIMEOUT",
                failure_summary=f"Test execution timed out after {timeout}s (possible infinite loop).",
            )

        passed, failed, inconclusive = self.parse_pytest_output(raw_stdout, raw_stderr)
        total = len(passed) + len(failed) + len(inconclusive)

        f2p: Dict[str, bool] = {}
        p2p: Dict[str, bool] = {}
        if baseline_results:
            for t_name, base_passed in baseline_results.items():
                is_currently_passed = (
                    t_name in passed
                    or any(p.endswith(t_name) or t_name.endswith(p) or t_name.split("::")[-1] == p.split("::")[-1] for p in passed)
                )
                if not base_passed:
                    f2p[t_name] = is_currently_passed
                else:
                    p2p[t_name] = is_currently_passed

        all_passed = (len(failed) == 0 and len(inconclusive) == 0 and len(passed) > 0)

        if baseline_results:
            has_cured_defect = any(f2p.values()) if f2p else True
            resolved = all_passed and has_cured_defect
        else:
            resolved = all_passed

        if resolved:
            cat = "NONE"
            summary = "All tests passed successfully."
            verdict = "RESOLVED"
        elif "SyntaxError" in raw_stdout or "SyntaxError" in raw_stderr:
            cat = "SYNTAX_ERROR"
            summary = "Syntax error in patched source file."
            verdict = "UNRESOLVED (Syntax error)"
        elif "ImportError" in raw_stdout or "ModuleNotFoundError" in raw_stdout:
            cat = "IMPORT_ERROR"
            summary = "Import error during test execution."
            verdict = "UNRESOLVED (Import error)"
        elif inconclusive:
            cat = "TEST_COLLECTION_OR_SETUP_ERROR"
            summary = f"Errors encountered in tests: {inconclusive}"
            verdict = "UNRESOLVED (Test error)"
        elif failed:
            cat = "ASSERTION_FAILURE"
            summary = f"{len(failed)} test(s) failed assertion check."
            verdict = "UNRESOLVED (Tests failed)"
        else:
            cat = "UNKNOWN"
            summary = "Test suite did not complete with passing status."
            verdict = "UNRESOLVED"

        return QuixBugsEvaluationResult(
            task_id=task.task_id,
            candidate_patch_applied=True,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            inconclusive_tests=inconclusive,
            fail_to_pass=f2p,
            pass_to_pass=p2p,
            all_passed=all_passed,
            resolved=resolved,
            evaluation_verdict=verdict,
            duration_seconds=round(duration, 3),
            exit_code=exit_code,
            raw_stdout=raw_stdout,
            raw_stderr=raw_stderr,
            sanitized_stdout=san_stdout,
            sanitized_stderr=san_stderr,
            oracle_redacted=True,
            failure_category=cat,
            failure_summary=summary,
        )

    def check_baseline_eligibility(
        self,
        task: QuixBugsTask,
        timeout: int = 10,
    ) -> QuixBugsBaselineResult:
        """Execute unpatched code in an isolated workspace via an external subprocess to confirm defect reproduction.

        Distinguishes:
        - ELIGIBLE: Test suite ran cleanly in a fresh Python subprocess and at least one test failed due to intended defect or timeout (infinite loop).
        - INELIGIBLE: All tests passed on unpatched code (no bug present).
        - NEEDS_RECHECK: Collection/import failure or unhandled environment failure.

        Isolation Guarantee:
        Executes via subprocess.run() in an isolated temporary working directory; workspace and process terminate cleanly, leaving no persistent sys.path or sys.modules alterations.
        """
        start_time = time.time()
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            try:
                self.create_agent_workspace(task.task_id, ws, init_git=False)
            except Exception as e:
                return QuixBugsBaselineResult(
                    task_id=task.task_id,
                    has_environment_failure=True,
                    eligibility_status="NEEDS_RECHECK",
                    error_message=f"Workspace creation failed: {e}",
                    duration_seconds=round(time.time() - start_time, 3),
                )

            test_rel = task.test_files[0] if task.test_files else f"python_testcases/test_{task.program_name}.py"
            test_abs = str((self.quixbugs_root / test_rel).resolve())
            py_test_dir = str((self.quixbugs_root / "python_testcases").resolve())
            qb_root_str = str(self.quixbugs_root)
            ws_str = str(ws)

            with tempfile.TemporaryDirectory() as eval_cwd:
                runner_code = (
                    "import sys, pytest\n"
                    f"sys.path.insert(0, {repr(ws_str)})\n"
                    f"sys.path.insert(1, {repr(py_test_dir)})\n"
                    f"sys.path.insert(2, {repr(qb_root_str)})\n"
                    f"sys.exit(pytest.main(['-v', '--tb=short', '--import-mode=append', {repr(test_abs)}]))\n"
                )

                env = os.environ.copy()
                env["PYTHONPATH"] = os.pathsep.join([ws_str, py_test_dir, qb_root_str])

                try:
                    res = subprocess.run(
                        [sys.executable, "-c", runner_code],
                        cwd=eval_cwd,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        encoding="utf-8",
                        errors="replace",
                    )
                    raw_out = f"{res.stdout}\n{res.stderr}"
                    is_timeout = False
                except subprocess.TimeoutExpired:
                    raw_out = f"TIMEOUT: Test execution exceeded {timeout}s (infinite loop in buggy code)"
                    is_timeout = True
                except Exception as e:
                    raw_out = f"EXECUTION_ERROR: {e}"
                    is_timeout = False

            duration = time.time() - start_time
            san_out, _ = sanitize_evaluator_output(raw_out, "")

            if is_timeout:
                return QuixBugsBaselineResult(
                    task_id=task.task_id,
                    total_tests=1,
                    failed_tests=[f"{test_rel}::TIMEOUT"],
                    has_reproduced_defect=True,
                    is_timeout=True,
                    eligibility_status="ELIGIBLE",
                    raw_output=raw_out,
                    sanitized_output=san_out,
                    duration_seconds=round(duration, 3),
                )

            passed, failed, inconclusive = self.parse_pytest_output(raw_out, "")
            total = len(passed) + len(failed) + len(inconclusive)

            has_env_error = (
                "ImportError" in raw_out
                or "ModuleNotFoundError" in raw_out
                or "SyntaxError" in raw_out
                or (total == 0 and "no tests ran" in raw_out.lower())
            )

            if has_env_error:
                status = "NEEDS_RECHECK"
            elif len(failed) > 0:
                status = "ELIGIBLE"
            elif total > 0 and len(failed) == 0:
                status = "INELIGIBLE"
            else:
                status = "NEEDS_RECHECK"

            return QuixBugsBaselineResult(
                task_id=task.task_id,
                total_tests=total,
                passed_tests=passed,
                failed_tests=failed,
                inconclusive_tests=inconclusive,
                has_reproduced_defect=len(failed) > 0,
                has_environment_failure=has_env_error,
                is_timeout=False,
                eligibility_status=status,
                raw_output=raw_out,
                sanitized_output=san_out,
                duration_seconds=round(duration, 3),
            )

    def list_tasks_summary(self) -> List[Dict[str, Any]]:
        """Return a lightweight list of summary records for all discovered tasks."""
        summaries = []
        for t in self.discover_tasks():
            summaries.append({
                "task_id": t.task_id,
                "program_name": t.program_name,
                "target_file": t.target_file,
                "test_file": t.evaluator_test_files[0] if t.evaluator_test_files else "",
                "agent_visible_count": len(t.agent_visible_files),
                "evaluator_support_count": len(t.evaluator_support_files),
                "is_graph_based": t.result_metadata.get("is_graph_based", False),
                "baseline_status": t.baseline_status,
                "eligibility_status": t.eligibility_status,
            })
        return summaries

