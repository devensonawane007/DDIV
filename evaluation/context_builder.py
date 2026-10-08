"""Targeted Context Builder for DDIV.

Constructs focused, AST-aware source and test context bounded by budget.
Avoids dumping unrelated code while providing callers, callees, and representative tests.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field


class TargetedContext(BaseModel):
    """Structured context artifact produced by TargetedContextBuilder."""

    formatted_source_code: str = ""
    formatted_tests_context: str = ""
    context_files: List[str] = Field(default_factory=list)
    selected_symbols: List[str] = Field(default_factory=list)
    selected_tests: List[str] = Field(default_factory=list)
    character_size: int = 0
    token_estimate: int = 0


class TargetedContextBuilder:
    """Extracts precise symbol implementations, callers, and test references from workspace."""

    def __init__(self, char_budget: int = 10000):
        self.char_budget = char_budget

    def _extract_ast_nodes(
        self, content: str, target_symbols: List[str]
    ) -> List[Tuple[int, int, str]]:
        """Find line ranges (start_line, end_line, name) for targeted symbols via AST."""
        try:
            tree = ast.parse(content)
        except Exception:
            return []

        ranges: List[Tuple[int, int, str]] = []
        clean_targets = {s.split(".")[-1].strip() for s in target_symbols if s.strip()}

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not clean_targets or node.name in clean_targets:
                    start = getattr(node, "lineno", 1)
                    end = getattr(node, "end_lineno", start + 20)
                    ranges.append((start, end, node.name))

        return sorted(ranges, key=lambda x: x[0])

    def _slice_source_with_imports(
        self, content: str, target_symbols: List[str], max_chars: int
    ) -> Tuple[str, List[str]]:
        """Slice imports and target functions/classes, falling back gracefully."""
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)
        if not lines:
            return "", []

        # 1. Extract header imports (first ~30 lines or until non-import/docstring)
        import_lines: List[str] = []
        for i, line in enumerate(lines[:40]):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ", "#", '"""', "'''")) or not stripped:
                import_lines.append(line)
            else:
                break

        # 2. Extract AST ranges for symbols
        ast_ranges = self._extract_ast_nodes(content, target_symbols)
        selected_symbols: List[str] = []
        sliced_blocks: List[str] = []

        if ast_ranges:
            for start, end, name in ast_ranges:
                selected_symbols.append(name)
                # Include 3 lines before and after for context
                context_start = max(1, start - 3)
                context_end = min(total_lines, end + 3)
                block = "".join(lines[context_start - 1 : context_end])
                sliced_blocks.append(f"# --- Target Symbol: {name} (lines {context_start}-{context_end}) ---\n{block}")
                if sum(len(b) for b in sliced_blocks) >= max_chars:
                    break
        else:
            # Fallback: substring search or header snippet
            first_match = -1
            for sym in target_symbols:
                clean = sym.split(".")[-1].strip()
                for pat in [f"def {clean}", f"class {clean}", clean]:
                    idx = content.find(pat)
                    if idx != -1:
                        first_match = idx
                        selected_symbols.append(clean)
                        break
                if first_match != -1:
                    break

            if first_match != -1:
                start_char = max(0, content.rfind("\n", 0, max(0, first_match - 200)))
                end_char = min(len(content), start_char + max_chars)
                sliced_blocks.append(content[start_char:end_char])
            else:
                sliced_blocks.append(content[:max_chars])

        combined = "".join(import_lines) + "\n# ...\n\n" + "\n\n# ...\n\n".join(sliced_blocks)
        if len(combined) > max_chars:
            combined = combined[:max_chars] + "\n# ... [truncated to fit context budget]"

        return combined, selected_symbols

    def _discover_relevant_tests(
        self,
        workspace_path: Path,
        located_files: List[str],
        target_symbols: List[str],
        max_chars: int = 2500,
    ) -> Tuple[str, List[str]]:
        """Search workspace for representative test cases targeting the located modules."""
        test_blocks: List[str] = []
        selected_tests: List[str] = []
        clean_symbols = {s.split(".")[-1].strip() for s in target_symbols if s.strip()}

        search_stems = [Path(f).stem for f in located_files if not f.startswith("tests/")]

        candidate_test_files: List[Path] = []
        for stem in search_stems:
            for p in workspace_path.glob(f"**/test_*{stem}*.py"):
                if p not in candidate_test_files:
                    candidate_test_files.append(p)
            for p in workspace_path.glob(f"**/*{stem}*_test.py"):
                if p not in candidate_test_files:
                    candidate_test_files.append(p)

        budget_remaining = max_chars
        for tf in candidate_test_files[:3]:
            try:
                t_content = tf.read_text(encoding="utf-8", errors="ignore")
                rel_path = str(tf.relative_to(workspace_path)).replace("\\", "/")

                # Look for test functions mentioning target symbols
                lines = t_content.splitlines(keepends=True)
                ast_ranges = self._extract_ast_nodes(t_content, list(clean_symbols))

                if ast_ranges:
                    for start, end, t_name in ast_ranges[:2]:
                        selected_tests.append(f"{rel_path}::{t_name}")
                        block = "".join(lines[max(0, start - 1) : min(len(lines), end + 2)])
                        test_blocks.append(f"### Test: {rel_path}::{t_name}\n```python\n{block}\n```")
                        budget_remaining -= len(block)
                        if budget_remaining <= 200:
                            break
                else:
                    # Take first test function
                    first_test = t_content[:min(len(t_content), 800)]
                    selected_tests.append(rel_path)
                    test_blocks.append(f"### Test: {rel_path}\n```python\n{first_test}\n```")
                    budget_remaining -= len(first_test)

                if budget_remaining <= 200:
                    break
            except Exception:
                continue

        return "\n\n".join(test_blocks), selected_tests

    def build_context(
        self,
        workspace_path: Path,
        located_files: List[str],
        target_symbols: Optional[List[str]] = None,
    ) -> TargetedContext:
        """Build compact, targeted source and test context within budget."""
        target_symbols = target_symbols or []
        source_blocks: List[str] = []
        context_files: List[str] = []
        all_selected_symbols: List[str] = []

        # Split budget: 75% for source code, 25% for tests
        source_budget = int(self.char_budget * 0.75)
        test_budget = int(self.char_budget * 0.25)

        # Filter out tests from located files for source context
        code_files = [
            f.replace("\\", "/").strip()
            for f in located_files
            if not f.startswith("tests/") and "/test_" not in f and not f.endswith("_test.py")
        ]

        if code_files:
            per_file_budget = max(1500, source_budget // len(code_files[:3]))
            for r_file in code_files[:3]:
                fpath = workspace_path / r_file
                if fpath.exists():
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="ignore")
                        snippet, syms = self._slice_source_with_imports(
                            content, target_symbols, per_file_budget
                        )
                        source_blocks.append(f"### File: {r_file}\n```python\n{snippet}\n```")
                        context_files.append(r_file)
                        all_selected_symbols.extend(syms)
                    except Exception:
                        continue

        formatted_source = "\n\n".join(source_blocks) if source_blocks else "No relevant source files located."

        # Discover relevant repository tests
        formatted_tests, selected_tests = self._discover_relevant_tests(
            workspace_path, located_files, target_symbols, test_budget
        )

        total_chars = len(formatted_source) + len(formatted_tests)
        token_est = total_chars // 4

        return TargetedContext(
            formatted_source_code=formatted_source,
            formatted_tests_context=formatted_tests,
            context_files=context_files,
            selected_symbols=sorted(set(all_selected_symbols)),
            selected_tests=selected_tests,
            character_size=total_chars,
            token_estimate=token_est,
        )
