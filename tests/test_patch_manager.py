"""Tests for PatchManager and unified diff operations."""

import tempfile
import unittest
from pathlib import Path

from evaluation.command_runner import CommandRunner
from evaluation.patch_manager import PatchManager


class TestPatchManager(unittest.TestCase):
    def setUp(self):
        self.runner = CommandRunner()
        self.patch_mgr = PatchManager(self.runner)
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.tmp_dir.name)

        # Initialize git in temp directory
        self.runner.run(["git", "init"], cwd=self.repo_dir)
        self.runner.run(["git", "config", "user.name", "Test User"], cwd=self.repo_dir)
        self.runner.run(["git", "config", "user.email", "test@test.local"], cwd=self.repo_dir)

        # Create a sample file
        (self.repo_dir / "sample.py").write_text("def hello():\n    return 'hello'\n", encoding="utf-8")
        self.runner.run(["git", "add", "sample.py"], cwd=self.repo_dir)
        self.runner.run(["git", "commit", "-m", "Initial"], cwd=self.repo_dir)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_validate_valid_patch(self):
        diff = (
            "--- a/sample.py\n"
            "+++ b/sample.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def hello():\n"
            "-    return 'hello'\n"
            "+    return 'world'\n"
        )
        res = self.patch_mgr.validate_patch(diff)
        self.assertTrue(res.is_valid)
        self.assertIn("sample.py", res.modified_files)

    def test_validate_invalid_patch(self):
        bad_diff = "Just a freeform comment without diff headers"
        res = self.patch_mgr.validate_patch(bad_diff)
        self.assertFalse(res.is_valid)
        self.assertIn("missing", res.error_message.lower())

    def test_apply_and_revert_patch(self):
        diff = (
            "--- a/sample.py\n"
            "+++ b/sample.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def hello():\n"
            "-    return 'hello'\n"
            "+    return 'world'\n"
        )
        # Apply patch
        apply_res = self.patch_mgr.apply_patch(self.repo_dir, diff)
        self.assertTrue(apply_res.is_success, f"Apply failed: {apply_res.stderr}")

        content_after = (self.repo_dir / "sample.py").read_text(encoding="utf-8")
        self.assertIn("world", content_after)

        # Revert patch
        revert_res = self.patch_mgr.revert_workspace(self.repo_dir)
        self.assertTrue(revert_res.is_success)

        content_reverted = (self.repo_dir / "sample.py").read_text(encoding="utf-8")
        self.assertIn("hello", content_reverted)


if __name__ == "__main__":
    unittest.main()
