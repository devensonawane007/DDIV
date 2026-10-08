"""Deterministic unit tests for DeterministicPatchBuilder and structured code modifications."""

import difflib
import subprocess
import tempfile
import unittest
from pathlib import Path

from evaluation.patch_builder import (
    CodeModification,
    DeterministicPatchBuilder,
    PatchBuilderResult,
)
from evaluation.patch_manager import PatchManager


SAMPLE_FILE_CONTENT = """def calculate_total(items, discount=0):
    subtotal = 0
    for item in items:
        subtotal += item.price
    if discount > 0:
        subtotal -= subtotal * discount
    return subtotal
"""


class TestPatchBuilder(unittest.TestCase):
    def setUp(self):
        self.patch_manager = PatchManager()
        self.builder = DeterministicPatchBuilder(self.patch_manager)

    def _setup_temp_repo(self, content: str = SAMPLE_FILE_CONTENT) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        tpath = Path(td.name)

        # Initialize git repo for git apply testing
        subprocess.run(["git", "init"], cwd=tpath, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "TestUser"], cwd=tpath, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tpath, check=True, capture_output=True)

        target = tpath / "src/calculator.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=tpath, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tpath, check=True, capture_output=True)
        return tpath

    def test_1_valid_insertion_after(self):
        """1. Verify valid insert_after places code immediately following anchor."""
        base_dir = self._setup_temp_repo()
        mod = CodeModification(
            path="src/calculator.py",
            target_symbol="calculate_total",
            operation="insert_after",
            anchor="    if discount > 0:\n        subtotal -= subtotal * discount",
            code="    if discount > 1.0:\n        raise ValueError('Discount cannot exceed 100%')",
            reason="Validate discount upper bound.",
        )
        res = self.builder.build_patch([mod], base_dir)
        self.assertTrue(res.success, f"Failed with: {res.error_message}")
        self.assertIn("+    if discount > 1.0:", res.unified_diff)
        self.assertIn("--- a/src/calculator.py", res.unified_diff)
        self.assertIn("+++ b/src/calculator.py", res.unified_diff)

    def test_2_valid_insertion_before(self):
        """2. Verify valid insert_before places code immediately preceding anchor."""
        base_dir = self._setup_temp_repo()
        mod = CodeModification(
            path="src/calculator.py",
            target_symbol="calculate_total",
            operation="insert_before",
            anchor="    subtotal = 0",
            code="    if not items:\n        return 0",
            reason="Handle empty items guard.",
        )
        res = self.builder.build_patch([mod], base_dir)
        self.assertTrue(res.success, f"Failed with: {res.error_message}")
        self.assertIn("+    if not items:", res.unified_diff)
        self.assertIn("--- a/src/calculator.py", res.unified_diff)
        self.assertIn("+++ b/src/calculator.py", res.unified_diff)

    def test_3_valid_replacement(self):
        """3. Verify valid replace substitutes anchor snippet with new code."""
        base_dir = self._setup_temp_repo()
        mod = CodeModification(
            path="src/calculator.py",
            target_symbol="calculate_total",
            operation="replace",
            anchor="        subtotal -= subtotal * discount",
            code="        subtotal = round(subtotal * (1 - discount), 2)",
            reason="Fix floating point discount math.",
        )
        res = self.builder.build_patch([mod], base_dir)
        self.assertTrue(res.success, f"Failed with: {res.error_message}")
        self.assertIn("-        subtotal -= subtotal * discount", res.unified_diff)
        self.assertIn("+        subtotal = round(subtotal * (1 - discount), 2)", res.unified_diff)

    def test_4_valid_deletion(self):
        """4. Verify valid delete removes anchor snippet."""
        base_dir = self._setup_temp_repo()
        mod = CodeModification(
            path="src/calculator.py",
            target_symbol="calculate_total",
            operation="delete",
            anchor="    if discount > 0:\n        subtotal -= subtotal * discount\n",
            code="",
            reason="Remove discount logic.",
        )
        res = self.builder.build_patch([mod], base_dir)
        self.assertTrue(res.success, f"Failed with: {res.error_message}")
        self.assertIn("-    if discount > 0:", res.unified_diff)

    def test_5_missing_anchor(self):
        """5. Verify missing anchor is cleanly rejected as ANCHOR_NOT_FOUND."""
        base_dir = self._setup_temp_repo()
        mod = CodeModification(
            path="src/calculator.py",
            operation="insert_after",
            anchor="non_existent_function_call()",
            code="do_something()",
            reason="Invalid anchor test.",
        )
        res = self.builder.build_patch([mod], base_dir)
        self.assertFalse(res.success)
        self.assertEqual(res.error_category, "ANCHOR_NOT_FOUND")
        self.assertFalse(res.anchor_found)

    def test_6_ambiguous_anchor(self):
        """6. Verify non-unique anchor is cleanly rejected as ANCHOR_AMBIGUOUS."""
        content = "x = 1\nx = 1\ny = 2\n"
        base_dir = self._setup_temp_repo(content)
        mod = CodeModification(
            path="src/calculator.py",
            operation="replace",
            anchor="x = 1",
            code="x = 42",
            reason="Ambiguous anchor test.",
        )
        res = self.builder.build_patch([mod], base_dir)
        self.assertFalse(res.success)
        self.assertEqual(res.error_category, "ANCHOR_AMBIGUOUS")
        self.assertTrue(res.anchor_found)
        self.assertFalse(res.anchor_unique)

    def test_7_whitespace_preservation(self):
        """7. Verify exact indentation and context whitespace are preserved."""
        content = "class A:\n    def foo(self):\n        x = 10\n        return x\n"
        base_dir = self._setup_temp_repo(content)
        mod = CodeModification(
            path="src/calculator.py",
            operation="insert_after",
            anchor="        x = 10",
            code="        if x < 0:\n            raise ValueError('Must be positive')",
            reason="Whitespace preservation test.",
        )
        res = self.builder.build_patch([mod], base_dir)
        self.assertTrue(res.success)
        self.assertIn("+        if x < 0:", res.unified_diff)
        self.assertIn("+            raise ValueError('Must be positive')", res.unified_diff)

    def test_8_correct_unified_diff_hunk_generation(self):
        """8. Verify deterministic diff contains valid @@ -start,count +start,count @@ coordinates."""
        base_dir = self._setup_temp_repo()
        mod = CodeModification(
            path="src/calculator.py",
            operation="insert_before",
            anchor="    return subtotal",
            code="    # Final audit log",
            reason="Audit log.",
        )
        res = self.builder.build_patch([mod], base_dir)
        self.assertTrue(res.success)
        import re
        hunk_match = re.search(r"^@@ -\d+,\d+ \+\d+,\d+ @@", res.unified_diff, re.MULTILINE)
        self.assertIsNotNone(hunk_match, f"Hunk header missing line numbers: {res.unified_diff}")

    def test_9_patch_manager_accepts_generated_patch(self):
        """9. Verify PatchManager.validate_patch unconditionally accepts the deterministic patch."""
        base_dir = self._setup_temp_repo()
        mod = CodeModification(
            path="src/calculator.py",
            operation="replace",
            anchor="    subtotal = 0",
            code="    subtotal = 0  # initialized",
            reason="Comment test.",
        )
        res = self.builder.build_patch([mod], base_dir)
        self.assertTrue(res.success)
        val = self.patch_manager.validate_patch(res.unified_diff)
        self.assertTrue(val.is_valid, f"PatchManager rejected deterministic patch: {val.error_message}")
        self.assertIn("src/calculator.py", val.modified_files)

    def test_10_git_apply_succeeds_on_temp_repo(self):
        """10. Verify git apply successfully applies the deterministic diff with return code 0."""
        base_dir = self._setup_temp_repo()
        mod = CodeModification(
            path="src/calculator.py",
            operation="insert_after",
            anchor="    for item in items:\n        subtotal += item.price",
            code="    if not items:\n        return 0",
            reason="Git apply verification test.",
        )
        res = self.builder.build_patch([mod], base_dir)
        self.assertTrue(res.success)

        # Write patch file and run git apply
        patch_file = base_dir / "candidate.patch"
        patch_file.write_text(res.unified_diff, encoding="utf-8")
        apply_res = subprocess.run(
            ["git", "apply", str(patch_file)],
            cwd=base_dir,
            capture_output=True,
            text=True,
        )
        self.assertEqual(apply_res.returncode, 0, f"git apply failed: {apply_res.stderr}")

        # Check modified file contains inserted line
        updated_content = (base_dir / "src/calculator.py").read_text(encoding="utf-8")
        self.assertIn("if not items:\n        return 0", updated_content)

    def test_11_malformed_coder_json_rejected_safely(self):
        """11. Verify malformed inputs (missing keys, invalid operations) fail gracefully."""
        base_dir = self._setup_temp_repo()

        # Missing anchor
        bad_dict = [{"path": "src/calculator.py", "operation": "insert_after"}]
        res = self.builder.build_patch(bad_dict, base_dir)
        self.assertFalse(res.success)
        self.assertEqual(res.error_category, "MALFORMED_OUTPUT")

        # Invalid operation
        bad_op = [{"path": "src/calculator.py", "operation": "magic_teleport", "anchor": "x", "code": "y"}]
        res = self.builder.build_patch(bad_op, base_dir)
        self.assertFalse(res.success)
        self.assertEqual(res.error_category, "INVALID_OPERATION")

        # Empty modifications list
        res = self.builder.build_patch([], base_dir)
        self.assertFalse(res.success)
        self.assertEqual(res.error_category, "EMPTY_MODIFICATIONS")


if __name__ == "__main__":
    unittest.main()
