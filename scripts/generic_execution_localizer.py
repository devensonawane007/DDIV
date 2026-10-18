"""Generic Execution-Path Localizer for DDIV v2.2.

Analyzes Python source files via AST and call-graph / delegation tracing
to identify the controlling execution path for an issue without task-specific hardcoding.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


class MethodRole(str, Enum):
    """Generic semantic role of a function or method."""
    CONFIGURATION_SETUP = "CONFIGURATION_SETUP"
    ORCHESTRATOR_ENTRY = "ORCHESTRATOR_ENTRY"
    DELEGATOR_FORWARDER = "DELEGATOR_FORWARDER"
    BEHAVIOR_CONTROLLER = "BEHAVIOR_CONTROLLER"
    OUTPUT_GENERATOR = "OUTPUT_GENERATOR"
    UTILITY_STANDARD = "UTILITY_STANDARD"


@dataclass
class SymbolNode:
    """Represents a function, method, or class discovered in the AST."""
    name: str
    kind: str  # "class", "method", "function"
    class_name: Optional[str] = None
    file_path: str = ""
    start_line: int = 1
    end_line: int = 1
    parameters: List[str] = field(default_factory=list)
    attributes_accessed: Set[str] = field(default_factory=set)
    attributes_assigned: Set[str] = field(default_factory=set)
    calls: Set[str] = field(default_factory=set)
    has_conditionals: bool = False
    has_loops: bool = False
    has_returns: bool = False
    line_count: int = 1
    bases: List[str] = field(default_factory=list)
    role: MethodRole = MethodRole.UTILITY_STANDARD
    is_shared_convergence_point: bool = False
    entry_points_reaching: Set[str] = field(default_factory=set)
    call_keywords: Set[str] = field(default_factory=set)
    string_constants: Set[str] = field(default_factory=set)

    @property
    def full_name(self) -> str:
        return f"{self.class_name}.{self.name}" if self.class_name else self.name


@dataclass
class FileAnalysis:
    """AST analysis of a single Python source file."""
    file_path: str
    symbols: Dict[str, SymbolNode] = field(default_factory=dict)
    classes: Dict[str, SymbolNode] = field(default_factory=dict)
    call_graph: Dict[str, Set[str]] = field(default_factory=dict)  # caller -> set of callees
    reverse_call_graph: Dict[str, Set[str]] = field(default_factory=dict)  # callee -> set of callers
    inheritance: Dict[str, List[str]] = field(default_factory=dict)  # class -> list of base class names


@dataclass
class LocalizationDecision:
    """Structured decision produced by GenericExecutionLocalizer."""
    target_file: str
    primary_symbol: str
    controlling_symbols: List[str] = field(default_factory=list)
    enriched_target_symbols: List[str] = field(default_factory=list)
    status: str = "INSUFFICIENT_EVIDENCE"  # "RESOLVED", "AMBIGUOUS", "INSUFFICIENT_EVIDENCE"
    confidence: float = 0.0
    evidence_rationale: str = ""
    extracted_concepts: List[str] = field(default_factory=list)
    primary_role: str = ""
    symbol_roles: Dict[str, str] = field(default_factory=dict)
    shared_convergence_points: List[str] = field(default_factory=list)
    call_graph: Dict[str, List[str]] = field(default_factory=dict)
    reverse_call_graph: Dict[str, List[str]] = field(default_factory=dict)
    inheritance: Dict[str, List[str]] = field(default_factory=dict)
    known_symbols: List[str] = field(default_factory=list)
    known_attributes: List[str] = field(default_factory=list)
    symbol_locations: Dict[str, Dict[str, int]] = field(default_factory=dict)
    graph_coverage_complete: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_file": self.target_file,
            "primary_symbol": self.primary_symbol,
            "primary_role": self.primary_role,
            "controlling_symbols": self.controlling_symbols,
            "enriched_target_symbols": self.enriched_target_symbols,
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "evidence_rationale": self.evidence_rationale,
            "extracted_concepts": self.extracted_concepts,
            "symbol_roles": self.symbol_roles,
            "shared_convergence_points": self.shared_convergence_points,
            "call_graph": self.call_graph,
            "reverse_call_graph": self.reverse_call_graph,
            "inheritance": self.inheritance,
            "known_symbols": self.known_symbols,
            "known_attributes": self.known_attributes,
            "symbol_locations": self.symbol_locations,
            "graph_coverage_complete": self.graph_coverage_complete,
        }


class GenericExecutionLocalizer:
    """Generic AST-based execution path and delegation analyzer."""

    STOPWORDS: Set[str] = {
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
        "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
        "by", "can", "cannot", "could", "current", "desired", "did", "do", "does", "doing", "down",
        "during", "each", "few", "for", "from", "further", "had", "has", "have", "having", "he",
        "her", "here", "hers", "herself", "him", "himself", "his", "how", "i", "if", "in", "into",
        "is", "it", "its", "itself", "just", "like", "many", "me", "more", "most", "my", "myself",
        "no", "nor", "not", "now", "of", "off", "on", "once", "only", "or", "other", "ought", "our",
        "ours", "ourselves", "out", "over", "own", "problem", "re", "same", "setting", "she", "should",
        "so", "solution", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
        "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until",
        "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom",
        "why", "with", "works", "would", "you", "your", "yours", "yourself", "yourselves",
        "reason", "remember", "coming", "added", "usual", "regressed", "since", "previous",
        "included", "removed", "skipped", "done", "make", "want", "see", "think", "know", "need", "used", "using"
    }

    INIT_DEFECT_KEYWORDS: Set[str] = {
        "init", "initialize", "initialization", "constructor", "creation", "instantiate",
        "instantiation", "default", "attributeerror", "has no attribute", "unbound",
        "missing argument", "required argument", "not set", "none type"
    }

    RUNTIME_CONTROL_KEYWORDS: Set[str] = {
        "disable", "disabled", "disables", "skip", "skips", "stop", "stops", "prevent",
        "prevents", "avoid", "avoids", "filter", "filters", "filtering", "treats",
        "raises", "crash", "infinite", "loop", "check", "checking", "false positive",
        "incorrect result", "bypass", "bypasses"
    }

    def __init__(self, min_confidence: float = 0.25):
        self.min_confidence = min_confidence

    def extract_concepts(self, problem_statement: str) -> List[str]:
        """Extract candidate configuration keys, option flags, and referenced identifiers."""
        if not problem_statement:
            return []

        concepts: Set[str] = set()

        # 1. Option flags: e.g. --min-similarity-lines or -d
        flags = re.findall(r"--([a-zA-Z0-9_-]+)", problem_statement)
        for flag in flags:
            snake = flag.replace("-", "_").lower()
            concepts.add(snake)
            parts = re.split(r"[-_]", flag)
            for p in parts:
                if len(p) >= 3 and p.lower() not in self.STOPWORDS:
                    concepts.add(p.lower())

        # 2. Backtick code identifiers: `foo_bar`, `SimilarChecker`
        ticks = re.findall(r"`([^`]+)`", problem_statement)
        for t in ticks:
            t_clean = t.strip()
            if " " not in t_clean and len(t_clean) >= 2:
                snake = t_clean.replace("-", "_").lower()
                concepts.add(snake)
                for part in re.split(r"[-_.]", t_clean):
                    if len(part) >= 3 and part.lower() not in self.STOPWORDS:
                        concepts.add(part.lower())

        # 3. Quoted identifiers
        quotes = re.findall(r"['\"]([a-zA-Z0-9_.-]+)['\"]", problem_statement)
        for q in quotes:
            if len(q) >= 2:
                snake = q.replace("-", "_").lower()
                concepts.add(snake)
                for part in re.split(r"[-_.]", q):
                    if len(part) >= 3 and part.lower() not in self.STOPWORDS:
                        concepts.add(part.lower())

        # 4. camelCase or snake_case identifiers
        snake_words = re.findall(r"\b[a-zA-Z]+_[a-zA-Z0-9_]+\b", problem_statement)
        for sw in snake_words:
            sw_lower = sw.lower()
            concepts.add(sw_lower)
            for part in sw.split("_"):
                if len(part) >= 3 and part.lower() not in self.STOPWORDS:
                    concepts.add(part.lower())

        # 5. General tokens (length >= 3, not stopwords)
        words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", problem_statement)
        for w in words:
            wl = w.lower()
            if wl not in self.STOPWORDS:
                concepts.add(wl)

        # 6. Critical numeric constants if explicitly mentioned with options (e.g. '0', 'zero')
        if re.search(r"\b(to\s+0|is\s+0|set\s+to\s+0|value\s+0)\b", problem_statement, re.IGNORECASE):
            concepts.add("0")
            concepts.add("zero")

        return sorted(concepts)

    def classify_method_role(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        attrs_assigned: Set[str],
        calls: Set[str],
        has_if: bool,
        has_loop: bool,
    ) -> MethodRole:
        """Classify the semantic role of a method based on AST structure."""
        name_lower = node.name.lower()

        # 1. Configuration / Setup: __init__, setup, configure, or sets attributes with no loops
        if name_lower in ("__init__", "__post_init__", "setup", "configure", "init") or name_lower.startswith("set_"):
            return MethodRole.CONFIGURATION_SETUP
        if attrs_assigned and not has_loop and not has_if and len(node.body) <= 5:
            return MethodRole.CONFIGURATION_SETUP

        # 2. Output generation: format, print, display, report, render, emit
        if any(name_lower.startswith(p) for p in ("display", "show", "print", "format", "render", "report", "dump", "write", "emit", "log")):
            return MethodRole.OUTPUT_GENERATOR

        # 3. Delegator / Forwarder: small body with single call/return
        if len(node.body) <= 2 and calls and not has_loop and not has_if:
            for stmt in node.body:
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
                    return MethodRole.DELEGATOR_FORWARDER

        # 4. Orchestrator / Entry point: run, close, process, execute, main, start, handle
        if any(name_lower.startswith(p) for p in ("run", "close", "process", "exec", "main", "start", "call", "handle", "dispatch")):
            if calls:
                return MethodRole.ORCHESTRATOR_ENTRY

        # 5. Behavior Controller: conditionals or loops controlling calculation
        if has_if or has_loop:
            return MethodRole.BEHAVIOR_CONTROLLER

        return MethodRole.UTILITY_STANDARD

    def analyze_file(self, file_path: Union[str, Path], content: Optional[str] = None) -> FileAnalysis:
        """Parse Python source into AST symbols, call graph, and inheritance trees."""
        f_path_str = str(file_path).replace("\\", "/")
        analysis = FileAnalysis(file_path=f_path_str)

        if content is None:
            p = Path(file_path)
            if not p.exists() or not p.is_file():
                return analysis
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return analysis

        try:
            tree = ast.parse(content)
        except Exception:
            return analysis

        # First pass: collect classes and functions
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                c_name = node.name
                bases = []
                for b in node.bases:
                    b_name = getattr(b, "id", None) or getattr(b, "attr", None)
                    if b_name:
                        bases.append(b_name)
                analysis.inheritance[c_name] = bases

                c_node = SymbolNode(
                    name=c_name,
                    kind="class",
                    file_path=f_path_str,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    bases=bases,
                    line_count=getattr(node, "end_lineno", node.lineno) - node.lineno + 1,
                    role=MethodRole.UTILITY_STANDARD,
                )
                analysis.classes[c_name] = c_node
                analysis.symbols[c_name] = c_node

                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_node = self._build_function_symbol(item, f_path_str, class_name=c_name)
                        analysis.symbols[m_node.full_name] = m_node

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_node = self._build_function_symbol(node, f_path_str, class_name=None)
                analysis.symbols[fn_node.name] = fn_node

        # Second pass: construct call graph
        for sym_name, sym in analysis.symbols.items():
            if sym.kind not in ("method", "function"):
                continue
            for called in sym.calls:
                # 1. Method-to-method calls within same class
                if sym.class_name:
                    sibling_name = f"{sym.class_name}.{called}"
                    if sibling_name in analysis.symbols:
                        analysis.call_graph.setdefault(sym.full_name, set()).add(sibling_name)
                        analysis.reverse_call_graph.setdefault(sibling_name, set()).add(sym.full_name)
                    # Base class methods
                    for base_c in analysis.inheritance.get(sym.class_name, []):
                        base_method = f"{base_c}.{called}"
                        if base_method in analysis.symbols:
                            analysis.call_graph.setdefault(sym.full_name, set()).add(base_method)
                            analysis.reverse_call_graph.setdefault(base_method, set()).add(sym.full_name)

                # 2. Standalone function or direct call
                if called in analysis.symbols:
                    analysis.call_graph.setdefault(sym.full_name, set()).add(called)
                    analysis.reverse_call_graph.setdefault(called, set()).add(sym.full_name)

                # 3. Cross-class method match: e.g. caller calls instance.run() where 'run' is a known method
                for other_sym_name, other_sym in analysis.symbols.items():
                    if other_sym.kind == "method" and other_sym.name == called:
                        analysis.call_graph.setdefault(sym.full_name, set()).add(other_sym_name)
                        analysis.reverse_call_graph.setdefault(other_sym_name, set()).add(sym.full_name)

        return analysis

    def _build_function_symbol(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        file_path: str,
        class_name: Optional[str],
    ) -> SymbolNode:
        """Extract symbol details and semantic role from an AST function/method node."""
        params = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
        attrs_read: Set[str] = set()
        attrs_written: Set[str] = set()
        calls: Set[str] = set()
        has_if = False
        has_loop = False
        has_returns = False

        call_kws: Set[str] = set()
        str_consts: Set[str] = set()

        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute):
                if isinstance(sub.ctx, ast.Store):
                    attrs_assigned = attrs_written
                else:
                    attrs_assigned = attrs_read
                attrs_assigned.add(sub.attr)
            elif isinstance(sub, ast.Call):
                if isinstance(sub.func, ast.Name):
                    calls.add(sub.func.id)
                elif isinstance(sub.func, ast.Attribute):
                    calls.add(sub.func.attr)
                for kw in sub.keywords:
                    if kw.arg:
                        call_kws.add(kw.arg)
            elif isinstance(sub, ast.Constant):
                if isinstance(sub.value, str) and len(sub.value.strip()) >= 2:
                    str_consts.add(sub.value.strip().lower())
            elif isinstance(sub, ast.If):
                has_if = True
            elif isinstance(sub, (ast.For, ast.While)):
                has_loop = True
            elif isinstance(sub, ast.Return):
                has_returns = True

        role = self.classify_method_role(
            node=node,
            attrs_assigned=attrs_written,
            calls=calls,
            has_if=has_if,
            has_loop=has_loop,
        )

        return SymbolNode(
            name=node.name,
            kind="method" if class_name else "function",
            class_name=class_name,
            file_path=file_path,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            parameters=params,
            attributes_accessed=attrs_read,
            attributes_assigned=attrs_written,
            calls=calls,
            has_conditionals=has_if,
            has_loops=has_loop,
            has_returns=has_returns,
            line_count=getattr(node, "end_lineno", node.lineno) - node.lineno + 1,
            role=role,
            call_keywords=call_kws,
            string_constants=str_consts,
        )

    def score_symbol(
        self,
        sym: SymbolNode,
        concepts: List[str],
        analysis: FileAnalysis,
        is_init_defect: bool = False,
        is_runtime_control_defect: bool = False,
    ) -> Tuple[float, List[str]]:
        """Compute relevance score and matched rationale for a symbol node, taking method roles into account."""
        score = 0.0
        matches: List[str] = []
        c_set = set(concepts)

        # 1. Exact attribute matches (strongest signal for configuration or state)
        all_attrs = sym.attributes_accessed | sym.attributes_assigned
        for attr in all_attrs:
            attr_lower = attr.lower()
            if attr_lower in c_set:
                score += 3.5
                matches.append(f"exact_attr:{attr}")
            else:
                for c in concepts:
                    if len(c) >= 3 and (c in attr_lower or attr_lower in c):
                        score += 1.5
                        matches.append(f"partial_attr:{attr}~{c}")
                        break

        # 2. Parameter matches
        for p in sym.parameters:
            p_lower = p.lower()
            if p_lower in c_set:
                score += 3.0
                matches.append(f"exact_param:{p}")
            else:
                for c in concepts:
                    if len(c) >= 3 and (c in p_lower or p_lower in c):
                        score += 1.0
                        matches.append(f"partial_param:{p}~{c}")
                        break

        # 3. Symbol name match
        sym_name_lower = sym.name.lower()
        if sym_name_lower in c_set:
            score += 3.0
            matches.append(f"exact_name:{sym.name}")
        else:
            for c in concepts:
                if len(c) >= 4 and c in sym_name_lower:
                    score += 1.5
                    matches.append(f"partial_name:{sym.name}~{c}")
                    break

        # 4. Class name match (if method)
        if sym.class_name:
            c_name_lower = sym.class_name.lower()
            if c_name_lower in c_set:
                score += 1.5
                matches.append(f"class_match:{sym.class_name}")
            else:
                for c in concepts:
                    if len(c) >= 4 and c in c_name_lower:
                        score += 0.8
                        matches.append(f"partial_class:{sym.class_name}~{c}")
                        break

        # 4b. Call keyword arguments (e.g. follow_symlinks=False, timeout=10)
        for kw in sym.call_keywords:
            kw_lower = kw.lower()
            if kw_lower in c_set:
                kw_weight = 20.0 if "_" in kw_lower else 6.0
                score += kw_weight
                matches.append(f"exact_call_kw:{kw}")
            else:
                for c in concepts:
                    if len(c) >= 4 and (c in kw_lower or kw_lower in c):
                        score += 2.5
                        matches.append(f"partial_call_kw:{kw}~{c}")
                        break

        # 4c. String constants (e.g. option names, flags)
        for sc in sym.string_constants:
            if sc in c_set:
                score += 2.5
                matches.append(f"str_const:{sc[:20]}")
            else:
                for c in concepts:
                    if len(c) >= 4 and c in sc:
                        score += 1.0
                        matches.append(f"partial_str:{c}")
                        break

        # 5. Method Role Weighting based on issue intent (evidence-driven, not hardcoded)
        if score > 0:
            if is_init_defect:
                if sym.role == MethodRole.CONFIGURATION_SETUP:
                    score += 4.5
                    matches.append("role_match:init_defect_setup")
                    if sym.attributes_assigned:
                        score += 1.5
                        matches.append("init_attributes_assigned")
                elif sym.role in (MethodRole.BEHAVIOR_CONTROLLER, MethodRole.ORCHESTRATOR_ENTRY):
                    score *= 0.65
                    matches.append("role_adj:runtime_in_init_issue")
            elif is_runtime_control_defect:
                if sym.role == MethodRole.BEHAVIOR_CONTROLLER:
                    score += 3.5
                    matches.append("role_match:runtime_controller")
                elif sym.role == MethodRole.ORCHESTRATOR_ENTRY:
                    score += 2.5
                    matches.append("role_match:orchestrator_entry")
                elif sym.role == MethodRole.CONFIGURATION_SETUP:
                    # Setup methods do not directly control runtime flow; retain state score but lower target priority
                    score *= 0.6
                    matches.append("role_adj:setup_in_runtime_issue")

            # Control logic weighting
            if not is_init_defect:
                if sym.has_conditionals:
                    score += 1.0
                if sym.has_loops:
                    score += 1.0

        return score, matches

    def _get_transitive_callees(self, sym_name: str, analysis: FileAnalysis, max_depth: int = 4) -> Dict[str, int]:
        """Find all transitive callees reachable from sym_name along with their minimum depth."""
        visited: Dict[str, int] = {}
        frontier = {sym_name}
        for d in range(1, max_depth + 1):
            next_frontier = set()
            for s in frontier:
                for callee in analysis.call_graph.get(s, set()):
                    if callee not in visited and callee != sym_name:
                        visited[callee] = d
                        next_frontier.add(callee)
            frontier = next_frontier
        return visited

    def trace_execution_flow(
        self,
        scored_symbols: Dict[str, Tuple[float, List[str]]],
        analysis: FileAnalysis,
        is_init_defect: bool = False,
    ) -> List[Tuple[str, float, str, List[str]]]:
        """Propagate scores along the call graph, identify shared convergence points, and rank candidates."""
        results: List[Tuple[str, float, str, List[str]]] = []

        # Identify all entry points (callers with no internal callers, or public orchestrators/forwarders)
        entry_points = [
            s_name for s_name, sym in analysis.symbols.items()
            if sym.kind in ("method", "function")
            and sym.name != "__init__"
            and analysis.call_graph.get(s_name)
            and (
                sym.role in (MethodRole.ORCHESTRATOR_ENTRY, MethodRole.DELEGATOR_FORWARDER)
                or not analysis.reverse_call_graph.get(s_name)
                or not sym.name.startswith("_")
                or any(sym.name.lower().startswith(p) for p in ("run", "close", "execute", "exec", "main", "start", "handle", "dispatch", "process"))
            )
        ]

        # Map which entry points reach which downstream symbols
        entry_reachability: Dict[str, Set[str]] = {}
        for ep in entry_points:
            callees = self._get_transitive_callees(ep, analysis, max_depth=4)
            for callee in callees:
                entry_reachability.setdefault(callee, set()).add(ep)

        for sym_name, (base_score, matches) in scored_symbols.items():
            sym = analysis.symbols.get(sym_name)
            if not sym or sym.kind == "class":
                continue

            propagated_score = base_score
            role = sym.role.value
            trace: List[str] = list(matches)

            # Transitive callees propagation
            trans_callees = self._get_transitive_callees(sym_name, analysis, max_depth=4)
            callee_bonus = 0.0
            for callee, depth in trans_callees.items():
                callee_score, _ = scored_symbols.get(callee, (0.0, []))
                if callee_score > 3.0:
                    weight = max(0.5, 3.0 / depth)
                    callee_bonus += weight
                    trace.append(f"reaches_controlling:{callee}(d={depth})")
            max_callee_bonus = min(base_score * 2.5, 12.0) if base_score > 0 else 3.0
            propagated_score += min(callee_bonus, max_callee_bonus)

            # Check if this method is called by an entry point
            callers = analysis.reverse_call_graph.get(sym_name, set())
            for caller in callers:
                caller_sym = analysis.symbols.get(caller)
                if caller_sym and caller_sym.role == MethodRole.ORCHESTRATOR_ENTRY:
                    propagated_score += 2.0
                    trace.append(f"called_by_entry:{caller}")

            # Orchestrator entry point bonus (suppress during initialization defects)
            if sym.role == MethodRole.ORCHESTRATOR_ENTRY and not is_init_defect:
                if trans_callees:
                    propagated_score += 3.0
                    trace.append("is_orchestrator_entry")

            # Shared Downstream Convergence: reachable from multiple distinct entry points
            reaching_entries = entry_reachability.get(sym_name, set())
            sym.entry_points_reaching = reaching_entries
            if len(reaching_entries) >= 2:
                sym.is_shared_convergence_point = True
                propagated_score += 3.5
                trace.append(f"shared_convergence_point(entries={sorted(reaching_entries)})")

            # Base class delegation
            if sym.class_name:
                bases = analysis.inheritance.get(sym.class_name, [])
                for b in bases:
                    if b in analysis.classes:
                        trace.append(f"inherits_from:{b}")

            results.append((sym_name, propagated_score, role, trace))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def localize(
        self,
        problem_statement: str,
        workspace_path: Union[str, Path],
        located_files: List[str],
        candidate_symbols: Optional[List[str]] = None,
    ) -> LocalizationDecision:
        """Perform generic execution path localization across located files."""
        concepts = self.extract_concepts(problem_statement)
        ws_p = Path(workspace_path)

        if not located_files:
            return LocalizationDecision(
                target_file="",
                primary_symbol="",
                status="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                evidence_rationale="No located files provided.",
                extracted_concepts=concepts,
            )

        prob_lower = problem_statement.lower()
        is_init_defect = any(k in prob_lower for k in self.INIT_DEFECT_KEYWORDS)
        is_runtime_control = any(k in prob_lower for k in self.RUNTIME_CONTROL_KEYWORDS)

        all_file_candidates: List[Tuple[str, str, float, str, List[str], FileAnalysis]] = []

        # Prioritize implementation files over test suites for defect localization
        impl_files = [
            f for f in located_files
            if f.endswith(".py")
            and not (f.startswith("test") or "/test" in f or f.endswith("_test.py"))
        ]
        files_to_analyze = impl_files if impl_files else [f for f in located_files if f.endswith(".py")]

        all_analyses: Dict[str, FileAnalysis] = {}
        for rel_file in files_to_analyze:
            full_file = ws_p / rel_file
            if full_file.exists():
                an = self.analyze_file(full_file)
                if an.symbols:
                    all_analyses[rel_file] = an

        # Cross-file call linking: if a symbol in file A calls a function in file B
        for rel_file, analysis in all_analyses.items():
            for s_name, sym in analysis.symbols.items():
                for called in sym.calls:
                    for other_file, other_analysis in all_analyses.items():
                        if other_file != rel_file and called in other_analysis.symbols:
                            analysis.call_graph.setdefault(sym.full_name, set()).add(called)
                            other_analysis.reverse_call_graph.setdefault(called, set()).add(sym.full_name)

        for rel_file, analysis in all_analyses.items():
            # Initial scoring
            scored: Dict[str, Tuple[float, List[str]]] = {}
            for s_name, sym in analysis.symbols.items():
                s_score, s_matches = self.score_symbol(
                    sym,
                    concepts,
                    analysis,
                    is_init_defect=is_init_defect,
                    is_runtime_control_defect=is_runtime_control,
                )
                if candidate_symbols:
                    clean_candidates = {c.split(".")[-1].strip() for c in candidate_symbols}
                    if sym.name in clean_candidates or (sym.class_name and sym.class_name in clean_candidates):
                        s_score += 1.5
                        s_matches.append("in_initial_candidates")
                if s_score > 0:
                    scored[s_name] = (s_score, s_matches)

            # Trace execution flow with transitive call propagation and convergence detection
            flow_results = self.trace_execution_flow(scored, analysis, is_init_defect=is_init_defect)
            for sym_name, score, role, trace in flow_results:
                if score >= 2.0:
                    all_file_candidates.append((rel_file, sym_name, score, role, trace, analysis))

        if not all_file_candidates:
            return LocalizationDecision(
                target_file=located_files[0],
                primary_symbol=candidate_symbols[0] if candidate_symbols else "",
                status="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                evidence_rationale="No symbols met the evidence threshold for the extracted concepts.",
                extracted_concepts=concepts,
            )

        # Sort all candidates across files
        all_file_candidates.sort(key=lambda x: x[2], reverse=True)

        top_file, top_sym, top_score, top_role, top_trace, top_analysis = all_file_candidates[0]

        # Check for ambiguity: if second candidate is close in score but in a completely different, unlinked class/file
        is_ambiguous = False
        if len(all_file_candidates) > 1:
            second_file, second_sym, second_score, _, _, second_analysis = all_file_candidates[1]
            if second_score > 0 and (top_score - second_score) / top_score < 0.10:
                if second_file != top_file:
                    is_ambiguous = True
                else:
                    top_node = top_analysis.symbols.get(top_sym)
                    sec_node = top_analysis.symbols.get(second_sym)
                    if top_node and sec_node and top_node.class_name != sec_node.class_name:
                        bases_top = set(top_analysis.inheritance.get(top_node.class_name or "", []))
                        bases_sec = set(top_analysis.inheritance.get(sec_node.class_name or "", []))
                        shared_base = bool(bases_top & bases_sec or sec_node.class_name in bases_top or top_node.class_name in bases_sec)
                        if not shared_base:
                            callees_top = self._get_transitive_callees(top_sym, top_analysis, max_depth=3)
                            callees_sec = self._get_transitive_callees(second_sym, top_analysis, max_depth=3)
                            connected = (
                                second_sym in callees_top
                                or top_sym in callees_sec
                                or any(c in callees_sec for c in callees_top)
                            )
                            if not connected:
                                is_ambiguous = True

        # Build enriched target symbols for context slicing across ALL candidate files:
        enriched: List[str] = []
        symbol_roles: Dict[str, str] = {}
        shared_convergence: List[str] = []

        # 1. Primary symbol first (highest priority)
        if top_sym not in enriched:
            enriched.append(top_sym)
        clean_top = top_sym.split(".")[-1]
        if clean_top not in enriched:
            enriched.append(clean_top)
        top_node = top_analysis.symbols.get(top_sym)
        if top_node and top_node.class_name and top_node.class_name not in enriched:
            enriched.append(top_node.class_name)

        # 2. Candidate symbols with exact concept matches across ANY file (placed at top priority!)
        for f, s, sc, r, tr, an in all_file_candidates:
            has_exact = any(m.startswith("exact_") for m in tr)
            if has_exact:
                if s not in enriched:
                    enriched.append(s)
                clean_s = s.split(".")[-1]
                if clean_s not in enriched:
                    enriched.append(clean_s)

        # 3. Top controlling symbols from top_analysis
        for f, s, sc, r, tr, an in all_file_candidates[:6]:
            s_node = an.symbols.get(s)
            if s_node and f == top_file:
                symbol_roles[s] = s_node.role.value
                if s_node.is_shared_convergence_point and s not in shared_convergence:
                    shared_convergence.append(s)
                if s not in enriched:
                    enriched.append(s)
                if s_node.name not in enriched:
                    enriched.append(s_node.name)
                if s_node.class_name and s_node.class_name not in enriched:
                    enriched.append(s_node.class_name)

        # 4. Top 2 symbols for each other located file
        file_top_symbols: Dict[str, List[str]] = {}
        for f, s, sc, r, tr, an in all_file_candidates:
            if f not in file_top_symbols:
                file_top_symbols[f] = []
            if len(file_top_symbols[f]) < 2 and s not in file_top_symbols[f]:
                file_top_symbols[f].append(s)

        for f, syms in file_top_symbols.items():
            for s in syms:
                if s not in enriched:
                    enriched.append(s)
                clean_s = s.split(".")[-1]
                if clean_s not in enriched:
                    enriched.append(clean_s)

        # Ensure any identified shared convergence points in top_analysis are recorded
        for s_name, s_sym in top_analysis.symbols.items():
            if s_sym.is_shared_convergence_point and s_name not in shared_convergence:
                shared_convergence.append(s_name)

        top_node = top_analysis.symbols.get(top_sym)
        controlling: List[str] = [top_sym]
        for f, s, sc, r, tr, an in all_file_candidates[1:8]:
            if f == top_file:
                is_reaching_entry = bool(top_node and top_node.is_shared_convergence_point and s in top_node.entry_points_reaching)
                if (sc >= max(2.0, top_score * 0.20) or is_reaching_entry) and s not in controlling:
                    controlling.append(s)

        confidence = min(1.0, top_score / 25.0)

        rationale_lines = [
            f"Localized controlling execution path to file '{top_file}'.",
            f"Primary controlling symbol: '{top_sym}' (role: {top_role}, score: {top_score:.1f}).",
            f"Matched concepts: {concepts[:8]}",
            f"Evidence trace: {', '.join(top_trace[:5])}",
            f"Controlling symbols along execution path: {controlling[:5]}",
        ]
        if shared_convergence:
            rationale_lines.append(f"Shared downstream convergence points: {shared_convergence}")
        rationale = "\n".join(rationale_lines)

        status = "AMBIGUOUS" if is_ambiguous else ("RESOLVED" if confidence >= self.min_confidence else "INSUFFICIENT_EVIDENCE")

        # Collect AST structural graph context across all analyzed files
        cg: Dict[str, List[str]] = {}
        rcg: Dict[str, List[str]] = {}
        inh: Dict[str, List[str]] = {}
        ks: List[str] = []
        sl: Dict[str, Dict[str, Any]] = {}
        ka_set: Set[str] = set()

        for rel_file, an in all_analyses.items():
            for k, v in an.call_graph.items():
                cur = cg.setdefault(k, [])
                for x in sorted(list(v)):
                    if x not in cur:
                        cur.append(x)
            for k, v in an.reverse_call_graph.items():
                cur = rcg.setdefault(k, [])
                for x in sorted(list(v)):
                    if x not in cur:
                        cur.append(x)
            for k, v in an.inheritance.items():
                cur = inh.setdefault(k, [])
                for x in list(v):
                    if x not in cur:
                        cur.append(x)

            for sym_name, sym_node in an.symbols.items():
                if sym_name not in ks:
                    ks.append(sym_name)
                    sl[sym_name] = {"start_line": sym_node.start_line, "end_line": sym_node.end_line, "file": rel_file}
                if sym_node.name not in ks:
                    ks.append(sym_node.name)
                ka_set.update(sym_node.attributes_accessed)
                ka_set.update(sym_node.attributes_assigned)
        ka = sorted(list(ka_set))

        return LocalizationDecision(
            target_file=top_file,
            primary_symbol=top_sym,
            controlling_symbols=controlling,
            enriched_target_symbols=enriched,
            status=status,
            confidence=confidence,
            evidence_rationale=rationale,
            extracted_concepts=concepts,
            primary_role=top_role,
            symbol_roles=symbol_roles,
            shared_convergence_points=shared_convergence,
            call_graph=cg,
            reverse_call_graph=rcg,
            inheritance=inh,
            known_symbols=ks,
            known_attributes=ka,
            symbol_locations=sl,
            graph_coverage_complete=bool(top_analysis.symbols),
        )
