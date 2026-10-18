"""Offline integration tests for QuixBugs benchmark adapter.

Tests:
1. Synthetic and real task discovery and stable ID generation.
2. Mapping programs to test modules and support files.
3. Workspace creation, isolation, and reference solution exclusion.
4. Patch validation, application, and resolution verification.
5. Prevention of false RESOLVED status on empty or invalid patches.
6. Preservation of individual passing and failing test outcomes.
7. Timeout protection on infinite loops.
8. Baseline eligibility checking.
9. Verification that task listing executes offline with zero LLM calls.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
import pytest

from evaluation.quixbugs_adapter import (
    QuixBugsAdapter,
    QuixBugsTask,
    QuixBugsEvaluationResult,
    QuixBugsBaselineResult,
    GRAPH_BASED_ALGORITHMS,
)


@pytest.fixture
def synthetic_quixbugs_dir(tmp_path: Path) -> Path:
    """Create a self-contained, minimal synthetic QuixBugs repository fixture."""
    qb = tmp_path / "quixbugs_synth"
    (qb / "python_programs").mkdir(parents=True)
    (qb / "python_testcases").mkdir(parents=True)
    (qb / "json_testcases").mkdir(parents=True)
    (qb / "correct_python_programs").mkdir(parents=True)

    # Program 1: algo_one (buggy math)
    prog1 = qb / "python_programs/algo_one.py"
    prog1.write_text("def algo_one(x):\n    return x\n", encoding="utf-8")

    # Correct Program 1 (reference - must be protected)
    cprog1 = qb / "correct_python_programs/algo_one.py"
    cprog1.write_text("def algo_one(x):\n    return x * 2\n", encoding="utf-8")

    # Test 1: test_algo_one
    test1 = qb / "python_testcases/test_algo_one.py"
    test1.write_text(
        "from python_programs.algo_one import algo_one\n\n"
        "def test_passing():\n"
        "    assert algo_one(0) == 0\n\n"
        "def test_failing():\n"
        "    assert algo_one(2) == 4\n",
        encoding="utf-8",
    )

    # Program 2: breadth_first_search (graph-based)
    prog2 = qb / "python_programs/breadth_first_search.py"
    prog2.write_text("def breadth_first_search(start, goal):\n    return False\n", encoding="utf-8")

    # Node helpers
    node_prog = qb / "python_programs/node.py"
    node_prog.write_text("class Node:\n    def __init__(self, val): self.val = val\n", encoding="utf-8")
    node_test = qb / "python_testcases/node.py"
    node_test.write_text("class Node:\n    def __init__(self, val): self.val = val\n", encoding="utf-8")

    test2 = qb / "python_testcases/test_breadth_first_search.py"
    test2.write_text(
        "from python_programs.breadth_first_search import breadth_first_search\n"
        "from node import Node\n\n"
        "def test_bfs():\n"
        "    assert not breadth_first_search(Node('A'), Node('B'))\n",
        encoding="utf-8",
    )

    # Conftest
    (qb / "conftest.py").write_text("# synthetic conftest\n", encoding="utf-8")

    return qb


def test_task_discovery_synthetic(synthetic_quixbugs_dir: Path):
    """Verify task discovery on a controlled synthetic benchmark directory."""
    adapter = QuixBugsAdapter(quixbugs_root=synthetic_quixbugs_dir)
    assert adapter.is_available()

    tasks = adapter.discover_tasks()
    assert len(tasks) == 2

    task_map = {t.program_name: t for t in tasks}
    assert "algo_one" in task_map
    assert "breadth_first_search" in task_map

    t1 = task_map["algo_one"]
    assert t1.task_id == "quixbugs-python-algo_one"
    assert t1.target_file == "python_programs/algo_one.py"
    assert t1.test_files == ["python_testcases/test_algo_one.py"]
    assert "conftest.py" in t1.support_files
    assert not t1.result_metadata["is_graph_based"]

    t2 = task_map["breadth_first_search"]
    assert t2.task_id == "quixbugs-python-breadth_first_search"
    assert t2.result_metadata["is_graph_based"]
    assert "python_programs/node.py" in t2.support_files
    assert "python_testcases/node.py" in t2.support_files


def test_task_discovery_real_dataset():
    """Verify discovery against the actual checkout at data/quixbugs."""
    adapter = QuixBugsAdapter(quixbugs_root="D:/DDIV/data/quixbugs")
    if not adapter.is_available():
        pytest.skip("QuixBugs checkout not found at D:/DDIV/data/quixbugs")

    tasks = adapter.discover_tasks()
    assert len(tasks) == 40, f"Expected exactly 40 Python tasks, got {len(tasks)}"

    task_ids = [t.task_id for t in tasks]
    assert len(set(task_ids)) == 40, "Task IDs must be 100% unique"
    assert all(tid.startswith("quixbugs-python-") for tid in task_ids)

    graph_tasks = [t for t in tasks if t.result_metadata.get("is_graph_based")]
    assert len(graph_tasks) == len(GRAPH_BASED_ALGORITHMS)


def test_workspace_creation_isolation_and_reference_exclusion(synthetic_quixbugs_dir: Path, tmp_path: Path):
    """Verify that agent workspace is created cleanly and NEVER includes reference solutions."""
    adapter = QuixBugsAdapter(quixbugs_root=synthetic_quixbugs_dir)
    ws_dir = tmp_path / "agent_ws_algo_one"

    created = adapter.create_task_workspace("quixbugs-python-algo_one", ws_dir, init_git=True)
    assert created.resolve() == ws_dir.resolve()

    # Target file must exist
    assert (ws_dir / "python_programs/algo_one.py").exists()

    # Ground-truth isolation: tests and test fixtures must NEVER be in agent workspace
    assert not (ws_dir / "python_testcases").exists()
    assert not (ws_dir / "json_testcases").exists()
    assert not (ws_dir / "conftest.py").exists()

    # CRITICAL: Reference solution must NEVER be present
    assert not (ws_dir / "correct_python_programs").exists()
    assert not (ws_dir / "correct_python_programs/algo_one.py").exists()

    # Check Git repo initialized in workspace
    assert (ws_dir / ".git").is_dir()


def test_reference_leak_prevention_gate(synthetic_quixbugs_dir: Path, tmp_path: Path, monkeypatch):
    """Verify that workspace creation fails closed if reference solutions somehow leak."""
    adapter = QuixBugsAdapter(quixbugs_root=synthetic_quixbugs_dir)
    ws_dir = tmp_path / "leaky_ws"

    # Simulate a bug where correct_python_programs is copied
    original_copy = shutil.copy2

    def leaky_copy(src, dst):
        res = original_copy(src, dst)
        # Maliciously create forbidden dir in destination
        forbidden = Path(dst).parent.parent / "correct_python_programs"
        forbidden.mkdir(parents=True, exist_ok=True)
        (forbidden / "leak.py").write_text("forbidden", encoding="utf-8")
        return res

    monkeypatch.setattr(shutil, "copy2", leaky_copy)

    with pytest.raises(RuntimeError, match="CRITICAL ISOLATION BREACH"):
        adapter.create_task_workspace("quixbugs-python-algo_one", ws_dir, init_git=False)


def test_patch_application_and_evaluation_resolved(synthetic_quixbugs_dir: Path, tmp_path: Path):
    """Verify that a valid bug-fixing patch is applied and evaluated to RESOLVED."""
    adapter = QuixBugsAdapter(quixbugs_root=synthetic_quixbugs_dir)
    ws_dir = tmp_path / "eval_ws"
    adapter.create_task_workspace("quixbugs-python-algo_one", ws_dir, init_git=True)
    task = adapter.get_task("quixbugs-python-algo_one")

    # Unified diff changing x to x * 2 in algo_one.py
    valid_patch = (
        "--- a/python_programs/algo_one.py\n"
        "+++ b/python_programs/algo_one.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def algo_one(x):\n"
        "-    return x\n"
        "+    return x * 2\n"
    )

    baseline = {
        "python_testcases/test_algo_one.py::test_passing": True,
        "python_testcases/test_algo_one.py::test_failing": False,
    }

    result = adapter.evaluate_patch(ws_dir, task, valid_patch, baseline_results=baseline)

    assert result.candidate_patch_applied
    assert result.resolved
    assert result.all_passed
    assert result.evaluation_verdict == "RESOLVED"
    assert result.failure_category == "NONE"
    assert "python_testcases/test_algo_one.py::test_failing" in result.fail_to_pass
    assert result.fail_to_pass["python_testcases/test_algo_one.py::test_failing"] is True


def test_reject_empty_and_invalid_patches(synthetic_quixbugs_dir: Path, tmp_path: Path):
    """Verify that empty, whitespace, and malformed patches are rejected without running tests."""
    adapter = QuixBugsAdapter(quixbugs_root=synthetic_quixbugs_dir)
    ws_dir = tmp_path / "reject_ws"
    adapter.create_task_workspace("quixbugs-python-algo_one", ws_dir, init_git=True)
    task = adapter.get_task("quixbugs-python-algo_one")

    # 1. Empty patch
    res_empty = adapter.evaluate_patch(ws_dir, task, "")
    assert not res_empty.candidate_patch_applied
    assert not res_empty.resolved
    assert res_empty.failure_category == "EMPTY_PATCH"

    # 2. Whitespace patch
    res_ws = adapter.evaluate_patch(ws_dir, task, "   \n\t  \n")
    assert not res_ws.candidate_patch_applied
    assert not res_ws.resolved
    assert res_ws.failure_category == "EMPTY_PATCH"

    # 3. Invalid format patch (lacks unified diff headers)
    res_inv = adapter.evaluate_patch(ws_dir, task, "def algo_one(x): return x + 1")
    assert not res_inv.candidate_patch_applied
    assert not res_inv.resolved
    assert res_inv.failure_category == "PATCH_FORMAT_INVALID"


def test_individual_test_outcome_preservation(synthetic_quixbugs_dir: Path, tmp_path: Path):
    """Verify that individual passing and failing test outcomes are preserved on unpatched code."""
    adapter = QuixBugsAdapter(quixbugs_root=synthetic_quixbugs_dir)
    ws_dir = tmp_path / "partial_ws"
    adapter.create_task_workspace("quixbugs-python-algo_one", ws_dir, init_git=True)
    task = adapter.get_task("quixbugs-python-algo_one")

    # A patch that modifies comment only, keeping the bug
    noop_patch = (
        "--- a/python_programs/algo_one.py\n"
        "+++ b/python_programs/algo_one.py\n"
        "@@ -1,2 +1,3 @@\n"
        "+# Just a comment\n"
        " def algo_one(x):\n"
        "     return x\n"
    )

    result = adapter.evaluate_patch(ws_dir, task, noop_patch)
    assert result.candidate_patch_applied
    assert not result.resolved
    assert not result.all_passed
    assert result.failure_category == "ASSERTION_FAILURE"

    # Individual test outcomes must be distinguished
    assert any("test_passing" in t for t in result.passed_tests)
    assert any("test_failing" in t for t in result.failed_tests)


def test_timeout_handling_infinite_loop(tmp_path: Path):
    """Verify that test evaluation handles infinite loops with a timeout and marks TIMEOUT."""
    qb = tmp_path / "quixbugs_loop"
    (qb / "python_programs").mkdir(parents=True)
    (qb / "python_testcases").mkdir(parents=True)
    (qb / "conftest.py").write_text("", encoding="utf-8")

    prog = qb / "python_programs/loop_algo.py"
    prog.write_text("def loop_algo():\n    while True:\n        pass\n", encoding="utf-8")

    test = qb / "python_testcases/test_loop_algo.py"
    test.write_text(
        "from python_programs.loop_algo import loop_algo\n"
        "def test_loop():\n"
        "    loop_algo()\n",
        encoding="utf-8",
    )

    adapter = QuixBugsAdapter(quixbugs_root=qb)
    ws_dir = tmp_path / "loop_ws"
    adapter.create_task_workspace("quixbugs-python-loop_algo", ws_dir, init_git=True)
    task = adapter.get_task("quixbugs-python-loop_algo")

    patch = (
        "--- a/python_programs/loop_algo.py\n"
        "+++ b/python_programs/loop_algo.py\n"
        "@@ -1,3 +1,4 @@\n"
        "+# comment\n"
        " def loop_algo():\n"
        "     while True:\n"
        "         pass\n"
    )

    # Use a small 2-second timeout
    result = adapter.evaluate_patch(ws_dir, task, patch, timeout=2)
    assert not result.resolved
    assert result.failure_category == "TIMEOUT"
    assert "Timeout" in result.evaluation_verdict


def test_baseline_eligibility_checker(synthetic_quixbugs_dir: Path):
    """Verify baseline defect reproduction check in isolated temporary workspace."""
    adapter = QuixBugsAdapter(quixbugs_root=synthetic_quixbugs_dir)
    task = adapter.get_task("quixbugs-python-algo_one")

    baseline = adapter.check_baseline_eligibility(task, timeout=5)
    assert baseline.has_reproduced_defect
    assert not baseline.has_environment_failure
    assert baseline.eligibility_status == "ELIGIBLE"
    assert any("test_failing" in t for t in baseline.failed_tests)
    assert any("test_passing" in t for t in baseline.passed_tests)


def test_task_listing_zero_llm_calls(synthetic_quixbugs_dir: Path):
    """Verify that listing tasks executes purely locally and offline."""
    adapter = QuixBugsAdapter(quixbugs_root=synthetic_quixbugs_dir)
    summaries = adapter.list_tasks_summary()
    assert len(summaries) == 2
    for s in summaries:
        assert s["baseline_status"] == "NOT_RUN"
        assert s["eligibility_status"] == "UNKNOWN"
