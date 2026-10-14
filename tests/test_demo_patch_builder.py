"""Unit and regression tests for DemoPatchBuilder."""
import ast
from pathlib import Path
import pytest
from scripts.demo_patch_builder import DemoPatchBuilder
from evaluation.patch_builder import CodeModification
from evaluation.patch_manager import PatchManager

FILE_CONTENT = """def _query_cpu() -> int | None:
    cpu_quota, avail_cpu = None, None
    if Path("/sys/fs/cgroup/cpu/cpu.shares").is_file():
        with open("/sys/fs/cgroup/cpu/cpu.shares", encoding="utf-8") as file:
            cpu_shares = int(file.read().rstrip())
        # For AWS, gives correct value * 1024.
        avail_cpu = int(cpu_shares / 1024)
    return avail_cpu
"""

def test_insert_before_unindented_anchor(tmp_path):
    file_p = tmp_path / "run.py"
    file_p.write_text(FILE_CONTENT, encoding="utf-8")
    builder = DemoPatchBuilder()
    mods = [
        CodeModification(
            path="run.py",
            operation="insert_before",
            anchor="return avail_cpu",
            code="    if avail_cpu is not None and avail_cpu < 1:\n        avail_cpu = 1",
            reason="Clamp CPU count to at least 1",
        )
    ]
    res = builder.build_patch(mods, base_dir=tmp_path)
    assert res.success is True, res.error_message
    pmgr = PatchManager()
    apply_res = pmgr.apply_patch(tmp_path, res.unified_diff)
    assert apply_res.is_success is True, apply_res.stderr
    patched_content = file_p.read_text(encoding="utf-8")
    ast.parse(patched_content)
    assert "    if avail_cpu is not None and avail_cpu < 1:" in patched_content
    assert "    return avail_cpu" in patched_content

def test_replace_unindented_anchor(tmp_path):
    file_p = tmp_path / "run.py"
    file_p.write_text(FILE_CONTENT, encoding="utf-8")
    builder = DemoPatchBuilder()
    mods = [
        CodeModification(
            path="run.py",
            operation="replace",
            anchor="return avail_cpu",
            code="    if avail_cpu is not None and avail_cpu < 1:\n        avail_cpu = 1\n    return avail_cpu",
            reason="Clamp in replace",
        )
    ]
    res = builder.build_patch(mods, base_dir=tmp_path)
    assert res.success is True, res.error_message
    pmgr = PatchManager()
    apply_res = pmgr.apply_patch(tmp_path, res.unified_diff)
    assert apply_res.is_success is True, apply_res.stderr
    patched_content = file_p.read_text(encoding="utf-8")
    ast.parse(patched_content)
    assert "    if avail_cpu is not None" in patched_content

def test_syntax_error_detection(tmp_path):
    file_p = tmp_path / "run.py"
    file_p.write_text(FILE_CONTENT, encoding="utf-8")
    builder = DemoPatchBuilder()
    mods = [
        CodeModification(
            path="run.py",
            operation="replace",
            anchor="return avail_cpu",
            code="if invalid syntax here!!!",
            reason="Invalid syntax",
        )
    ]
    res = builder.build_patch(mods, base_dir=tmp_path)
    assert res.success is False
    assert res.error_category == "SYNTAX_ERROR"
    assert "failed Python AST syntax verification" in res.error_message
