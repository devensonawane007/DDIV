"""Unified diff validation, sanitation, application, and rollback."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel

from evaluation.command_runner import CommandResult, CommandRunner


class PatchValidationResult(BaseModel):
    is_valid: bool
    modified_files: List[str]
    error_message: Optional[str] = None
    sanitized_patch: str = ""


class PatchManager:
    """Manages patch validation, applying to working trees, and cleanly reverting."""

    def __init__(self, command_runner: Optional[CommandRunner] = None):
        self.runner = command_runner or CommandRunner()

    @staticmethod
    def sanitize_patch(raw_patch: str) -> str:
        """Strip markdown fences, normalize line endings, and ensure trailing newline."""
        if not raw_patch:
            return ""
        patch = raw_patch.replace("\r\n", "\n")
        lines = patch.split("\n")
        while lines and (not lines[0].strip() or lines[0].strip().startswith("```")):
            lines.pop(0)
        while lines and lines[-1].strip().startswith("```"):
            lines.pop()
        patch = "\n".join(lines)
        if not patch.endswith("\n"):
            patch += "\n"
        return patch

    def validate_patch(self, raw_patch: str) -> PatchValidationResult:
        """Verify unified diff format and extract target modified files."""
        patch = self.sanitize_patch(raw_patch)
        if not patch:
            return PatchValidationResult(
                is_valid=False,
                modified_files=[],
                error_message="Patch is empty.",
            )

        # Standard unified diff pattern
        # Must contain at least one --- and +++ pair and a hunk header @@
        has_minus = bool(re.search(r"^--- (?:a/|[^\s]+)", patch, re.MULTILINE))
        has_plus = bool(re.search(r"^\+\+\+ (?:b/|[^\s]+)", patch, re.MULTILINE))
        has_hunk = bool(re.search(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", patch, re.MULTILINE))

        if not (has_minus and has_plus and has_hunk):
            return PatchValidationResult(
                is_valid=False,
                modified_files=[],
                error_message="Patch does not match standard unified diff format (missing ---, +++, or @@ hunk headers with line numbers).",
                sanitized_patch=patch,
            )

        # Extract modified files from +++ lines
        modified = []
        for match in re.finditer(r"^\+\+\+ (?:b/)?([^\s]+)", patch, re.MULTILINE):
            fpath = match.group(1).strip()
            if fpath != "/dev/null" and fpath not in modified:
                modified.append(fpath)

        return PatchValidationResult(
            is_valid=True,
            modified_files=modified,
            sanitized_patch=patch,
        )

    def apply_patch(self, workspace_path: str | Path, patch_content: str) -> CommandResult:
        """Apply patch to target repository workspace using git apply."""
        clean_patch = self.sanitize_patch(patch_content)
        wpath = Path(workspace_path)

        with tempfile.NamedTemporaryFile("wb", suffix=".patch", delete=False) as tmp:
            tmp.write(clean_patch.encode("utf-8"))
            tmp_path = tmp.name

        try:
            # 1. Check patch first (strict)
            check_res = self.runner.run(
                ["git", "apply", "--check", tmp_path],
                cwd=wpath,
            )
            apply_flags = ["--whitespace=nowarn"]
            if not check_res.is_success:
                # 2. Check with whitespace tolerance (standard for cross-platform SWE-bench evaluation)
                check_tol = self.runner.run(
                    ["git", "apply", "--check", "--ignore-space-change", "--ignore-whitespace", tmp_path],
                    cwd=wpath,
                )
                if check_tol.is_success:
                    apply_flags.extend(["--ignore-space-change", "--ignore-whitespace"])
                else:
                    return check_res

            # Actually apply patch
            apply_res = self.runner.run(
                ["git", "apply"] + apply_flags + [tmp_path],
                cwd=wpath,
            )
            return apply_res
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

    def revert_workspace(self, workspace_path: str | Path) -> CommandResult:
        """Reset workspace back to clean state."""
        wpath = Path(workspace_path)
        # Git reset and clean
        res1 = self.runner.run(["git", "reset", "--hard", "HEAD"], cwd=wpath)
        if not res1.is_success:
            res1 = self.runner.run(["git", "checkout", "--", "."], cwd=wpath)
        res2 = self.runner.run(["git", "clean", "-fd"], cwd=wpath)
        return res2 if res1.is_success else res1
