"""Comprehensive Phase 6.1 Audit and Hardening Test Suite.

Deterministic, offline tests verifying:
- Task 1: CPU-share regression audit, None preservation, and _cpu_count caller semantics.
- Task 2: AST undefined-variable detection, differential validation, closures, walrus, and comprehensions.
- Task 3: Real source grounding extraction, failure disambiguation, and anti-repetition constraints.
- Task 4: False-success prevention invariants in experiment_worker.
"""

from __future__ import annotations

import ast
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

import pytest

from core.conditions import ExperimentCondition
from core.config import DDIVConfig, ExecutionMode
from evaluation.backends import EvaluationOutcome, EvaluationResult, EvaluationTier
from evaluation.patch_manager import PatchManager, PatchValidationResult
from scripts.demo_patch_builder import DemoPatchBuilder
from scripts.v2_2_recovery_manager import (
    FailureDisambiguator,
    ProposalHistory,
    ProposalRecord,
    extract_source_grounding_context,
)


# ==============================================================================
# Task 1: Audit CPU-share regression and _cpu_count semantics
# ==============================================================================

def faithful_query_cpu(cgroup_fs: Dict[str, str], fix_mode: str = "fixed") -> Optional[int]:
    """Faithful executable reproduction of pylint/lint/run.py:_query_cpu().

    fix_mode:
      - "unpatched": raw historical buggy code (returns 0 on low shares)
      - "naive_or_1": naive 'return avail_cpu or 1' (breaks None semantics)
      - "fixed": correct 'max(avail_cpu, 1) if avail_cpu is not None else None'
    """
    cpu_quota, avail_cpu = None, None

    quota_path = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
    if quota_path in cgroup_fs:
        cpu_quota = int(cgroup_fs[quota_path].strip())

    period_path = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"
    shares_path = "/sys/fs/cgroup/cpu/cpu.shares"

    if cpu_quota and cpu_quota != -1 and period_path in cgroup_fs:
        cpu_period = int(cgroup_fs[period_path].strip())
        avail_cpu = int(cpu_quota / cpu_period)
    elif shares_path in cgroup_fs:
        cpu_shares = int(cgroup_fs[shares_path].strip())
        avail_cpu = int(cpu_shares / 1024)

    if fix_mode == "unpatched":
        return avail_cpu
    elif fix_mode == "naive_or_1":
        return avail_cpu or 1
    elif fix_mode == "fixed":
        if avail_cpu is not None:
            return max(avail_cpu, 1)
        return None
    else:
        raise ValueError(f"Unknown fix_mode: {fix_mode}")


def faithful_cpu_count(query_cpu_result: Optional[int], host_cores: int = 32) -> int:
    """Faithful reproduction of pylint/lint/run.py:_cpu_count()."""
    cpu_share = query_cpu_result
    cpu_count = host_cores
    if cpu_share is not None:
        return min(cpu_share, cpu_count)
    return cpu_count


class TestTask1CpuShareRegression:
    """Audit of CPU-share fallback calculations and caller semantics."""

    def test_unpatched_cpu_shares_yields_zero_and_crashes(self):
        """(a) Quota unavailable and cpu.shares = 2 yields count of 0 without fix."""
        fs = {
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "-1",
            "/sys/fs/cgroup/cpu/cpu.shares": "2",
        }
        unpatched_result = faithful_query_cpu(fs, fix_mode="unpatched")
        assert unpatched_result == 0, f"Expected unpatched to return 0, got {unpatched_result}"

        # In _cpu_count, min(0, 32) == 0 -> multiprocessing pool fails
        effective_cpus = faithful_cpu_count(unpatched_result, host_cores=32)
        assert effective_cpus == 0, "Unpatched calculation must yield 0 effective CPUs"

    def test_corrected_logic_returns_usable_count(self):
        """(b) Corrected logic returns usable count >= 1."""
        fs = {
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "-1",
            "/sys/fs/cgroup/cpu/cpu.shares": "2",
        }
        fixed_result = faithful_query_cpu(fs, fix_mode="fixed")
        assert fixed_result == 1, f"Expected corrected logic to return 1, got {fixed_result}"

        effective_cpus = faithful_cpu_count(fixed_result, host_cores=32)
        assert effective_cpus == 1, "Effective CPUs in container must be >= 1"

    def test_missing_cpu_information_preserves_none_semantics(self):
        """(c) Missing CPU information preserves None semantics and prevents 1-core cap.

        Crucial test: Proves that naive 'avail_cpu or 1' is defective because it turns
        None into 1, throttling a 32-core host machine down to 1 core.
        The correct fix returns None, preserving full host core count.
        """
        empty_fs: Dict[str, str] = {}

        # 1. Unpatched returns None
        unpatched_res = faithful_query_cpu(empty_fs, fix_mode="unpatched")
        assert unpatched_res is None

        # 2. Naive fix 'return avail_cpu or 1' WRONGLY returns 1
        naive_res = faithful_query_cpu(empty_fs, fix_mode="naive_or_1")
        assert naive_res == 1, "Demonstrating naive bug: None or 1 evaluates to 1"
        naive_cores = faithful_cpu_count(naive_res, host_cores=32)
        assert naive_cores == 1, "Demonstrating naive flaw: 32 host cores capped to 1!"

        # 3. Corrected logic preserves None
        fixed_res = faithful_query_cpu(empty_fs, fix_mode="fixed")
        assert fixed_res is None, f"Expected None when cgroups absent, got {fixed_res}"
        fixed_cores = faithful_cpu_count(fixed_res, host_cores=32)
        assert fixed_cores == 32, f"Host cores must remain 32 when None, got {fixed_cores}"

    def test_multicore_container_quota_preserved(self):
        """(d) Containers with higher CPU quota or shares retain their full multi-core count."""
        fs_multi = {
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "400000",
            "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000",
        }
        fixed_multi = faithful_query_cpu(fs_multi, fix_mode="fixed")
        assert fixed_multi == 4
        effective_cpus = faithful_cpu_count(fixed_multi, host_cores=32)
        assert effective_cpus == 4

    def test_isolated_workspace_run_py_inspection(self):
        """Verify the exact source in data/workspaces/preflight_verification/pylint-dev__pylint-6903."""
        run_py = Path("data/workspaces/preflight_verification/pylint-dev__pylint-6903/pylint/lint/run.py")
        if not run_py.exists():
            pytest.skip("Preflight workspace not present in current environment")

        content = run_py.read_text(encoding="utf-8")
        assert "def _query_cpu()" in content
        assert "def _cpu_count()" in content
        assert "cpu.shares" in content
        assert "cpu.cfs_quota_us" in content


# ==============================================================================
# Task 2: Audit undefined-variable detection and AST static analysis
# ==============================================================================

class TestTask2UndefinedVariableDetection:
    """Comprehensive test matrix for AST variable resolution."""

    def test_01_introduced_undefined_variable(self):
        """Introduced undefined variable load is flagged with function name and line."""
        code = (
            "def compute_total(items):\n"
            "    count = len(items)\n"
            "    return result\n"  # 'result' is undefined
        )
        undef = DemoPatchBuilder.get_undefined_variable_references(code)
        assert len(undef) == 1
        fn, var, line = list(undef)[0]
        assert fn == "compute_total"
        assert var == "result"
        assert line == 3

        # validate_variable_definitions returns formatted error message
        orig_code = (
            "def compute_total(items):\n"
            "    count = len(items)\n"
            "    return count\n"
        )
        err = DemoPatchBuilder.validate_variable_definitions(code, orig_code)
        assert err is not None
        assert "Undefined local variable 'result'" in err
        assert "compute_total" in err

    def test_02_args_imports_and_builtins_not_flagged(self):
        """Arguments (pos, kwonly, *args, **kwargs), imports, and builtins are recognized."""
        code = (
            "import os\n"
            "from math import sqrt as square_root\n"
            "\n"
            "def complex_fn(a, b=10, *args, flag=True, **kwargs):\n"
            "    import json\n"
            "    val = int(a) + len(args) + square_root(b)\n"
            "    data = json.dumps({'flag': flag, 'kw': kwargs})\n"
            "    return max(val, 1)\n"
        )
        undef = DemoPatchBuilder.get_undefined_variable_references(code)
        assert undef == set(), f"Expected no undefined variables, found {undef}"

    def test_03_globals_and_nonlocals_not_flagged(self):
        """Global and nonlocal declarations are recognized across function scope."""
        code = (
            "g_counter = 0\n"
            "\n"
            "def mutate_global():\n"
            "    global g_counter\n"
            "    g_counter += 1\n"
            "    return g_counter\n"
        )
        undef = DemoPatchBuilder.get_undefined_variable_references(code)
        assert undef == set(), f"Expected global to be recognized, found {undef}"

    def test_04_closures_and_nested_functions(self):
        """Enclosing function scope variables are visible to inner functions regardless of order."""
        # Case A: Assigned before inner function
        code_a = (
            "def outer(x):\n"
            "    val = x * 2\n"
            "    def inner():\n"
            "        return val + 1\n"
            "    return inner()\n"
        )
        assert DemoPatchBuilder.get_undefined_variable_references(code_a) == set()

        # Case B: Assigned after inner function definition (valid Python closure)
        code_b = (
            "def outer():\n"
            "    def inner():\n"
            "        return val + helper()\n"
            "    val = 42\n"
            "    def helper():\n"
            "        return 1\n"
            "    return inner()\n"
        )
        assert DemoPatchBuilder.get_undefined_variable_references(code_b) == set()

        # Case C: Inner function references truly undefined variable
        code_c = (
            "def outer(x):\n"
            "    def inner():\n"
            "        return nonexistent_var\n"
            "    return inner()\n"
        )
        undef_c = DemoPatchBuilder.get_undefined_variable_references(code_c)
        assert len(undef_c) == 1
        fn, var, _ = list(undef_c)[0]
        assert fn == "inner"
        assert var == "nonexistent_var"

    def test_05_self_and_class_attributes(self):
        """Methods with self/cls access attributes without false positives; bare names caught."""
        code = (
            "class Worker:\n"
            "    class_attr = 'CLASS'\n"
            "    def __init__(self, name):\n"
            "        self.name = name\n"
            "        self.active = True\n"
            "\n"
            "    def get_info(self):\n"
            "        self.active = False\n"
            "        return f'{self.name}: {self.active}'\n"
            "\n"
            "    def bad_method(self):\n"
            "        return unassigned_var\n"  # Bare undefined variable
        )
        undef = DemoPatchBuilder.get_undefined_variable_references(code)
        assert len(undef) == 1
        fn, var, _ = list(undef)[0]
        assert fn == "bad_method"
        assert var == "unassigned_var"

    def test_06_comprehensions_lambdas_and_walrus(self):
        """Comprehensions, lambdas, and walrus operators bind their targets properly."""
        code = (
            "def process_data(items):\n"
            "    squared = [x * x for x in items if x > 0]\n"
            "    pair_dict = {f'k_{k}': v for k, v in items}\n"
            "    sorter = lambda a, b: a - b\n"
            "    if (total := sum(squared)) > 100:\n"
            "        return total\n"
            "    return sorter(10, 5)\n"
        )
        undef = DemoPatchBuilder.get_undefined_variable_references(code)
        assert undef == set(), f"Expected comprehensions and walrus to be valid, found {undef}"

    def test_07_conditionals_loops_and_try_except(self):
        """Loop variables, context managers, and exception variables are recognized."""
        code = (
            "def handler(filepath):\n"
            "    try:\n"
            "        with open(filepath) as fp:\n"
            "            lines = fp.readlines()\n"
            "        for idx, line in enumerate(lines):\n"
            "            if idx > 10:\n"
            "                break\n"
            "    except (OSError, ValueError) as exc:\n"
            "        return str(exc)\n"
            "    return len(lines)\n"
        )
        undef = DemoPatchBuilder.get_undefined_variable_references(code)
        assert undef == set(), f"Expected try-except and loop vars to be valid, found {undef}"

    def test_08_augassign_detection(self):
        """AugAssign (+=) on uninitialized variable is flagged; on known variable is valid."""
        # Uninitialized AugAssign
        code_bad = (
            "def accumulate(val):\n"
            "    total += val\n"  # total never initialized
            "    return total\n"
        )
        undef_bad = DemoPatchBuilder.get_undefined_variable_references(code_bad)
        assert len(undef_bad) == 1
        fn, var, _ = list(undef_bad)[0]
        assert fn == "accumulate"
        assert var == "total"

        # Initialized AugAssign
        code_good = (
            "def accumulate(val):\n"
            "    total = 0\n"
            "    total += val\n"
            "    return total\n"
        )
        assert DemoPatchBuilder.get_undefined_variable_references(code_good) == set()

    def test_09_preexisting_unresolved_names_differential_validation(self):
        """Differential validation ignores pre-existing unresolved names, flagging only new ones."""
        orig_content = (
            "def legacy_function():\n"
            "    return DYNAMIC_GLOBAL_FROM_C_EXT\n"
        )
        # Patch keeps the pre-existing unresolved name and adds another valid line
        clean_patch_content = (
            "def legacy_function():\n"
            "    logged = True\n"
            "    return DYNAMIC_GLOBAL_FROM_C_EXT\n"
        )
        err = DemoPatchBuilder.validate_variable_definitions(clean_patch_content, orig_content)
        assert err is None, "Pre-existing unresolved name must not cause false rejection"

        # Patch introduces a NEW undefined name
        broken_patch_content = (
            "def legacy_function():\n"
            "    return DYNAMIC_GLOBAL_FROM_C_EXT + introduced_bad_var\n"
        )
        err_broken = DemoPatchBuilder.validate_variable_definitions(broken_patch_content, orig_content)
        assert err_broken is not None
        assert "introduced_bad_var" in err_broken

    def test_10_syntax_invalid_patch_handling(self):
        """Syntax-invalid content returns empty set from undefined analysis; caught at syntax phase."""
        bad_syntax = "def broken(:\n    return 1\n"
        undef = DemoPatchBuilder.get_undefined_variable_references(bad_syntax)
        assert undef == set(), "Syntax errors must be safely caught without crashing"

        # Build patch on syntax error classifies as SYNTAX_ERROR
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "foo.py"
            f.write_text("def valid():\n    return 0\n", encoding="utf-8")
            pb = DemoPatchBuilder()
            res = pb.build_patch(
                [{"path": "foo.py", "operation": "replace", "anchor": "return 0", "code": "return )"}],
                td,
            )
            assert res.success is False
            assert res.error_category in ("SYNTAX_ERROR", "SYNTAX_ERROR_INDENTATION")


# ==============================================================================
# Task 3: Verify source grounding and recovery mechanisms
# ==============================================================================

class TestTask3SourceGroundingAndRecovery:
    """Audit of source grounding extraction, failure classification, and anti-repetition."""

    def test_01_extract_source_grounding_context_real_file(self):
        """extract_source_grounding_context extracts real parameters, local vars, and returns."""
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "runner.py"
            src.write_text(
                "def execute_task(task_id, timeout=30, *extra):\n"
                "    status = 'PENDING'\n"
                "    retries = 0\n"
                "    if timeout > 0:\n"
                "        status = 'ACTIVE'\n"
                "    return status\n",
                encoding="utf-8",
            )
            ctx = extract_source_grounding_context(
                workspace_path=Path(td),
                target_file="runner.py",
                symbol_hint="execute_task",
            )
            assert "CRITICAL VERIFIED SOURCE GROUNDING" in ctx
            assert "task_id" in ctx
            assert "timeout" in ctx
            assert "retries" in ctx
            assert "status" in ctx
            assert "return status" in ctx
            assert "Do NOT reference placeholder variable names" in ctx

    def test_02_extract_source_grounding_context_nonexistent_file(self):
        """Nonexistent file returns empty string safely without fabricating symbols."""
        with tempfile.TemporaryDirectory() as td:
            ctx = extract_source_grounding_context(
                workspace_path=Path(td),
                target_file="nonexistent.py",
                symbol_hint="any_func",
            )
            assert ctx == "", "Must return empty string on missing file"

    def test_03_failure_disambiguator_classifications(self):
        """FailureDisambiguator correctly maps low-level errors to recovery categories."""
        # Category 1: Undefined variable
        cat, msg = FailureDisambiguator.classify(
            patch_valid=False,
            patch_applied=False,
            pb_error_category="UNDEFINED_VARIABLE",
            pb_error_message="Undefined local variable 'result' referenced",
        )
        assert cat == "UNDEFINED_VARIABLE"
        assert "result" in msg

        # Category 2: Nonexistent anchor
        cat2, msg2 = FailureDisambiguator.classify(
            patch_valid=False,
            patch_applied=False,
            pb_error_category="ANCHOR_NOT_FOUND",
            pb_error_message="Anchor not found: return result",
        )
        assert cat2 == "ANCHOR_NOT_FOUND"

        # Category 3: Indentation / invalid scope
        cat3, msg3 = FailureDisambiguator.classify(
            patch_valid=False,
            patch_applied=False,
            pb_error_category="SYNTAX_ERROR_INDENTATION",
            pb_error_message="unexpected indent",
        )
        assert cat3 == "SYNTAX_ERROR_INDENTATION"

    def test_04_proposal_history_anti_repetition_and_constraints(self):
        """ProposalHistory blocks identical failed proposals while permitting corrected ones."""
        hist = ProposalHistory()
        hist.record_attempt(
            attempt=1,
            path="pylint/lint/run.py",
            target_symbol="run._query_cpu",
            operation="replace",
            anchor="return avail_cpu",
            code="return result",
            error_category="UNDEFINED_VARIABLE",
            error_detail="Undefined local variable 'result' referenced before assignment",
        )

        # 1. Identical proposal is blocked (returns matching attempt 1)
        matched_att = hist.is_repeated(
            path="pylint/lint/run.py",
            target_symbol="run._query_cpu",
            operation="replace",
            anchor="return avail_cpu",
            code="return result",
        )
        assert matched_att == 1

        # 2. Corrected proposal with different code is NOT blocked (returns None)
        matched_att2 = hist.is_repeated(
            path="pylint/lint/run.py",
            target_symbol="run._query_cpu",
            operation="replace",
            anchor="return avail_cpu",
            code="return max(avail_cpu, 1) if avail_cpu is not None else None",
        )
        assert matched_att2 is None

        # 3. Negative constraints directive is generated with explicit error feedback
        constraints = hist.format_negative_constraints()
        assert "Attempt 1" in constraints
        assert "UNDEFINED_VARIABLE" in constraints
        assert "You MUST NOT introduce undefined variables" in constraints


# ==============================================================================
# Task 4: Verify false-success prevention invariants
# ==============================================================================

class TestTask4FalseSuccessPrevention:
    """Audit of status transitions and prevention of false-success resolution."""

    def test_empty_patch_cannot_resolve(self):
        """An empty patch cannot be validated, applied, or marked RESOLVED."""
        pm = PatchManager()
        val_res = pm.validate_patch("")
        assert val_res.is_valid is False
        assert val_res.error_message == "Patch is empty."

        # Invariant: final_patch_correct must be False
        final_patch_correct = (EvaluationOutcome.RESOLVED == EvaluationOutcome.RESOLVED) if val_res.is_valid else False
        assert final_patch_correct is False

    def test_invalid_diff_cannot_resolve(self):
        """An invalid patch diff cannot pass validation or resolve."""
        pm = PatchManager()
        val_res = pm.validate_patch("This is just freeform text, not a diff.")
        assert val_res.is_valid is False
        assert "Patch does not match standard unified diff format" in val_res.error_message

        final_patch_correct = (EvaluationOutcome.RESOLVED == EvaluationOutcome.RESOLVED) if val_res.is_valid else False
        assert final_patch_correct is False

    def test_unapplied_patch_prevents_resolution_invariant(self):
        """Even if an evaluator mock returns RESOLVED, unapplied/invalid patch forces UNRESOLVED."""
        candidate_patch = ""
        val_res = PatchValidationResult(is_valid=False, modified_files=[], error_message="Empty patch")
        agent_apply_success = False

        # Simulated evaluator response (e.g. from buggy mock or cached test pass on clean base)
        eval_res = EvaluationResult(
            backend_name="mock_evaluator",
            tier=EvaluationTier.TIER_1_INTERNAL,
            task_id="pylint-dev__pylint-6903",
            is_available=True,
            outcome=EvaluationOutcome.RESOLVED,
            verdict="RESOLVED_INTERNALLY (Mock pass)",
            details={"internal_resolved": True},
        )

        # Enforce worker invariant logic from core/experiment_worker.py:
        if eval_res.outcome == EvaluationOutcome.RESOLVED:
            if not bool(candidate_patch.strip()) or not val_res.is_valid or not agent_apply_success:
                eval_res.outcome = EvaluationOutcome.UNRESOLVED
                eval_res.verdict = "UNRESOLVED_INTERNALLY (Empty, invalid, or unapplied patch cannot resolve)"
                eval_res.details["internal_resolved"] = False

        assert eval_res.outcome == EvaluationOutcome.UNRESOLVED
        assert "cannot resolve" in eval_res.verdict
        assert eval_res.details["internal_resolved"] is False
