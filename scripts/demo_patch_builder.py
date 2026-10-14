"""Demo Patch Builder: Whitespace-aware and syntax-verified patch construction.

Isolated operational correction for the DDIV presentation demonstration.
Preserves frozen framework files while fixing the line-indexing and
indentation misalignment bottleneck identified in Phase 1.
"""

from __future__ import annotations

import ast
import difflib
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from evaluation.patch_builder import CodeModification, PatchBuilderResult
from evaluation.patch_manager import PatchManager


class DemoPatchBuilder:
    """Constructs robust unified diffs with line-aligned anchoring and AST syntax verification."""

    def __init__(self, patch_manager: Optional[PatchManager] = None):
        self.patch_manager = patch_manager or PatchManager()

    @staticmethod
    def normalize_code_indentation(code: str, anchor: str, anchor_indent: int, op: str) -> str:
        """Align code snippet indentation relative to the anchor while preserving intra-snippet structure."""
        lines = code.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            return ""

        non_empty = [l for l in lines if l.strip()]
        min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)

        anchor_stripped = anchor.strip()
        if op == "insert_after" and anchor_stripped.endswith(":"):
            target_indent = anchor_indent + 4
        else:
            target_indent = anchor_indent

        adjusted = []
        for l in lines:
            if not l.strip():
                adjusted.append("")
            else:
                rel = (len(l) - len(l.lstrip())) - min_indent
                new_prefix = " " * max(0, target_indent + rel)
                adjusted.append(new_prefix + l.lstrip())

        return "\n".join(adjusted) + "\n"

    def build_patch(
        self,
        modifications: List[Union[CodeModification, Dict[str, Any]]],
        base_dir: Union[Path, str],
    ) -> PatchBuilderResult:
        start_time = time.time()
        base_path = Path(base_dir)

        if not modifications:
            return PatchBuilderResult(
                success=False,
                error_message="No modifications provided.",
                error_category="EMPTY_MODIFICATIONS",
                generation_latency=time.time() - start_time,
            )

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

        mods_by_file: Dict[str, List[CodeModification]] = {}
        for mod in norm_mods:
            norm_rel = mod.path.replace("\\", "/").strip().lstrip("/")
            mods_by_file.setdefault(norm_rel, []).append(mod)

        diff_chunks: List[str] = []
        applied_records: List[Dict[str, Any]] = []

        for rel_path, file_mods in mods_by_file.items():
            full_path = base_path / rel_path
            if not full_path.exists():
                # Strictly safe placeholder resolution: require a unique, verified exact filename match in base_path
                resolved_rel = None
                if ("path/to/" in rel_path or "..." in rel_path) and rel_path.endswith(".py"):
                    target_name = Path(rel_path).name
                    matching = [p for p in base_path.glob(f"**/{target_name}") if ".git" not in p.parts]
                    if len(matching) == 1:
                        resolved_rel = str(matching[0].relative_to(base_path)).replace("\\", "/")

                if resolved_rel and (base_path / resolved_rel).exists():
                    rel_path = resolved_rel
                    full_path = base_path / resolved_rel
                else:
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
                        error_message=f"Unsupported operation '{op}'.",
                        error_category="INVALID_OPERATION",
                        target_files=list(mods_by_file.keys()),
                        generation_latency=time.time() - start_time,
                    )

                if not anchor:
                    return PatchBuilderResult(
                        success=False,
                        error_message=f"Empty anchor provided in '{rel_path}'.",
                        error_category="EMPTY_ANCHOR",
                        target_files=list(mods_by_file.keys()),
                        generation_latency=time.time() - start_time,
                    )

                anchor_count = current_content.count(anchor)
                if anchor_count == 0:
                    anchor_lines = [l.strip() for l in anchor.splitlines() if l.strip()]
                    if anchor_lines:
                        content_lines = current_content.splitlines(keepends=True)
                        matched_spans = []
                        for i in range(len(content_lines) - len(anchor_lines) + 1):
                            match = True
                            for j, a_line in enumerate(anchor_lines):
                                c_line = content_lines[i + j].strip()
                                a_norm = a_line.replace("'", '"').replace(" ", "")
                                c_norm = c_line.replace("'", '"').replace(" ", "")
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
                        error_message=f"Anchor not found in '{rel_path}': {anchor[:100]}",
                        error_category="ANCHOR_NOT_FOUND",
                        target_files=list(mods_by_file.keys()),
                        generation_latency=time.time() - start_time,
                    )
                elif anchor_count > 1:
                    return PatchBuilderResult(
                        success=False,
                        error_message=f"Anchor ambiguous in '{rel_path}' ({anchor_count} matches).",
                        error_category="ANCHOR_AMBIGUOUS",
                        target_files=list(mods_by_file.keys()),
                        generation_latency=time.time() - start_time,
                    )

                idx = current_content.find(anchor)
                line_start = current_content.rfind("\n", 0, idx) + 1
                line_prefix = current_content[line_start:idx]
                is_pure_prefix = bool(not line_prefix or line_prefix.strip() == "")
                anchor_leading_spaces = len(anchor) - len(anchor.lstrip(" "))
                anchor_indent = (len(line_prefix) + anchor_leading_spaces) if is_pure_prefix else 0

                if op == "insert_before":
                    if is_pure_prefix:
                        norm_code = self.normalize_code_indentation(code, anchor, anchor_indent, "insert_before")
                        current_content = current_content[:line_start] + norm_code + current_content[line_start:]
                    else:
                        norm_code = code if code.endswith("\n") else (code + "\n")
                        current_content = current_content[:idx] + norm_code + current_content[idx:]

                elif op == "insert_after":
                    insert_pos = idx + len(anchor)
                    if not anchor.endswith("\n"):
                        if current_content[insert_pos:insert_pos + 2] == "\r\n":
                            insert_pos += 2
                        elif current_content[insert_pos:insert_pos + 1] == "\n":
                            insert_pos += 1
                    if is_pure_prefix:
                        norm_code = self.normalize_code_indentation(code, anchor, anchor_indent, "insert_after")
                    else:
                        norm_code = code if code.endswith("\n") else (code + "\n")
                    current_content = current_content[:insert_pos] + norm_code + current_content[insert_pos:]

                elif op == "replace":
                    anchor_end = idx + len(anchor)
                    if not anchor.endswith("\n"):
                        if current_content[anchor_end:anchor_end + 2] == "\r\n":
                            anchor_end += 2
                        elif current_content[anchor_end:anchor_end + 1] == "\n":
                            anchor_end += 1
                    if is_pure_prefix:
                        norm_code = self.normalize_code_indentation(code, anchor, anchor_indent, "replace")
                        current_content = current_content[:line_start] + norm_code + current_content[anchor_end:]
                    else:
                        norm_code = code.rstrip("\r\n")
                        current_content = current_content[:idx] + norm_code + current_content[idx + len(anchor):]

                elif op == "delete":
                    end_pos = idx + len(anchor)
                    if not anchor.endswith("\n"):
                        if current_content[end_pos:end_pos + 2] == "\r\n":
                            end_pos += 2
                        elif current_content[end_pos:end_pos + 1] == "\n":
                            end_pos += 1
                    current_content = current_content[:idx] + current_content[end_pos:]

                applied_records.append({
                    "path": rel_path,
                    "operation": op,
                    "target_symbol": mod.target_symbol,
                    "reason": mod.reason,
                })

            if rel_path.endswith(".py"):
                try:
                    ast.parse(current_content)
                except (SyntaxError, IndentationError) as syn_err:
                    return PatchBuilderResult(
                        success=False,
                        error_message=f"Patched file '{rel_path}' failed Python AST syntax verification: {syn_err}",
                        error_category="SYNTAX_ERROR",
                        target_files=list(mods_by_file.keys()),
                        generation_latency=time.time() - start_time,
                    )

            orig_lines = original_content.splitlines(keepends=True)
            mod_lines = current_content.splitlines(keepends=True)
            file_diff = list(
                difflib.unified_diff(
                    orig_lines,
                    mod_lines,
                    fromfile=f"a/{rel_path}",
                    tofile=f"b/{rel_path}",
                )
            )
            if file_diff:
                diff_chunks.append("".join(file_diff))

        if not diff_chunks:
            return PatchBuilderResult(
                success=False,
                error_message="Modifications resulted in an empty diff (no changes made).",
                error_category="EMPTY_DIFF",
                generation_latency=time.time() - start_time,
            )

        full_patch = "".join(diff_chunks)
        val_res = self.patch_manager.validate_patch(full_patch)
        if not val_res.is_valid:
            return PatchBuilderResult(
                success=False,
                error_message=f"Generated patch failed validation: {val_res.error_message}",
                error_category="INVALID_DIFF_STRUCTURE",
                target_files=list(mods_by_file.keys()),
                generation_latency=time.time() - start_time,
            )

        return PatchBuilderResult(
            success=True,
            unified_diff=full_patch,
            applied_modifications=applied_records,
            anchor_found=True,
            anchor_unique=True,
            target_files=list(mods_by_file.keys()),
            generation_latency=time.time() - start_time,
        )
