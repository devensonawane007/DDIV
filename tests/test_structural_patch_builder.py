"""Tests for AST-grounded patch construction, structural anchor resolution, and semantic anti-repetition."""

from pathlib import Path
import pytest

from evaluation.patch_builder import CodeModification
from scripts.demo_patch_builder import (
    ASTScopeRegion,
    DemoPatchBuilder,
    StructuralCodeModification,
    compute_source_fingerprint,
    find_ast_scopes,
    resolve_target_scope,
)
from scripts.v2_2_recovery_manager import (
    FailureDisambiguator,
    ProposalHistory,
    are_codes_ast_equivalent,
)

SAMPLE_MULTI_CLASS_MODULE = '''"""Module containing multiple collectors with identical method signatures."""

class CollectorA:
    def __init__(self, name: str):
        self.name = name

    def collect(self):
        return [f"A:{self.name}"]

    def teardown(self):
        pass


class CollectorB:
    def __init__(self, name: str):
        self.name = name

    def collect(self):
        return [f"B:{self.name}"]

    def teardown(self):
        pass


class CollectorC:
    def __init__(self, name: str):
        self.name = name

    def collect(self):
        return [f"C:{self.name}"]

    def teardown(self):
        pass
'''


def test_duplicate_method_signatures_disambiguated_by_target_symbol(tmp_path: Path):
    """Multiple classes define collect(); target_symbol scopes edit to CollectorB alone."""
    target_file = tmp_path / "collectors.py"
    target_file.write_text(SAMPLE_MULTI_CLASS_MODULE, encoding="utf-8")

    pb = DemoPatchBuilder()
    mod = StructuralCodeModification(
        path="collectors.py",
        target_symbol="CollectorB.collect",
        operation="replace",
        anchor="        return [f\"B:{self.name}\"]",
        code="        # Disambiguated patch in B\n        return [f\"B_MODIFIED:{self.name}\"]",
        reason="Update collector B",
    )

    res = pb.build_patch([mod], base_dir=tmp_path)
    assert res.success is True, f"Failed: {res.error_message}"
    assert res.unified_diff is not None

    # Target file on disk was not modified by build_patch itself
    lines = target_file.read_text(encoding="utf-8").splitlines(keepends=True)
    assert "B_MODIFIED" not in "".join(lines)

    # Now verify diff contents
    diff = res.unified_diff
    assert "B_MODIFIED" in diff
    assert "CollectorB" in diff or "return [f\"B_MODIFIED" in diff
    assert "CollectorA" not in diff
    assert "CollectorC" not in diff


def test_untouched_duplicate_classes_remain_identical(tmp_path: Path):
    """Verify that CollectorA and CollectorC remain byte-for-byte identical after editing CollectorB."""
    target_file = tmp_path / "collectors.py"
    target_file.write_text(SAMPLE_MULTI_CLASS_MODULE, encoding="utf-8")

    pb = DemoPatchBuilder()
    mod = StructuralCodeModification(
        path="collectors.py",
        target_class="CollectorB",
        target_method="collect",
        operation="insert_after",
        anchor="    def collect(self):",
        code="        guard_active = True",
        reason="Add guard to B",
    )

    res = pb.build_patch([mod], base_dir=tmp_path)
    assert res.success is True

    # Apply diff using DDIV PatchManager in git workspace
    import subprocess
    from evaluation.patch_manager import PatchManager

    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), check=True, capture_output=True)

    pm = PatchManager()
    apply_res = pm.apply_patch(tmp_path, res.unified_diff)
    assert apply_res.is_success is True, f"Git apply failed: {apply_res.stderr}"

    new_content = target_file.read_text(encoding="utf-8")
    scopes = find_ast_scopes(new_content)
    scope_a = next(s for s in scopes if s.qualified_name == "CollectorA")
    scope_c = next(s for s in scopes if s.qualified_name == "CollectorC")

    orig_scopes = find_ast_scopes(SAMPLE_MULTI_CLASS_MODULE)
    orig_scope_a = next(s for s in orig_scopes if s.qualified_name == "CollectorA")
    orig_scope_c = next(s for s in orig_scopes if s.qualified_name == "CollectorC")

    # Byte-for-byte equality of unmodified classes
    assert scope_a.full_text == orig_scope_a.full_text
    assert scope_c.full_text == orig_scope_c.full_text
    assert scope_a.fingerprint == orig_scope_a.fingerprint
    assert scope_c.fingerprint == orig_scope_c.fingerprint


def test_duplicate_method_signatures_rejected_when_unscoped(tmp_path: Path):
    """When an anchor appears in multiple classes without target_symbol, reject with ANCHOR_AMBIGUOUS_MULTI_CLASS."""
    target_file = tmp_path / "collectors.py"
    target_file.write_text(SAMPLE_MULTI_CLASS_MODULE, encoding="utf-8")

    pb = DemoPatchBuilder()
    mod = StructuralCodeModification(
        path="collectors.py",
        operation="insert_after",
        anchor="    def collect(self):",
        code="        print('in collect')",
        reason="Unscoped ambiguous insertion",
    )

    res = pb.build_patch([mod], base_dir=tmp_path)
    assert res.success is False
    assert res.error_category == "ANCHOR_AMBIGUOUS_MULTI_CLASS"
    assert "CollectorA" in res.error_message
    assert "CollectorB" in res.error_message
    assert "CollectorC" in res.error_message
    assert "target_symbol" in res.error_message


def test_stale_anchor_rejected_by_source_fingerprint_mismatch(tmp_path: Path):
    """When source_fingerprint does not match the actual target block, reject with STALE_ANCHOR."""
    target_file = tmp_path / "collectors.py"
    target_file.write_text(SAMPLE_MULTI_CLASS_MODULE, encoding="utf-8")

    pb = DemoPatchBuilder()
    stale_fingerprint = "0123456789abcdef"  # Non-matching fingerprint

    mod = StructuralCodeModification(
        path="collectors.py",
        target_symbol="CollectorA.collect",
        source_fingerprint=stale_fingerprint,
        operation="insert_after",
        anchor="    def collect(self):",
        code="        check_validity()",
        reason="Stale edit attempt",
    )

    res = pb.build_patch([mod], base_dir=tmp_path)
    assert res.success is False
    assert res.error_category == "STALE_ANCHOR"
    assert stale_fingerprint in res.error_message

    # File on disk must remain pristine
    assert target_file.read_text(encoding="utf-8") == SAMPLE_MULTI_CLASS_MODULE


def test_valid_source_fingerprint_matches_and_applies(tmp_path: Path):
    """When source_fingerprint matches the target block, the patch applies cleanly."""
    target_file = tmp_path / "collectors.py"
    target_file.write_text(SAMPLE_MULTI_CLASS_MODULE, encoding="utf-8")

    scopes = find_ast_scopes(SAMPLE_MULTI_CLASS_MODULE)
    scope_a_collect, _ = resolve_target_scope(scopes, target_symbol="CollectorA.collect")
    assert scope_a_collect is not None
    valid_fp = scope_a_collect.fingerprint

    pb = DemoPatchBuilder()
    mod = StructuralCodeModification(
        path="collectors.py",
        target_symbol="CollectorA.collect",
        source_fingerprint=valid_fp,
        operation="insert_after",
        anchor="    def collect(self):",
        code="        check_validity()",
        reason="Valid fingerprinted edit",
    )

    res = pb.build_patch([mod], base_dir=tmp_path)
    assert res.success is True
    assert res.unified_diff is not None
    assert "check_validity()" in res.unified_diff


def test_anchor_not_in_target_scope_rejected(tmp_path: Path):
    """When an anchor exists in another scope but not the target scope, reject with ANCHOR_NOT_IN_TARGET_SCOPE."""
    target_file = tmp_path / "collectors.py"
    target_file.write_text(SAMPLE_MULTI_CLASS_MODULE, encoding="utf-8")

    pb = DemoPatchBuilder()
    # The anchor belongs to CollectorB, but we target CollectorA.collect
    mod = StructuralCodeModification(
        path="collectors.py",
        target_symbol="CollectorA.collect",
        operation="replace",
        anchor="        return [f\"B:{self.name}\"]",
        code="        return []",
        reason="Wrong scope targeting",
    )

    res = pb.build_patch([mod], base_dir=tmp_path)
    assert res.success is False
    assert res.error_category == "ANCHOR_NOT_IN_TARGET_SCOPE"
    assert "CollectorA.collect" in res.error_message


def test_line_range_bounds_disambiguation(tmp_path: Path):
    """Line range bounds disambiguate duplicate anchors when target_symbol is not provided."""
    target_file = tmp_path / "collectors.py"
    target_file.write_text(SAMPLE_MULTI_CLASS_MODULE, encoding="utf-8")

    # CollectorB starts around line 15
    scopes = find_ast_scopes(SAMPLE_MULTI_CLASS_MODULE)
    scope_b = next(s for s in scopes if s.qualified_name == "CollectorB")

    pb = DemoPatchBuilder()
    mod = StructuralCodeModification(
        path="collectors.py",
        line_range=(scope_b.start_line, scope_b.end_line),
        operation="insert_after",
        anchor="    def collect(self):",
        code="        # bounded by line range",
        reason="Line-bounded disambiguation",
    )

    res = pb.build_patch([mod], base_dir=tmp_path)
    assert res.success is True
    assert res.unified_diff is not None
    assert "bounded by line range" in res.unified_diff


def test_line_range_out_of_bounds_rejected(tmp_path: Path):
    """Line range outside actual anchor location rejects with OUT_OF_RANGE_ANCHOR."""
    target_file = tmp_path / "collectors.py"
    target_file.write_text(SAMPLE_MULTI_CLASS_MODULE, encoding="utf-8")

    pb = DemoPatchBuilder()
    mod = StructuralCodeModification(
        path="collectors.py",
        line_range=(100, 120),  # File has ~35 lines
        operation="insert_after",
        anchor="    def collect(self):",
        code="        # impossible range",
        reason="Out of bounds range",
    )

    res = pb.build_patch([mod], base_dir=tmp_path)
    assert res.success is False
    assert res.error_category == "OUT_OF_RANGE_ANCHOR"


def test_backward_compatibility_with_legacy_codemodification_and_dict(tmp_path: Path):
    """Legacy CodeModification and raw dict proposals continue to work seamlessly."""
    target_file = tmp_path / "sample.py"
    target_file.write_text("def unique_func():\n    return 42\n", encoding="utf-8")

    pb = DemoPatchBuilder()

    # 1. Legacy CodeModification instance
    legacy_mod = CodeModification(
        path="sample.py",
        operation="replace",
        anchor="    return 42",
        code="    return 100",
        reason="Legacy update",
    )
    res1 = pb.build_patch([legacy_mod], base_dir=tmp_path)
    assert res1.success is True
    assert "return 100" in res1.unified_diff

    # 2. Raw dict
    dict_mod = {
        "path": "sample.py",
        "operation": "replace",
        "anchor": "    return 42",
        "code": "    return 200",
        "reason": "Dict update",
    }
    res2 = pb.build_patch([dict_mod], base_dir=tmp_path)
    assert res2.success is True
    assert "return 200" in res2.unified_diff


def test_semantic_anti_repetition_detects_ast_equivalent_code():
    """ProposalHistory detects AST-equivalent code regardless of comments or whitespace."""
    history = ProposalHistory()
    history.record_attempt(
        attempt=1,
        path="src/module.py",
        operation="insert_after",
        anchor="def func():",
        code="    # Initial comment\n    x = 1\n    return x\n",
        target_symbol="MyClass.func",
        error_category="F2P_FAILURE",
        error_detail="Test failed",
    )

    # Minor comment and whitespace differences:
    variation_code = "    x = 1 # different inline comment\n    return x"
    repeated = history.is_repeated(
        path="src/module.py",
        operation="insert_after",
        anchor="def func():",
        code=variation_code,
        target_symbol="MyClass.func",
    )
    assert repeated == 1, "AST-equivalent proposal should be detected as repeated"

    # Genuinely different code:
    different_code = "    x = 2\n    return x"
    not_repeated = history.is_repeated(
        path="src/module.py",
        operation="insert_after",
        anchor="def func():",
        code=different_code,
        target_symbol="MyClass.func",
    )
    assert not_repeated is None, "Semantically different proposal should be novel"


def test_semantic_anti_repetition_allows_structural_disambiguation_retry():
    """Attempt 1 failed with ambiguous unscoped anchor; Attempt 2 supplies target_symbol and is ALLOWED."""
    history = ProposalHistory()
    # Attempt 1: unscoped anchor failed due to multi-class ambiguity
    history.record_attempt(
        attempt=1,
        path="src/collectors.py",
        operation="insert_after",
        anchor="def collect(self):",
        code="    check()",
        target_symbol=None,
        error_category="ANCHOR_AMBIGUOUS_MULTI_CLASS",
        error_detail="Ambiguous across CollectorA, CollectorB",
    )

    # Attempt 2: Re-submitting the exact same anchor string, but supplying target_symbol
    repeated = history.is_repeated(
        path="src/collectors.py",
        operation="insert_after",
        anchor="def collect(self):",
        code="    check()",
        target_symbol="CollectorB.collect",
    )
    assert repeated is None, "Supplying valid structural disambiguation must NOT be blocked as repeated"

    # Attempt 3: Repeating Attempt 1 without structural disambiguation IS blocked
    repeated_unscoped = history.is_repeated(
        path="src/collectors.py",
        operation="insert_after",
        anchor="def collect(self):",
        code="    check()",
        target_symbol=None,
    )
    assert repeated_unscoped == 1, "Repeating unscoped ambiguous anchor must be blocked"


def test_failure_disambiguator_classifies_new_anchor_categories():
    """FailureDisambiguator correctly maps the new structural anchor error categories."""
    cat1, _ = FailureDisambiguator.classify(
        patch_valid=False,
        patch_applied=False,
        pb_error_category="ANCHOR_AMBIGUOUS_MULTI_CLASS",
        pb_error_message="Ambiguous across multiple classes",
    )
    assert cat1 == "ANCHOR_AMBIGUOUS_MULTI_CLASS"

    cat2, _ = FailureDisambiguator.classify(
        patch_valid=False,
        patch_applied=False,
        pb_error_category="STALE_ANCHOR",
        pb_error_message="Fingerprint mismatched",
    )
    assert cat2 == "STALE_ANCHOR"

    cat3, _ = FailureDisambiguator.classify(
        patch_valid=False,
        patch_applied=False,
        pb_error_category="ANCHOR_NOT_IN_TARGET_SCOPE",
        pb_error_message="Not in target scope",
    )
    assert cat3 == "ANCHOR_NOT_IN_TARGET_SCOPE"


def test_negative_constraints_format_actionable_mandates():
    """Negative directives generated for Coder explicitly mandate target_symbol on multi-class ambiguity."""
    history = ProposalHistory()
    history.record_attempt(
        attempt=1,
        path="src/collectors.py",
        operation="insert_after",
        anchor="def collect(self, parent):",
        code="    pass",
        target_symbol=None,
        error_category="ANCHOR_AMBIGUOUS_MULTI_CLASS",
        error_detail="Ambiguous across CollectorA, CollectorB, CollectorC",
    )
    history.record_attempt(
        attempt=2,
        path="src/helpers.py",
        operation="replace",
        anchor="def helper():",
        code="    return True",
        target_symbol="helpers.helper",
        error_category="STALE_ANCHOR",
        error_detail="Fingerprint mismatch",
    )

    constraints = history.format_negative_constraints()
    assert "Attempt 1" in constraints
    assert "ANCHOR_AMBIGUOUS_MULTI_CLASS" in constraints
    assert "You MUST NOT repeat this ambiguous anchor without specifying 'target_symbol'" in constraints
    assert "Attempt 2" in constraints
    assert "STALE_ANCHOR" in constraints
    assert "Source fingerprint mismatched" in constraints
