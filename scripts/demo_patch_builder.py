"""Demo Patch Builder: Whitespace-aware, AST-grounded, and syntax-verified patch construction.

Provides:
1. StructuralCodeModification: Extended modification specification with AST targeting.
2. ASTScopeRegion: Bounded structural regions for accurate class/method scoping.
3. find_anchor_occurrences: 4-tier robust anchor matching strategy.
4. DemoPatchBuilder: Unified diff construction with indentation alignment and AST verification.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import difflib
import hashlib
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from pydantic import BaseModel, Field

from evaluation.patch_builder import CodeModification, PatchBuilderResult
from evaluation.patch_manager import PatchManager


def compute_source_fingerprint(text: str) -> str:
    """Deterministic SHA-256 fingerprint of normalized source block text.

    Normalizes line endings (CRLF/CR to LF), strips outer whitespace, and collapses trailing
    whitespace on each line to ensure reproducible hashing across operating systems.
    """
    if not text:
        return ""
    norm_lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while norm_lines and not norm_lines[0].strip():
        norm_lines.pop(0)
    while norm_lines and not norm_lines[-1].strip():
        norm_lines.pop()
    norm_text = "\n".join(norm_lines)
    return hashlib.sha256(norm_text.encode("utf-8")).hexdigest()[:16]


class StructuralCodeModification(BaseModel):
    """Extended code modification with AST-grounded structural targeting metadata."""

    path: str = Field(..., description="Relative path to target file")
    target_symbol: Optional[str] = Field(None, description="Qualified symbol, e.g. 'ClassA.method' or 'func'")
    target_class: Optional[str] = Field(None, description="Enclosing class name, e.g. 'ClassA'")
    target_method: Optional[str] = Field(None, description="Target method/function name, e.g. 'method'")
    node_type: Optional[str] = Field(None, description="AST node type, e.g. 'FunctionDef', 'ClassDef'")
    line_range: Optional[Tuple[int, int]] = Field(None, description="1-based (start_line, end_line) in source file")
    surrounding_context: Optional[str] = Field(None, description="Surrounding code block to disambiguate")
    source_fingerprint: Optional[str] = Field(None, description="Expected SHA-256 fingerprint of target block")
    operation: str = Field(..., description="Operation: 'insert_after', 'insert_before', 'replace', or 'delete'")
    anchor: str = Field(..., description="Code snippet from source file to anchor the change")
    code: str = Field(default="", description="Code to insert or replace with (empty for delete)")
    reason: str = Field(default="", description="Semantic rationale for this specific change")


@dataclass
class ASTScopeRegion:
    """Bounded structural region within a Python source file."""
    qualified_name: str
    class_name: Optional[str]
    name: str
    node_type: str
    start_line: int
    end_line: int
    start_idx: int
    end_idx: int
    header_text: str
    body_text: str
    full_text: str
    fingerprint: str


def byte_col_to_char_col(line_str: str, byte_col: int) -> int:
    """Convert a 0-based UTF-8 byte column offset from Python AST into a character index."""
    line_bytes = line_str.encode("utf-8")
    safe_byte_col = min(len(line_bytes), max(0, byte_col))
    return len(line_bytes[:safe_byte_col].decode("utf-8", errors="replace"))


def find_ast_scopes(content: str) -> List[ASTScopeRegion]:
    """Parse Python source and extract all class and function AST scope regions recursively with exact character offsets."""
    try:
        tree = ast.parse(content)
    except Exception:
        return []

    lines = content.splitlines(keepends=True)
    line_starts = [0]
    for l in lines:
        line_starts.append(line_starts[-1] + len(l))

    def get_span(node: ast.AST) -> Tuple[int, int]:
        s_line = getattr(node, "lineno", 1)
        s_byte_col = getattr(node, "col_offset", 0)
        e_line = getattr(node, "end_lineno", s_line)

        if 1 <= s_line <= len(lines):
            line_str = lines[s_line - 1]
            s_char_col = byte_col_to_char_col(line_str, s_byte_col)
            if not line_str[:s_char_col].strip():
                s_idx = line_starts[s_line - 1]
            else:
                s_idx = line_starts[s_line - 1] + s_char_col
        else:
            s_idx = 0

        if 1 <= e_line <= len(lines):
            end_line_str = lines[e_line - 1]
            e_byte_col = getattr(node, "end_col_offset", len(end_line_str.encode("utf-8")))
            e_char_col = byte_col_to_char_col(end_line_str, e_byte_col)
            e_idx = line_starts[e_line - 1] + e_char_col
        else:
            e_idx = len(content)

        return s_idx, e_idx

    scopes: List[ASTScopeRegion] = []

    def walk_scopes(node: ast.AST, parent_class: Optional[str] = None):
        for child in getattr(node, "body", []):
            if isinstance(child, ast.ClassDef):
                s_idx, e_idx = get_span(child)
                c_text = content[s_idx:e_idx]
                qname = f"{parent_class}.{child.name}" if parent_class else child.name
                scopes.append(ASTScopeRegion(
                    qualified_name=qname,
                    class_name=parent_class,
                    name=child.name,
                    node_type="ClassDef",
                    start_line=child.lineno,
                    end_line=getattr(child, "end_lineno", child.lineno),
                    start_idx=s_idx,
                    end_idx=e_idx,
                    header_text=c_text.splitlines()[0] if c_text.splitlines() else "",
                    body_text=c_text,
                    full_text=c_text,
                    fingerprint=compute_source_fingerprint(c_text),
                ))
                walk_scopes(child, parent_class=qname)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                s_idx, e_idx = get_span(child)
                f_text = content[s_idx:e_idx]
                qname = f"{parent_class}.{child.name}" if parent_class else child.name
                ntype = "AsyncFunctionDef" if isinstance(child, ast.AsyncFunctionDef) else "FunctionDef"
                scopes.append(ASTScopeRegion(
                    qualified_name=qname,
                    class_name=parent_class,
                    name=child.name,
                    node_type=ntype,
                    start_line=child.lineno,
                    end_line=getattr(child, "end_lineno", child.lineno),
                    start_idx=s_idx,
                    end_idx=e_idx,
                    header_text=f_text.splitlines()[0] if f_text.splitlines() else "",
                    body_text=f_text,
                    full_text=f_text,
                    fingerprint=compute_source_fingerprint(f_text),
                ))

    walk_scopes(tree)
    return scopes

def resolve_target_scope(
    scopes: List[ASTScopeRegion],
    target_symbol: Optional[str] = None,
    target_class: Optional[str] = None,
    target_method: Optional[str] = None,
) -> Tuple[Optional[ASTScopeRegion], List[str]]:
    """Resolve an AST scope from target metadata.

    Returns (matched_scope, candidate_qualified_names).
    """
    candidates: List[ASTScopeRegion] = []

    # Priority 1: Explicit target_class + target_method
    if target_class and target_method:
        for s in scopes:
            cls_match = (
                s.class_name == target_class
                or (s.class_name and (s.class_name == target_class or s.class_name.endswith(f".{target_class}")))
            )
            if cls_match and s.name == target_method:
                candidates.append(s)
        if len(candidates) == 1:
            return candidates[0], [candidates[0].qualified_name]
        return None, [s.qualified_name for s in candidates]

    # Priority 2: target_symbol
    if target_symbol:
        sym = target_symbol.strip()
        clean_sym = sym.split("(")[0].strip()
        parts = [p for p in clean_sym.split(".") if p]

        # 2a: Exact qualified_name match
        for s in scopes:
            if s.qualified_name == clean_sym:
                candidates.append(s)
        if len(candidates) == 1:
            return candidates[0], [candidates[0].qualified_name]
        if len(candidates) > 1:
            return None, [s.qualified_name for s in candidates]

        # 2b: Suffix / short qualified match (e.g. Class.method matching pkg.Class.method)
        if len(parts) >= 2:
            short_qname = f"{parts[-2]}.{parts[-1]}"
            for s in scopes:
                if s.qualified_name.endswith(short_qname):
                    if s not in candidates:
                        candidates.append(s)
            if len(candidates) == 1:
                return candidates[0], [candidates[0].qualified_name]
            if len(candidates) > 1:
                return None, [s.qualified_name for s in candidates]

        # 2c: Unqualified name match
        last_part = parts[-1]
        for s in scopes:
            if s.name == last_part:
                if s not in candidates:
                    candidates.append(s)
        if len(candidates) == 1:
            return candidates[0], [candidates[0].qualified_name]
        return None, [s.qualified_name for s in candidates]

    # Priority 3: target_class alone
    if target_class:
        for s in scopes:
            if s.node_type == "ClassDef" and (
                s.name == target_class
                or s.qualified_name == target_class
                or s.qualified_name.endswith(f".{target_class}")
            ):
                candidates.append(s)
        if len(candidates) == 1:
            return candidates[0], [candidates[0].qualified_name]
        return None, [s.qualified_name for s in candidates]

    # Priority 4: target_method alone
    if target_method:
        for s in scopes:
            if s.name == target_method and s.node_type in ("FunctionDef", "AsyncFunctionDef"):
                candidates.append(s)
        if len(candidates) == 1:
            return candidates[0], [candidates[0].qualified_name]
        return None, [s.qualified_name for s in candidates]

    return None, []


def find_anchor_occurrences(text: str, anchor: str, is_python: bool = True) -> Tuple[int, str, List[int]]:
    """Search for anchor in text using the 4-tier matching strategy.

    Returns:
        (match_count, resolved_anchor_string, list_of_start_byte_indices)
    """
    if not text or not anchor:
        return 0, anchor, []

    # Tier 1: Exact Verbatim Match
    indices: List[int] = []
    idx = text.find(anchor)
    while idx != -1:
        indices.append(idx)
        idx = text.find(anchor, idx + 1)

    if indices:
        return len(indices), anchor, indices

    content_lines = text.splitlines(keepends=True)
    line_offsets = [0]
    for cl in content_lines:
        line_offsets.append(line_offsets[-1] + len(cl))

    # Tier 2: Normalized Line-by-Line Match
    anchor_lines = [l.strip() for l in anchor.splitlines() if l.strip()]
    if anchor_lines:
        matched_spans: List[str] = []
        matched_indices: List[int] = []
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
                start_off = line_offsets[i]
                if not anchor.endswith("\n") and verbatim_chunk.endswith("\n"):
                    verbatim_chunk = verbatim_chunk.rstrip("\r\n")
                if verbatim_chunk not in matched_spans:
                    matched_spans.append(verbatim_chunk)
                matched_indices.append(start_off)

        if len(matched_spans) == 1 and len(matched_indices) == 1:
            return 1, matched_spans[0], matched_indices
        elif len(matched_indices) > 1:
            chosen = matched_spans[0] if len(matched_spans) == 1 else anchor
            return len(matched_indices), chosen, matched_indices

    # Tier 3: Whitespace-Collapsed Sliding Window
    norm_anchor_clean = "".join(anchor.replace("'", '"').split())
    if len(norm_anchor_clean) >= 8:
        max_w = min(len(content_lines), max(len(anchor_lines) + 6, 8))
        matched_spans = []
        matched_indices = []
        matched_start_lines: Set[int] = set()
        for w in range(1, max_w + 1):
            for i in range(len(content_lines) - w + 1):
                if i in matched_start_lines:
                    continue
                chunk = "".join(content_lines[i : i + w])
                norm_chunk = "".join(chunk.replace("'", '"').split())
                if norm_chunk == norm_anchor_clean:
                    matched_start_lines.add(i)
                    verbatim = chunk
                    if not anchor.endswith("\n") and verbatim.endswith("\n"):
                        verbatim = verbatim.rstrip("\r\n")
                    if verbatim not in matched_spans:
                        matched_spans.append(verbatim)
                    matched_indices.append(line_offsets[i])

        if len(matched_spans) == 1 and len(matched_indices) == 1:
            return 1, matched_spans[0], matched_indices
        elif len(matched_indices) > 1:
            chosen = matched_spans[0] if len(matched_spans) == 1 else anchor
            return len(matched_indices), chosen, matched_indices

    # Tier 4: AST Function / Method Signature Header Match
    if is_python:
        stripped_anchor = anchor.strip()
        if stripped_anchor.startswith(("def ", "async def ", "class ")):
            fn_match = re.match(r"(?:async\s+def|def|class)\s+([a-zA-Z_][a-zA-Z0-9_]*)", stripped_anchor)
            if fn_match:
                target_name = fn_match.group(1)
                try:
                    tree = ast.parse(text)
                    matching_nodes = [
                        node for node in ast.walk(tree)
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                        and node.name == target_name
                    ]
                    if len(matching_nodes) == 1:
                        target_node = matching_nodes[0]
                        sig_start = target_node.lineno - 1
                        if target_node.body:
                            body_start = target_node.body[0].lineno - 1
                            sig_lines = content_lines[sig_start:body_start]
                        else:
                            sig_lines = [content_lines[sig_start]]
                        sig_text = "".join(sig_lines)
                        colon_pos = sig_text.rfind(":")
                        if colon_pos != -1:
                            verbatim_sig = sig_text[: colon_pos + 1]
                            if not anchor.endswith("\n") and verbatim_sig.endswith("\n"):
                                verbatim_sig = verbatim_sig.rstrip("\r\n")
                            return 1, verbatim_sig, [line_offsets[sig_start]]
                    elif len(matching_nodes) > 1:
                        node_indices = [line_offsets[n.lineno - 1] for n in matching_nodes]
                        return len(matching_nodes), anchor, node_indices
                except Exception:
                    pass

    return 0, anchor, []

class DemoPatchBuilder:
    """Constructs robust unified diffs with line-aligned anchoring and AST syntax verification."""

    last_result: Optional[PatchBuilderResult] = None

    def __init__(self, patch_manager: Optional[PatchManager] = None):
        self.patch_manager = patch_manager or PatchManager()
        self.last_result: Optional[PatchBuilderResult] = None

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

    @staticmethod
    def validate_ast_scopes(content: str, rel_path: str = "") -> Optional[str]:
        """Validate Python code structure and statement scoping.

        Rejects:
        1. 'return' statements directly or conditionally inside a class body (outside methods).
        2. Executable statements directly at class scope referencing instance variable 'self'.

        Does NOT reject:
        - Valid methods or inner classes with 'self'.
        - Class attributes, constants, type annotations.
        - Docstrings or class-level definitions.

        Returns:
            Error message if a scope violation is detected, None if valid.
        """
        try:
            tree = ast.parse(content)
        except Exception:
            return None  # Let standard syntax check handle parse errors

        class ScopeVisitor(ast.NodeVisitor):
            def __init__(self):
                self.error: Optional[str] = None

            def visit_ClassDef(self, node: ast.ClassDef):
                if self.error:
                    return
                for stmt in node.body:
                    # Inner functions/methods and nested classes define their own legitimate scopes
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        self.generic_visit(stmt)
                        continue

                    # For direct class body statements (if, while, assignments, expressions, try, with):
                    for subnode in ast.walk(stmt):
                        if isinstance(subnode, ast.Return):
                            self.error = (
                                f"Illegal 'return' statement at class scope '{node.name}' (line {subnode.lineno}). "
                                f"A 'return' statement cannot execute in a class body; it must be inside a method definition."
                            )
                            return
                        if isinstance(subnode, ast.Name) and subnode.id == "self":
                            self.error = (
                                f"Illegal instance variable reference 'self' at class scope '{node.name}' (line {subnode.lineno}). "
                                f"Instance attributes or methods cannot be accessed directly in class body scope. "
                                f"To place statements inside a method, use 'operation': 'insert_after' with the 'def ...:' header as anchor, not 'insert_before'."
                            )
                            return

                    self.generic_visit(stmt)

        visitor = ScopeVisitor()
        visitor.visit(tree)
        return visitor.error

    @classmethod
    def get_undefined_variable_references(cls, content: str) -> Set[Tuple[str, str, int]]:
        """Extract set of (function_name, var_name, lineno) for variable loads without definition."""
        try:
            tree = ast.parse(content)
        except Exception:
            return set()

        import builtins

        builtins_set = set(dir(builtins)) | {
            "__file__",
            "__name__",
            "__doc__",
            "__package__",
            "__spec__",
            "__annotations__",
        }

        module_symbols: Set[str] = set()
        has_wildcard = False
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                module_symbols.add(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module_symbols.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        has_wildcard = True
                    else:
                        module_symbols.add(alias.asname or alias.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for sub in ast.walk(target):
                        if isinstance(sub, ast.Name):
                            module_symbols.add(sub.id)

        if has_wildcard:
            return set()

        class ExprChecker(ast.NodeVisitor):
            def __init__(self, base_known: Set[str]):
                self.known_stack = [set(base_known)]
                self.errors: Set[Tuple[str, int]] = set()
                self.newly_assigned: Set[str] = set()

            def visit_Name(self, n: ast.Name):
                if isinstance(n.ctx, ast.Load):
                    current_known = set().union(*self.known_stack)
                    if n.id not in current_known and n.id not in module_symbols and n.id not in builtins_set:
                        self.errors.add((n.id, n.lineno))
                self.generic_visit(n)

            def visit_NamedExpr(self, n: ast.NamedExpr):
                # Walrus operator (x := expr): value is evaluated, target is bound
                self.visit(n.value)
                if isinstance(n.target, ast.Name):
                    self.known_stack[-1].add(n.target.id)
                    self.newly_assigned.add(n.target.id)
                self.visit(n.target)

            def visit_ListComp(self, n: ast.ListComp):
                comp_targets: Set[str] = set()
                for gen in n.generators:
                    self.visit(gen.iter)
                    for t in ast.walk(gen.target):
                        if isinstance(t, ast.Name):
                            comp_targets.add(t.id)
                    for if_expr in gen.ifs:
                        self.known_stack.append(comp_targets)
                        self.visit(if_expr)
                        self.known_stack.pop()
                self.known_stack.append(comp_targets)
                self.visit(n.elt)
                self.known_stack.pop()

            visit_SetComp = visit_ListComp
            visit_GeneratorExp = visit_ListComp

            def visit_DictComp(self, n: ast.DictComp):
                comp_targets: Set[str] = set()
                for gen in n.generators:
                    self.visit(gen.iter)
                    for t in ast.walk(gen.target):
                        if isinstance(t, ast.Name):
                            comp_targets.add(t.id)
                    for if_expr in gen.ifs:
                        self.known_stack.append(comp_targets)
                        self.visit(if_expr)
                        self.known_stack.pop()
                self.known_stack.append(comp_targets)
                self.visit(n.key)
                self.visit(n.value)
                self.known_stack.pop()

            def visit_Lambda(self, n: ast.Lambda):
                lam_args = {a.arg for a in n.args.posonlyargs + n.args.args + n.args.kwonlyargs}
                if n.args.vararg:
                    lam_args.add(n.args.vararg.arg)
                if n.args.kwarg:
                    lam_args.add(n.args.kwarg.arg)
                self.known_stack.append(lam_args)
                self.visit(n.body)
                self.known_stack.pop()

        all_errors: Set[Tuple[str, str, int]] = set()

        def collect_defined_names(node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> Set[str]:
            names: Set[str] = set()
            for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                names.add(arg.arg)
            if node.args.vararg:
                names.add(node.args.vararg.arg)
            if node.args.kwarg:
                names.add(node.args.kwarg.arg)
            names.add(node.name)

            class DefVisitor(ast.NodeVisitor):
                def visit_FunctionDef(self, n: ast.FunctionDef):
                    names.add(n.name)
                visit_AsyncFunctionDef = visit_FunctionDef
                def visit_ClassDef(self, n: ast.ClassDef):
                    names.add(n.name)
                def visit_Assign(self, n: ast.Assign):
                    for t in n.targets:
                        for sub in ast.walk(t):
                            if isinstance(sub, ast.Name):
                                names.add(sub.id)
                    self.generic_visit(n)
                def visit_AnnAssign(self, n: ast.AnnAssign):
                    for sub in ast.walk(n.target):
                        if isinstance(sub, ast.Name):
                            names.add(sub.id)
                    self.generic_visit(n)
                def visit_AugAssign(self, n: ast.AugAssign):
                    for sub in ast.walk(n.target):
                        if isinstance(sub, ast.Name):
                            names.add(sub.id)
                    self.generic_visit(n)
                def visit_NamedExpr(self, n: ast.NamedExpr):
                    if isinstance(n.target, ast.Name):
                        names.add(n.target.id)
                    self.generic_visit(n)
                def visit_For(self, n: ast.For):
                    for sub in ast.walk(n.target):
                        if isinstance(sub, ast.Name):
                            names.add(sub.id)
                    self.generic_visit(n)
                visit_AsyncFor = visit_For
                def visit_With(self, n: ast.With):
                    for item in n.items:
                        if item.optional_vars:
                            for sub in ast.walk(item.optional_vars):
                                if isinstance(sub, ast.Name):
                                    names.add(sub.id)
                    self.generic_visit(n)
                visit_AsyncWith = visit_With
                def visit_Global(self, n: ast.Global):
                    names.update(n.names)
                def visit_Nonlocal(self, n: ast.Nonlocal):
                    names.update(n.names)
                def visit_Import(self, n: ast.Import):
                    for alias in n.names:
                        names.add(alias.asname or alias.name)
                def visit_ImportFrom(self, n: ast.ImportFrom):
                    for alias in n.names:
                        names.add(alias.asname or alias.name)
                def visit_ExceptHandler(self, n: ast.ExceptHandler):
                    if n.name:
                        names.add(n.name)
                    self.generic_visit(n)

            visitor = DefVisitor()
            for stmt in node.body:
                visitor.visit(stmt)
            return names

        def check_function(func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef], parent_scope: Set[str]):
            all_defs = collect_defined_names(func_node)
            known = set(parent_scope)
            for arg in func_node.args.posonlyargs + func_node.args.args + func_node.args.kwonlyargs:
                known.add(arg.arg)
            if func_node.args.vararg:
                known.add(func_node.args.vararg.arg)
            if func_node.args.kwarg:
                known.add(func_node.args.kwarg.arg)
            known.add(func_node.name)

            for stmt in func_node.body:
                if isinstance(stmt, (ast.Global, ast.Nonlocal)):
                    known.update(stmt.names)

            def get_targets(target_node: ast.AST) -> Set[str]:
                names: Set[str] = set()
                for n in ast.walk(target_node):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
                return names

            def check_expr(expr_node: ast.AST):
                checker = ExprChecker(known)
                checker.visit(expr_node)
                known.update(checker.newly_assigned)
                for var_name, line in checker.errors:
                    all_errors.add((func_node.name, var_name, line))

            def visit_stmts(stmts: List[ast.stmt]):
                for stmt in stmts:
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        known.add(stmt.name)
                        check_function(stmt, parent_scope=known | all_defs)
                    elif isinstance(stmt, ast.ClassDef):
                        known.add(stmt.name)
                        for m in stmt.body:
                            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                check_function(m, parent_scope=known | all_defs | {"self", "cls"})
                    elif isinstance(stmt, (ast.Global, ast.Nonlocal)):
                        known.update(stmt.names)
                    elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
                        for alias in stmt.names:
                            known.add(alias.asname or alias.name)
                    elif isinstance(stmt, ast.Assign):
                        check_expr(stmt.value)
                        for t in stmt.targets:
                            known.update(get_targets(t))
                    elif isinstance(stmt, ast.AnnAssign):
                        if stmt.value:
                            check_expr(stmt.value)
                        known.update(get_targets(stmt.target))
                    elif isinstance(stmt, ast.AugAssign):
                        if isinstance(stmt.target, ast.Name):
                            if stmt.target.id not in known and stmt.target.id not in module_symbols and stmt.target.id not in builtins_set:
                                all_errors.add((func_node.name, stmt.target.id, stmt.target.lineno))
                        else:
                            check_expr(stmt.target)
                        check_expr(stmt.value)
                        known.update(get_targets(stmt.target))
                    elif isinstance(stmt, ast.Return):
                        if stmt.value:
                            check_expr(stmt.value)
                    elif isinstance(stmt, ast.Expr):
                        check_expr(stmt.value)
                    elif isinstance(stmt, (ast.If, ast.While)):
                        check_expr(stmt.test)
                        visit_stmts(stmt.body)
                        visit_stmts(stmt.orelse)
                    elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                        check_expr(stmt.iter)
                        known.update(get_targets(stmt.target))
                        visit_stmts(stmt.body)
                        visit_stmts(stmt.orelse)
                    elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                        for item in stmt.items:
                            check_expr(item.context_expr)
                            if item.optional_vars:
                                known.update(get_targets(item.optional_vars))
                        visit_stmts(stmt.body)
                    elif isinstance(stmt, ast.Try):
                        visit_stmts(stmt.body)
                        for h in stmt.handlers:
                            if h.name:
                                known.add(h.name)
                            visit_stmts(h.body)
                        visit_stmts(stmt.orelse)
                        visit_stmts(stmt.finalbody)

            visit_stmts(func_node.body)

        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                check_function(n, set())
            elif isinstance(n, ast.ClassDef):
                for m in n.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        check_function(m, {"self", "cls"})

        return all_errors

    @classmethod
    def validate_variable_definitions(
        cls, current_content: str, original_content: str = "", rel_path: str = ""
    ) -> Optional[str]:
        """Validate that candidate patch does not introduce undefined local variable references.

        Uses differential checking against original_content to avoid false positives on pre-existing
        wildcard imports, dynamic definitions, or test mocks.
        """
        current_undef = cls.get_undefined_variable_references(current_content)
        if not current_undef:
            return None

        orig_undef = cls.get_undefined_variable_references(original_content) if original_content else set()
        orig_pairs = {(func, var) for func, var, _ in orig_undef}
        introduced = [(func, var, line) for func, var, line in current_undef if (func, var) not in orig_pairs]
        if not introduced:
            return None

        func_name, var_name, lineno = introduced[0]
        return (
            f"Undefined local variable '{var_name}' referenced before assignment in function '{func_name}' (line {lineno})."
        )

    def build_patch(
        self,
        modifications: List[Union[CodeModification, Dict[str, Any]]],
        base_dir: Union[Path, str],
    ) -> PatchBuilderResult:
        start_time = time.time()
        base_path = Path(base_dir)

        def _finish(res: PatchBuilderResult) -> PatchBuilderResult:
            self.last_result = res
            DemoPatchBuilder.last_result = res
            return res

        if not modifications:
            return _finish(
                PatchBuilderResult(
                    success=False,
                    error_message="No modifications provided.",
                    error_category="EMPTY_MODIFICATIONS",
                    generation_latency=time.time() - start_time,
                )
            )

        norm_mods: List[Union[StructuralCodeModification, CodeModification]] = []
        for mod in modifications:
            if isinstance(mod, (StructuralCodeModification, CodeModification)):
                norm_mods.append(mod)
            elif isinstance(mod, dict):
                try:
                    norm_mods.append(StructuralCodeModification(**mod))
                except Exception:
                    try:
                        norm_mods.append(CodeModification(**mod))
                    except Exception as exc:
                        return _finish(
                            PatchBuilderResult(
                                success=False,
                                error_message=f"Malformed code modification payload: {exc}",
                                error_category="MALFORMED_OUTPUT",
                                generation_latency=time.time() - start_time,
                            )
                        )
            else:
                return _finish(
                    PatchBuilderResult(
                        success=False,
                        error_message=f"Unsupported modification type: {type(mod)}",
                        error_category="MALFORMED_OUTPUT",
                        generation_latency=time.time() - start_time,
                    )
                )

        mods_by_file: Dict[str, List[Union[StructuralCodeModification, CodeModification]]] = {}
        for mod in norm_mods:
            norm_rel = mod.path.replace("\\", "/").strip().lstrip("/")
            mods_by_file.setdefault(norm_rel, []).append(mod)

        diff_chunks: List[str] = []
        applied_records: List[Dict[str, Any]] = []

        for rel_path, file_mods in mods_by_file.items():
            # Security: Validate target path does not escape base directory
            target_file_path = base_path / rel_path
            try:
                target_file_path.resolve().relative_to(base_path.resolve())
            except (ValueError, Exception):
                return _finish(
                    PatchBuilderResult(
                        success=False,
                        error_message=f"Security Error: Target path '{rel_path}' resolves outside workspace.",
                        error_category="INVALID_TARGET_PATH",
                        target_files=list(mods_by_file.keys()),
                        generation_latency=time.time() - start_time,
                    )
                )

            full_path = target_file_path
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
                    return _finish(
                        PatchBuilderResult(
                            success=False,
                            error_message=f"Target file not found in workspace: {rel_path}",
                            error_category="FILE_NOT_FOUND",
                            target_files=list(mods_by_file.keys()),
                            generation_latency=time.time() - start_time,
                        )
                    )

            try:
                original_content = full_path.read_text(encoding="utf-8")
            except Exception as read_err:
                return _finish(
                    PatchBuilderResult(
                        success=False,
                        error_message=f"Failed to read target file '{rel_path}': {read_err}",
                        error_category="FILE_READ_ERROR",
                        target_files=list(mods_by_file.keys()),
                        generation_latency=time.time() - start_time,
                    )
                )

            current_content = original_content

            for mod in file_mods:
                op = mod.operation.lower().strip()
                anchor = mod.anchor
                code = mod.code or ""
                target_symbol = getattr(mod, "target_symbol", None)
                target_class = getattr(mod, "target_class", None)
                target_method = getattr(mod, "target_method", None)
                line_range = getattr(mod, "line_range", None)
                source_fingerprint = getattr(mod, "source_fingerprint", None)
                surrounding_context = getattr(mod, "surrounding_context", None)

                if op not in ("insert_after", "insert_before", "replace", "delete"):
                    return _finish(
                        PatchBuilderResult(
                            success=False,
                            error_message=f"Unsupported operation '{op}'.",
                            error_category="INVALID_OPERATION",
                            target_files=list(mods_by_file.keys()),
                            generation_latency=time.time() - start_time,
                        )
                    )

                if not anchor:
                    return _finish(
                        PatchBuilderResult(
                            success=False,
                            error_message=f"Empty anchor provided in '{rel_path}'.",
                            error_category="EMPTY_ANCHOR",
                            target_files=list(mods_by_file.keys()),
                            generation_latency=time.time() - start_time,
                        )
                    )

                is_python = rel_path.endswith(".py")
                ast_scopes = find_ast_scopes(current_content) if is_python else []
                target_scope = None

                if is_python and (target_symbol or target_class or target_method):
                    target_scope, candidates = resolve_target_scope(
                        ast_scopes,
                        target_symbol=target_symbol,
                        target_class=target_class,
                        target_method=target_method,
                    )
                    if target_scope is None:
                        if len(candidates) > 1:
                            return _finish(
                                PatchBuilderResult(
                                    success=False,
                                    error_message=f"Target symbol '{target_symbol or target_method}' is ambiguous across multiple scopes {candidates} in '{rel_path}'.",
                                    error_category="ANCHOR_AMBIGUOUS_MULTI_CLASS",
                                    target_files=list(mods_by_file.keys()),
                                    generation_latency=time.time() - start_time,
                                )
                            )
                        else:
                            return _finish(
                                PatchBuilderResult(
                                    success=False,
                                    error_message=f"Target symbol '{target_symbol or target_class or target_method}' not found in '{rel_path}'.",
                                    error_category="ANCHOR_NOT_IN_TARGET_SCOPE",
                                    target_files=list(mods_by_file.keys()),
                                    generation_latency=time.time() - start_time,
                                )
                            )

                if target_scope is not None:
                    # Stale fingerprint check on resolved scope
                    if source_fingerprint:
                        valid_fps = [
                            target_scope.fingerprint,
                            compute_source_fingerprint(target_scope.full_text),
                            compute_source_fingerprint(anchor),
                        ]
                        if surrounding_context:
                            valid_fps.append(compute_source_fingerprint(surrounding_context))
                        if source_fingerprint not in valid_fps:
                            return _finish(
                                PatchBuilderResult(
                                    success=False,
                                    error_message=f"Stale anchor detected in '{rel_path}': source_fingerprint '{source_fingerprint}' does not match target block '{target_scope.qualified_name}'.",
                                    error_category="STALE_ANCHOR",
                                    target_files=list(mods_by_file.keys()),
                                    generation_latency=time.time() - start_time,
                                )
                            )

                    # Scoped anchor search
                    scoped_count, resolved_anc, scoped_indices = find_anchor_occurrences(
                        target_scope.full_text, anchor, is_python=True
                    )
                    if scoped_count == 0:
                        global_count, _, _ = find_anchor_occurrences(current_content, anchor, is_python=is_python)
                        if global_count == 0:
                            actual_returns = [
                                line.strip()
                                for line in target_scope.full_text.splitlines()
                                if line.strip().startswith("return ")
                            ]
                            candidate_msg = (
                                f" (candidate return statement(s) in scope: {actual_returns[:3]})"
                                if actual_returns and anchor.strip().startswith("return")
                                else ""
                            )
                            return _finish(
                                PatchBuilderResult(
                                    success=False,
                                    error_message=f"Anchor not found in '{rel_path}': {anchor[:100]}{candidate_msg}",
                                    error_category="ANCHOR_NOT_FOUND",
                                    target_files=list(mods_by_file.keys()),
                                    generation_latency=time.time() - start_time,
                                )
                            )
                        return _finish(
                            PatchBuilderResult(
                                success=False,
                                error_message=f"Anchor not found in target scope '{target_scope.qualified_name}' in '{rel_path}': {anchor[:100]}",
                                error_category="ANCHOR_NOT_IN_TARGET_SCOPE",
                                target_files=list(mods_by_file.keys()),
                                generation_latency=time.time() - start_time,
                            )
                        )
                    elif scoped_count > 1:
                        return _finish(
                            PatchBuilderResult(
                                success=False,
                                error_message=f"Anchor ambiguous within target scope '{target_scope.qualified_name}' in '{rel_path}' ({scoped_count} matches).",
                                error_category="ANCHOR_AMBIGUOUS_IN_SCOPE",
                                target_files=list(mods_by_file.keys()),
                                generation_latency=time.time() - start_time,
                            )
                        )

                    anchor = resolved_anc
                    idx = target_scope.start_idx + scoped_indices[0]
                else:
                    # Global anchor search
                    anchor_count, resolved_anc, indices = find_anchor_occurrences(
                        current_content, anchor, is_python=is_python
                    )

                    if anchor_count == 0:
                        actual_returns = [
                            line.strip()
                            for line in current_content.splitlines()
                            if line.strip().startswith("return ")
                        ]
                        candidate_msg = (
                            f" (candidate return statement(s) in file: {actual_returns[:3]})"
                            if actual_returns and anchor.strip().startswith("return")
                            else ""
                        )
                        return _finish(
                            PatchBuilderResult(
                                success=False,
                                error_message=f"Anchor not found in '{rel_path}': {anchor[:100]}{candidate_msg}",
                                error_category="ANCHOR_NOT_FOUND",
                                target_files=list(mods_by_file.keys()),
                                generation_latency=time.time() - start_time,
                            )
                        )

                    # Filter by line range if provided
                    if anchor_count > 1 and line_range and len(line_range) == 2:
                        s_line, e_line = line_range
                        filtered = [i for i in indices if s_line <= (current_content.count("\n", 0, i) + 1) <= e_line]
                        if len(filtered) == 1:
                            indices = filtered
                            anchor_count = 1
                        elif len(filtered) > 1:
                            return _finish(
                                PatchBuilderResult(
                                    success=False,
                                    error_message=f"Anchor is ambiguous within line range {line_range} in '{rel_path}' ({len(filtered)} matches).",
                                    error_category="ANCHOR_AMBIGUOUS_IN_SCOPE",
                                    target_files=list(mods_by_file.keys()),
                                    generation_latency=time.time() - start_time,
                                )
                            )
                        else:
                            return _finish(
                                PatchBuilderResult(
                                    success=False,
                                    error_message=f"Anchor occurrences in '{rel_path}' fall outside specified line range {line_range}.",
                                    error_category="OUT_OF_RANGE_ANCHOR",
                                    target_files=list(mods_by_file.keys()),
                                    generation_latency=time.time() - start_time,
                                )
                            )

                    if anchor_count > 1:
                        if is_python and ast_scopes:
                            candidate_classes = set()
                            for ind in indices:
                                for s in ast_scopes:
                                    if (s.node_type == "ClassDef" or s.class_name) and (s.start_idx <= ind < s.end_idx):
                                        candidate_classes.add(s.class_name or s.name)
                            if len(candidate_classes) > 1:
                                return _finish(
                                    PatchBuilderResult(
                                        success=False,
                                        error_message=f"Anchor is ambiguous across multiple classes {sorted(list(candidate_classes))} in '{rel_path}'. Please specify 'target_symbol' (e.g. '{sorted(list(candidate_classes))[0]}.<method>') or enclosing class context to disambiguate.",
                                        error_category="ANCHOR_AMBIGUOUS_MULTI_CLASS",
                                        target_files=list(mods_by_file.keys()),
                                        generation_latency=time.time() - start_time,
                                    )
                                )

                        return _finish(
                            PatchBuilderResult(
                                success=False,
                                error_message=f"Anchor ambiguous in '{rel_path}' ({anchor_count} matches).",
                                error_category="ANCHOR_AMBIGUOUS",
                                target_files=list(mods_by_file.keys()),
                                generation_latency=time.time() - start_time,
                            )
                        )

                    anchor = resolved_anc
                    idx = indices[0]

                    # Check line range if provided on unique match
                    if line_range and len(line_range) == 2:
                        line_no = current_content.count("\n", 0, idx) + 1
                        if not (line_range[0] <= line_no <= line_range[1]):
                            return _finish(
                                PatchBuilderResult(
                                    success=False,
                                    error_message=f"Anchor at line {line_no} in '{rel_path}' is outside specified line range {line_range}.",
                                    error_category="OUT_OF_RANGE_ANCHOR",
                                    target_files=list(mods_by_file.keys()),
                                    generation_latency=time.time() - start_time,
                                )
                            )

                    # Stale fingerprint check for unscoped modification
                    if source_fingerprint:
                        valid_fps = [compute_source_fingerprint(anchor)]
                        if surrounding_context:
                            valid_fps.append(compute_source_fingerprint(surrounding_context))
                        if source_fingerprint not in valid_fps:
                            return _finish(
                                PatchBuilderResult(
                                    success=False,
                                    error_message=f"Stale anchor detected in '{rel_path}': source_fingerprint '{source_fingerprint}' does not match anchor block.",
                                    error_category="STALE_ANCHOR",
                                    target_files=list(mods_by_file.keys()),
                                    generation_latency=time.time() - start_time,
                                )
                            )

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
                        if current_content[insert_pos : insert_pos + 2] == "\r\n":
                            insert_pos += 2
                        elif current_content[insert_pos : insert_pos + 1] == "\n":
                            insert_pos += 1
                    if is_pure_prefix:
                        norm_code = self.normalize_code_indentation(code, anchor, anchor_indent, "insert_after")
                    else:
                        norm_code = code if code.endswith("\n") else (code + "\n")
                    current_content = current_content[:insert_pos] + norm_code + current_content[insert_pos:]

                elif op == "replace":
                    anchor_end = idx + len(anchor)
                    if not anchor.endswith("\n"):
                        if current_content[anchor_end : anchor_end + 2] == "\r\n":
                            anchor_end += 2
                        elif current_content[anchor_end : anchor_end + 1] == "\n":
                            anchor_end += 1
                    if is_pure_prefix:
                        norm_code = self.normalize_code_indentation(code, anchor, anchor_indent, "replace")
                        current_content = current_content[:line_start] + norm_code + current_content[anchor_end:]
                    else:
                        norm_code = code.rstrip("\r\n")
                        current_content = current_content[:idx] + norm_code + current_content[idx + len(anchor) :]

                elif op == "delete":
                    end_pos = idx + len(anchor)
                    if not anchor.endswith("\n"):
                        if current_content[end_pos : end_pos + 2] == "\r\n":
                            end_pos += 2
                        elif current_content[end_pos : end_pos + 1] == "\n":
                            end_pos += 1
                    current_content = current_content[:idx] + current_content[end_pos:]

                applied_records.append({
                    "path": rel_path,
                    "operation": op,
                    "target_symbol": target_symbol,
                    "target_class": target_class,
                    "reason": getattr(mod, "reason", ""),
                })

            if rel_path.endswith(".py"):
                try:
                    ast.parse(current_content)
                except (SyntaxError, IndentationError) as syn_err:
                    err_cat = "SYNTAX_ERROR_INDENTATION" if isinstance(syn_err, IndentationError) else "SYNTAX_ERROR"
                    return _finish(
                        PatchBuilderResult(
                            success=False,
                            error_message=f"Patched file '{rel_path}' failed Python AST syntax verification: {syn_err}",
                            error_category=err_cat,
                            target_files=list(mods_by_file.keys()),
                            generation_latency=time.time() - start_time,
                        )
                    )

                try:
                    compile(current_content, rel_path, "exec")
                except SyntaxError as comp_err:
                    if isinstance(comp_err, IndentationError):
                        err_cat = "SYNTAX_ERROR_INDENTATION"
                    elif "return" in str(comp_err).lower():
                        err_cat = "INVALID_SCOPE"
                    else:
                        err_cat = "SYNTAX_ERROR"
                    return _finish(
                        PatchBuilderResult(
                            success=False,
                            error_message=f"Patched file '{rel_path}' failed Python bytecode compilation: {comp_err}",
                            error_category=err_cat,
                            target_files=list(mods_by_file.keys()),
                            generation_latency=time.time() - start_time,
                        )
                    )

                scope_err = self.validate_ast_scopes(current_content, rel_path)
                if scope_err:
                    return _finish(
                        PatchBuilderResult(
                            success=False,
                            error_message=f"Patched file '{rel_path}' failed structural scope verification: {scope_err}",
                            error_category="INVALID_SCOPE",
                            target_files=list(mods_by_file.keys()),
                            generation_latency=time.time() - start_time,
                        )
                    )

                undef_err = self.validate_variable_definitions(current_content, original_content, rel_path)
                if undef_err:
                    return _finish(
                        PatchBuilderResult(
                            success=False,
                            error_message=f"Patched file '{rel_path}' failed variable definition verification: {undef_err}",
                            error_category="UNDEFINED_VARIABLE",
                            target_files=list(mods_by_file.keys()),
                            generation_latency=time.time() - start_time,
                        )
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
            return _finish(
                PatchBuilderResult(
                    success=False,
                    error_message="Modifications resulted in an empty diff (no changes made).",
                    error_category="EMPTY_DIFF",
                    generation_latency=time.time() - start_time,
                )
            )

        full_patch = "".join(diff_chunks)
        val_res = self.patch_manager.validate_patch(full_patch)
        if not val_res.is_valid:
            return _finish(
                PatchBuilderResult(
                    success=False,
                    error_message=f"Generated patch failed validation: {val_res.error_message}",
                    error_category="INVALID_DIFF_STRUCTURE",
                    target_files=list(mods_by_file.keys()),
                    generation_latency=time.time() - start_time,
                )
            )

        # Source revision verification: verify patch applies cleanly against base_path git workspace
        git_dir = base_path / ".git"
        if git_dir.exists():
            try:
                proc = subprocess.run(
                    ["git", "apply", "--check", "-"],
                    input=full_patch,
                    cwd=str(base_path),
                    capture_output=True,
                    text=True,
                )
                if proc.returncode != 0:
                    return _finish(
                        PatchBuilderResult(
                            success=False,
                            error_message=f"Generated patch failed git apply --check against base revision: {proc.stderr.strip()}",
                            error_category="PATCH_REVISION_MISMATCH",
                            target_files=list(mods_by_file.keys()),
                            generation_latency=time.time() - start_time,
                        )
                    )
            except Exception:
                pass

        return _finish(
            PatchBuilderResult(
                success=True,
                unified_diff=full_patch,
                applied_modifications=applied_records,
                anchor_found=True,
                anchor_unique=True,
                target_files=list(mods_by_file.keys()),
                generation_latency=time.time() - start_time,
            )
        )