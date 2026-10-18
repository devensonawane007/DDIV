"""Deterministic unit tests for Phase 6 DDIV recovery reliability enhancements.

Verifies:
1. CPU-shares math & fallback logic.
2. Static AST detection of undefined local variables (UNDEFINED_VARIABLE).
3. Explicit detection of nonexistent anchors with candidate return diagnostics (ANCHOR_NOT_FOUND).
4. Indentation error categorization (SYNTAX_ERROR_INDENTATION).
5. Valid source-grounded repair synthesis (return avail_cpu or 1).
6. Source grounding extraction and directive formatting.
7. Invariant: invalid/empty patches are never marked resolved.
8. Anti-repetition tracking and negative constraints for structural failures.
"""

from __future__ import annotations

import ast
from pathlib import Path
import pytest

from evaluation.patch_builder import CodeModification
from evaluation.patch_manager import PatchManager
from recovery.failure_detector import FailureDetector, FailureType, GranularFailureType
from scripts.demo_patch_builder import DemoPatchBuilder
from scripts.v2_2_recovery_manager import (
    FailureDisambiguator,
    ProposalHistory,
    extract_source_grounding_context,
)

SAMPLE_RUN_PY = """\"\"\"Sample run module simulating pylint/lint/run.py.\"\"\"
from pathlib import Path

def _query_cpu() -> int | None:
    cpu_quota, avail_cpu = None, None
    if Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").is_file():
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", encoding="utf-8") as file:
            cpu_quota = int(file.read().rstrip())
    if cpu_quota and cpu_quota != -1 and Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").is_file():
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us", encoding="utf-8") as file:
            cpu_period = int(file.read().rstrip())
        avail_cpu = int(cpu_quota / cpu_period)
    elif Path("/sys/fs/cgroup/cpu/cpu.shares").is_file():
        with open("/sys/fs/cgroup/cpu/cpu.shares", encoding="utf-8") as file:
            cpu_shares = int(file.read().rstrip())
        avail_cpu = int(cpu_shares / 1024)
    return avail_cpu


def _cpu_count() -> int:
    return _query_cpu() or 1
"""


def test_01_cpu_shares_fallback_math():
    """Test 1: CPU-shares calculation with small values (e.g. cpu.shares = 2).

    Unprotected calculation evaluates to int(2 / 1024) == 0, causing multiprocessing crashes.
    The fallback logic (avail_cpu or 1) guarantees a minimum of 1.
    """
    cpu_shares = 2
    raw_avail_cpu = int(cpu_shares / 1024)
    assert raw_avail_cpu == 0, "Unprotected integer division evaluates to 0"

    # Historical repair
    repaired_avail_cpu = raw_avail_cpu or 1
    assert repaired_avail_cpu == 1, "Fallback 'or 1' ensures at least 1 core"

    # Standard branch clamp
    clamped_avail_cpu = max(1, raw_avail_cpu)
    assert clamped_avail_cpu == 1, "max(1, ...) also guarantees at least 1 core"


def test_02_undefined_variable_rejection(tmp_path: Path):
    """Test 2: Reject proposal referencing undefined local variable 'result' before assignment.

    Full DDIV Attempt 2 failed at runtime with UnboundLocalError due to:
        result = max(1, result)
    DemoPatchBuilder must catch this statically before test execution.
    """
    file_p = tmp_path / "run.py"
    file_p.write_text(SAMPLE_RUN_PY, encoding="utf-8")

    builder = DemoPatchBuilder()
    mods = [
        CodeModification(
            path="run.py",
            operation="insert_before",
            anchor="return avail_cpu",
            code="    result = max(1, result)",
            reason="Attempting to clamp hallucinated variable",
        )
    ]
    res = builder.build_patch(mods, base_dir=tmp_path)
    assert res.success is False
    assert res.error_category == "UNDEFINED_VARIABLE"
    assert "result" in res.error_message
    assert "_query_cpu" in res.error_message


def test_03_nonexistent_anchor_rejection_with_candidate_diagnostics(tmp_path: Path):
    """Test 3: Reject proposal with nonexistent anchor 'return result'.

    DemoPatchBuilder must return ANCHOR_NOT_FOUND and list candidate return statements
    actually found in the scope (e.g. 'return avail_cpu').
    """
    file_p = tmp_path / "run.py"
    file_p.write_text(SAMPLE_RUN_PY, encoding="utf-8")

    builder = DemoPatchBuilder()
    mods = [
        CodeModification(
            path="run.py",
            operation="replace",
            anchor="return result",
            code="return max(1, result)",
            reason="Replacing hallucinated anchor",
        )
    ]
    res = builder.build_patch(mods, base_dir=tmp_path)
    assert res.success is False
    assert res.error_category == "ANCHOR_NOT_FOUND"
    assert "return result" in res.error_message
    assert "return avail_cpu" in res.error_message, "Must supply candidate return statement from source"


def test_04_indentation_error_categorization(tmp_path: Path):
    """Test 4: Disambiguate IndentationError as SYNTAX_ERROR_INDENTATION.

    RETRY_ONLY failed with 12 spaces in an 8-space block.
    DemoPatchBuilder must categorize this specifically so supervisor can direct indentation fix.
    """
    file_p = tmp_path / "run.py"
    file_p.write_text(SAMPLE_RUN_PY, encoding="utf-8")

    builder = DemoPatchBuilder()
    # Inserting badly indented block directly
    mods = [
        CodeModification(
            path="run.py",
            operation="insert_before",
            anchor="return avail_cpu",
            code="            avail_cpu = 1\n    avail_cpu = 2",
            reason="Bad indentation level",
        )
    ]
    res = builder.build_patch(mods, base_dir=tmp_path)
    assert res.success is False
    assert res.error_category == "SYNTAX_ERROR_INDENTATION"
    assert "indent" in res.error_message.lower()


def test_05_valid_source_grounded_patch_synthesis(tmp_path: Path):
    """Test 5: Verify valid source-grounded modification builds and applies cleanly.

    Historical repair: replace 'return avail_cpu' with 'return avail_cpu or 1'.
    """
    file_p = tmp_path / "run.py"
    file_p.write_text(SAMPLE_RUN_PY, encoding="utf-8")

    builder = DemoPatchBuilder()
    mods = [
        CodeModification(
            path="run.py",
            operation="replace",
            anchor="    return avail_cpu",
            code="    return avail_cpu or 1",
            reason="Fix CPU count calculation for containers",
        )
    ]
    res = builder.build_patch(mods, base_dir=tmp_path)
    assert res.success is True, res.error_message
    assert res.unified_diff, "Diff should not be empty"

    pmgr = PatchManager()
    apply_res = pmgr.apply_patch(tmp_path, res.unified_diff)
    assert apply_res.is_success is True

    patched_content = file_p.read_text(encoding="utf-8")
    ast.parse(patched_content)
    assert "return avail_cpu or 1" in patched_content


def test_06_source_grounding_context_extraction():
    """Test 6: Verify extract_source_grounding_context extracts real symbols and return statements."""
    grounding = extract_source_grounding_context(
        workspace_path=None,
        target_file="pylint/lint/run.py",
        symbol_hint="_query_cpu",
        file_content=SAMPLE_RUN_PY,
    )
    assert "CRITICAL VERIFIED SOURCE GROUNDING" in grounding
    assert "avail_cpu" in grounding
    assert "cpu_shares" in grounding
    assert "return avail_cpu" in grounding
    assert "Do NOT reference placeholder variable names (e.g. 'result', 'temp', 'data')" in grounding
    assert "return avail_cpu" in grounding


def test_07_no_false_success_on_invalid_or_empty_patch():
    """Test 7: Invariant: Invalid or empty patch is never marked as RESOLVED."""
    detector = FailureDetector()
    det_res = detector.evaluate(
        patch_valid=False,
        patch_applied=False,
        test_passed=False,
        test_output="Patch not applied",
        coder_error_code="UNDEFINED_VARIABLE",
        coder_error_detail="Undefined local variable 'result'",
    )
    assert det_res.is_failure is True
    assert det_res.candidate_failure_type == FailureType.F3

    norm_cat, exp = FailureDisambiguator.classify(
        patch_valid=False,
        patch_applied=False,
        pb_error_category="UNDEFINED_VARIABLE",
        pb_error_message="Undefined local variable 'result'",
        coder_error_code="UNDEFINED_VARIABLE",
        coder_error_msg="Undefined local variable 'result'",
    )
    assert norm_cat == "UNDEFINED_VARIABLE"
    assert "result" in exp


def test_08_anti_repetition_blocking_and_negative_constraints():
    """Test 8: Verify ProposalHistory detects repeated invalid anchors and formats negative constraints."""
    history = ProposalHistory()
    history.record_attempt(
        attempt=1,
        path="pylint/lint/run.py",
        operation="replace",
        anchor="return result",
        code="return max(1, result)",
        target_symbol="_query_cpu",
        error_category="ANCHOR_NOT_FOUND",
        error_detail="Anchor not found in 'pylint/lint/run.py': return result",
    )

    # Repeating the same missing anchor must be flagged
    rep_att = history.is_repeated(
        path="pylint/lint/run.py",
        operation="replace",
        anchor="return result",
        code="return max(1, result)",
        target_symbol="_query_cpu",
    )
    assert rep_att == 1, "Must detect attempt 1 as repeated proposal"

    # Negative constraints must specifically direct Coder not to repeat the nonexistent anchor
    constraints = history.format_negative_constraints()
    assert "CRITICAL DIRECTIVE: DO NOT REPEAT PREVIOUS FAILED PROPOSALS:" in constraints
    assert "[ANCHOR_NOT_FOUND]" in constraints
    assert "You MUST NOT reuse this anchor. Copy an exact anchor line verbatim from the target source file." in constraints

    # Record second attempt with undefined variable
    history.record_attempt(
        attempt=2,
        path="pylint/lint/run.py",
        operation="insert_before",
        anchor="return avail_cpu",
        code="result = max(1, result)",
        target_symbol="_query_cpu",
        error_category="UNDEFINED_VARIABLE",
        error_detail="Undefined local variable 'result' referenced before assignment",
    )
    constraints_att2 = history.format_negative_constraints()
    assert "[UNDEFINED_VARIABLE]" in constraints_att2
    assert "You MUST NOT introduce undefined variables. Only use variables verified in the function scope." in constraints_att2
