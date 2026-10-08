"""Deterministic Patch Builder: Converts structured code modifications into valid unified diffs."""

from __future__ import annotations

import difflib
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from evaluation.patch_manager import PatchManager, PatchValidationResult


class CodeModification(BaseModel):
    """Structured code modification specified by the Coder Agent."""

    path: str = Field(..., description="Relative path to target file")
    target_symbol: Optional[str] = Field(None, description="Target function, class, or method (e.g. Blueprint.__init__)")
    operation: str = Field(..., description="Operation: 'insert_after', 'insert_before', 'replace', or 'delete'")
    anchor: str = Field(..., description="Exact unique code snippet from source file to anchor the change")
    code: str = Field(default="", description="Code to insert or replace with (empty for delete)")
    reason: str = Field(default="", description="Semantic rationale for this specific change")


class PatchBuilderResult(BaseModel):
    """Result of deterministic patch construction."""

    success: bool
    unified_diff: str = ""
    error_message: Optional[str] = None
    error_category: Optional[str] = None
    applied_modifications: List[Dict[str, Any]] = Field(default_factory=list)
    anchor_found: bool = False
    anchor_unique: bool = False
    target_files: List[str] = Field(default_factory=list)
    generation_latency: float = 0.0


class DeterministicPatchBuilder:
    """Deterministically transforms structured code modifications into standard unified git diffs."""

    def __init__(self, patch_manager: Optional[PatchManager] = None):
        self.patch_manager = patch_manager or PatchManager()

    def build_patch(
        self,
        modifications: List[Union[CodeModification, Dict[str, Any]]],
        base_dir: Union[Path, str],
    ) -> PatchBuilderResult:
        """Convert a list of structured modifications into a verified unified diff."""
        start_time = time.time()
        base_path = Path(base_dir)

        if not modifications:
            return PatchBuilderResult(
                success=False,
                error_message="No modifications provided.",
                error_category="EMPTY_MODIFICATIONS",
                generation_latency=time.time() - start_time,
            )

        # Normalize modification objects
        norm_mods: List[CodeModification] = []
        for mod in modifications:
            if isinstance(mod, CodeModification):
                norm_mods.append(mod)
            elif isinstance(mod, dict):
                try:
                    norm_mods.append(CodeModification(**mod))
                except Exception as exc:
                    return PatchBuilderResult(
                        success=False,
                        error_message=f"Malformed code modification payload: {exc}",
                        error_category="MALFORMED_OUTPUT",
                        generation_latency=time.time() - start_time,
                    )
            else:
                return PatchBuilderResult(
                    success=False,
                    error_message=f"Unsupported modification type: {type(mod)}",
                    error_category="MALFORMED_OUTPUT",
                    generation_latency=time.time() - start_time,
                )

        # Group modifications by relative file path
        mods_by_file: Dict[str, List[CodeModification]] = {}
        for mod in norm_mods:
            norm_rel = mod.path.replace("\\", "/").strip().lstrip("/")
            mods_by_file.setdefault(norm_rel, []).append(mod)

        diff_chunks: List[str] = []
        applied_records: List[Dict[str, Any]] = []
        all_anchors_found = True
        all_anchors_unique = True

        for rel_path, file_mods in mods_by_file.items():
            full_path = base_path / rel_path
            if not full_path.exists():
                return PatchBuilderResult(
                    success=False,
                    error_message=f"Target file not found in workspace: {rel_path}",
                    error_category="FILE_NOT_FOUND",
                    target_files=list(mods_by_file.keys()),
                    generation_latency=time.time() - start_time,
                )

            try:
                original_content = full_path.read_text(encoding="utf-8")
            except Exception as read_err:
                return PatchBuilderResult(
                    success=False,
                    error_message=f"Failed to read target file '{rel_path}': {read_err}",
                    error_category="FILE_READ_ERROR",
                    target_files=list(mods_by_file.keys()),
                    generation_latency=time.time() - start_time,
                )

            current_content = original_content

            for mod in file_mods:
                op = mod.operation.lower().strip()
                anchor = mod.anchor
                code = mod.code or ""

                if op not in ("insert_after", "insert_before", "replace", "delete"):
                    return PatchBuilderResult(
                        success=False,
                        error_message=(
                            f"Unsupported operation '{op}'. Supported operations are: "
                            "'insert_after', 'insert_before', 'replace', 'delete'."
                        ),
                        error_category="INVALID_OPERATION",
                        target_files=list(mods_by_file.keys()),
                        generation_latency=time.time() - start_time,
                    )

                if not anchor:
                    return PatchBuilderResult(
                        success=False,
                        error_message=f"Empty anchor provided for modification in '{rel_path}'.",
                        error_category="EMPTY_ANCHOR",
                        target_files=list(mods_by_file.keys()),
                        generation_latency=time.time() - start_time,
                    )

                anchor_count = current_content.count(anchor)
                if anchor_count == 0:
                    # Fallback: attempt normalized line matching to tolerate minor escaping, quote, or spacing differences
                    anchor_lines = [l.strip() for l in anchor.splitlines() if l.strip()]
                    if anchor_lines:
                        content_lines = current_content.splitlines(keepends=True)
                        matched_spans = []
                        for i in range(len(content_lines) - len(anchor_lines) + 1):
                            match = True
                            for j, a_line in enumerate(anchor_lines):
                                c_line = content_lines[i + j].strip()
                                a_norm = a_line.replace("'", '"').replace(" ", "").replace("\\", "")
                                c_norm = c_line.replace("'", '"').replace(" ", "").replace("\\", "")
                                if a_norm != c_norm:
                                    match = False
                                    break
                            if match:
                                verbatim_chunk = "".join(content_lines[i : i + len(anchor_lines)])
                                if not anchor.endswith("\n") and verbatim_chunk.endswith("\n"):
                                    verbatim_chunk = verbatim_chunk.rstrip("\r\n")
                                matched_spans.append(verbatim_chunk)
                        if len(matched_spans) == 1:
                            anchor = matched_spans[0]
                            anchor_count = 1

                if anchor_count == 0:
                    return PatchBuilderResult(
                        success=False,
                        error_message=(
                            f"Anchor not found in '{rel_path}'. Anchor must match exact verbatim lines "
                            f"from source file with identical indentation. Anchor snippet:\n{anchor[:150]}"
                        ),
                        error_category="ANCHOR_NOT_FOUND",
                        anchor_found=False,
                        anchor_unique=False,
                        target_files=list(mods_by_file.keys()),
                        generation_latency=time.time() - start_time,
                    )
                elif anchor_count > 1:
                    return PatchBuilderResult(
                        success=False,
                        error_message=(
                            f"Anchor is ambiguous in '{rel_path}' (found {anchor_count} occurrences). "
                            f"Include additional surrounding context lines to make the anchor uniquely identifiable."
                        ),
                        error_category="ANCHOR_AMBIGUOUS",
                        anchor_found=True,
                        anchor_unique=False,
                        target_files=list(mods_by_file.keys()),
                        generation_latency=time.time() - start_time,
                    )

                idx = current_content.find(anchor)
                line_start = current_content.rfind("\n", 0, idx) + 1
                line_prefix = current_content[line_start:idx]
                is_pure_prefix = bool(line_prefix and line_prefix.strip() == "")

                if op == "insert_after":
                    insert_pos = idx + len(anchor)
                    if not anchor.endswith("\n"):
                        if current_content[insert_pos:insert_pos + 2] == "\r\n":
                            insert_pos += 2
                        elif current_content[insert_pos:insert_pos + 1] == "\n":
                            insert_pos += 1
                    if is_pure_prefix and code:
                        code_lines = code.splitlines(keepends=True)
                        if code_lines and not code_lines[0].startswith((" ", "\t")):
                            code = "".join(
                                (line_prefix + l) if l.strip() else l for l in code_lines
                            )
                    if code and not code.endswith("\n"):
                        code += "\n"
                    current_content = current_content[:insert_pos] + code + current_content[insert_pos:]

                elif op == "insert_before":
                    if is_pure_prefix and code:
                        code_lines = code.splitlines(keepends=True)
                        if code_lines and not code_lines[0].startswith((" ", "\t")):
                            code = "".join(
                                (line_prefix + l) if l.strip() else l for l in code_lines
                            )
                    if code and not code.endswith("\n"):
                        code += "\n"
                    current_content = current_content[:idx] + code + current_content[idx:]

                elif op == "replace":
                    if is_pure_prefix and code:
                        code_lines = code.splitlines(keepends=True)
                        if len(code_lines) > 1 and not code_lines[0].startswith((" ", "\t")):
                            code = code_lines[0] + "".join(
                                (line_prefix + l) if l.strip() else l for l in code_lines[1:]
                            )
                    if anchor.endswith("\n") and code and not code.endswith("\n"):
                        code += "\n"
                    current_content = current_content[:idx] + code + current_content[idx + len(anchor):]

                elif op == "delete":
                    end_pos = idx + len(anchor)
                    if not anchor.endswith("\n"):
                        if current_content[end_pos:end_pos + 2] == "\r\n":
                            end_pos += 2
                        elif current_content[end_pos:end_pos + 1] == "\n":
                            end_pos += 1
                    current_content = current_content[:idx] + current_content[end_pos:]

                else:
                    return PatchBuilderResult(
                        success=False,
                        error_message=(
                            f"Unsupported operation '{op}'. Supported operations are: "
                            "'insert_after', 'insert_before', 'replace', 'delete'."
                        ),
                        error_category="INVALID_OPERATION",
                        target_files=list(mods_by_file.keys()),
                        generation_latency=time.time() - start_time,
                    )

                applied_records.append({
                    "path": rel_path,
                    "target_symbol": mod.target_symbol,
                    "operation": op,
                    "anchor_preview": anchor[:80],
                    "code_preview": code[:80] if code else "",
                    "reason": mod.reason,
                })

            # Generate unified diff for this file
            orig_lines = original_content.splitlines(keepends=True)
            new_lines = current_content.splitlines(keepends=True)

            diff_lines = list(difflib.unified_diff(
                orig_lines,
                new_lines,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
                lineterm="\n",
            ))

            if diff_lines:
                diff_chunks.append(f"diff --git a/{rel_path} b/{rel_path}\n" + "".join(diff_lines))

        if not diff_chunks:
            return PatchBuilderResult(
                success=False,
                error_message="Applied modifications resulted in an empty diff (no changes detected).",
                error_category="EMPTY_DIFF",
                target_files=list(mods_by_file.keys()),
                generation_latency=time.time() - start_time,
            )

        full_diff = "\n".join(diff_chunks)
        if not full_diff.endswith("\n"):
            full_diff += "\n"

        # Validate through PatchManager
        val_res = self.patch_manager.validate_patch(full_diff)
        if not val_res.is_valid:
            return PatchBuilderResult(
                success=False,
                unified_diff=full_diff,
                error_message=f"Deterministic patch failed PatchManager validation: {val_res.error_message}",
                error_category="PATCH_VALIDATION_FAILED",
                target_files=list(mods_by_file.keys()),
                generation_latency=time.time() - start_time,
            )

        return PatchBuilderResult(
            success=True,
            unified_diff=val_res.sanitized_patch,
            applied_modifications=applied_records,
            anchor_found=all_anchors_found,
            anchor_unique=all_anchors_unique,
            target_files=list(mods_by_file.keys()),
            generation_latency=time.time() - start_time,
        )
