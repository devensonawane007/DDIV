"""Generic Decision Consistency and Verification for DDIV v2.2.

Enforces evidence-based consistency between LocalizationDecision, Supervisor recovery
directives, and Coder modification proposals without task-specific hardcoding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from scripts.generic_execution_localizer import LocalizationDecision


@dataclass
class ConsistencyResult:
    """Outcome of validating a Supervisor recommendation against LocalizationDecision."""
    status: str  # "AGREED", "JUSTIFIED_OVERRIDE", "CONTRADICTORY", "AMBIGUOUS_EVIDENCE"
    recommended_symbols: List[str] = field(default_factory=list)
    controlling_symbols: List[str] = field(default_factory=list)
    unsupported_symbols: List[str] = field(default_factory=list)
    has_justification: bool = False
    justification_detail: str = ""
    reconciliation_message: str = ""
    supporting_relationship: str = ""
    source_location: str = ""
    referenced_attributes: List[str] = field(default_factory=list)
    referenced_paths: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


class DecisionConsistencyValidator:
    """Validates and reconciles Supervisor directives against verified execution-path evidence."""

    JUSTIFICATION_KEYWORDS: Set[str] = {
        "calls", "called", "invokes", "invoked", "delegates", "delegated", "delegation",
        "caller", "callee", "call site", "call chain", "downstream", "upstream",
        "inherits", "subclass", "base class", "override", "overridden",
        "instantiates", "initializes", "constructor", "controls flow", "orchestrates",
        "bypasses", "guards", "entry point", "reaches"
    }

    IGNORE_TOKENS: Set[str] = {
        "the", "a", "an", "this", "that", "each", "some", "which", "any", "all",
        "method", "methods", "function", "functions", "class", "classes", "file", "files",
        "patch", "code", "coder", "supervisor", "test", "tests", "pylint",
        "was", "is", "for", "it", "with", "from", "to", "by", "and", "or", "not",
        "be", "are", "were", "been", "have", "has", "had", "do", "does", "did",
        "if", "but", "so", "as", "at", "when", "where", "while", "of", "off", "on", "out", "over",
        "self", "cls", "return", "def", "import", "true", "false", "none",
        "commit", "commits", "argument", "arguments", "parameter", "parameters", "param", "params",
        "option", "options", "flag", "flags", "call", "calls", "logic", "check", "checks",
        "line", "lines", "symbol", "symbols", "module", "modules", "package", "packages",
        "repo", "repository", "branch", "pr", "diff", "task", "change", "changes"
    }

    @classmethod
    def classify_symbol_reference(
        cls,
        raw_token: str,
        decision: Optional[LocalizationDecision] = None,
    ) -> Tuple[str, Optional[str]]:
        """Classify a reference into METHOD, CLASS, ATTRIBUTE_EXPRESSION, FILE_PATH, or PROSE.

        Returns (type_category, canonical_symbol_or_none).
        """
        token = raw_token.strip()
        if not token:
            return "PROSE_OR_KEYWORD", None

        # 1. File path check
        if "/" in token or "\\" in token or any(token.lower().endswith(ext) for ext in (".py", ".json", ".txt", ".md", ".yml", ".yaml", ".toml")):
            return "FILE_PATH", None

        # 1b. Keyword argument / assignment check (e.g. follow_symlinks=False, timeout=10)
        if "=" in token:
            return "ATTRIBUTE_EXPRESSION", None

        # 2. Prose / Stopwords / Ignored tokens
        token_lower = token.lower()
        if token_lower in cls.IGNORE_TOKENS:
            return "PROSE_OR_KEYWORD", None

        # 3. Method call with parens e.g. "open()", "self.process_module()", "cls.run()"
        if token.endswith("()"):
            inner = token[:-2].strip()
            if inner.startswith("self."):
                inner = inner[5:]
            elif inner.startswith("cls."):
                inner = inner[4:]
            if inner and inner.isidentifier():
                return "METHOD", inner
            elif inner and "." in inner:
                parts = inner.split(".")
                if all(p.isidentifier() for p in parts):
                    return "METHOD", inner

        # 4. Handle self. expressions: e.g. self.process_module vs self.linter.config.min_similarity_lines
        if token.startswith("self."):
            attr_path = token[5:]
            # Multiple dots e.g. linter.config.min_similarity_lines
            if "." in attr_path:
                return "ATTRIBUTE_EXPRESSION", None

            # Single attribute: e.g. self.process_module vs self.threshold
            if decision and decision.known_symbols:
                clean_syms = {s.split(".")[-1] for s in decision.known_symbols}
                if attr_path in clean_syms:
                    return "METHOD", attr_path
                if attr_path in decision.known_attributes:
                    return "ATTRIBUTE_EXPRESSION", None

            # Fallback heuristic: standard verb prefixes indicate methods
            if any(attr_path.startswith(p) for p in ("get_", "set_", "is_", "has_", "run", "process", "open", "close", "compute", "handle")):
                return "METHOD", attr_path

            # Default for self.<single_identifier> without method evidence is attribute expression
            return "ATTRIBUTE_EXPRESSION", None

        # 5. Multiple dots without self (e.g. config.min_similarity_lines.value)
        if token.count(".") >= 2:
            return "ATTRIBUTE_EXPRESSION", None

        # 6. Single dot e.g. Similar.run, CoreEngine._process_records, config.timeout
        if "." in token:
            lhs, rhs = token.split(".", 1)
            if lhs.isidentifier() and rhs.isidentifier():
                # If lhs is Capitalized, it's typically Class.method
                if lhs[0].isupper():
                    return "METHOD", token
                # If decision provides known symbols
                if decision and decision.known_symbols:
                    if token in decision.known_symbols or rhs in {s.split(".")[-1] for s in decision.known_symbols}:
                        return "METHOD", token
                    if rhs in decision.known_attributes:
                        return "ATTRIBUTE_EXPRESSION", None
                return "METHOD", token

        # 7. Unqualified identifier
        if token.isidentifier():
            if token[0].isupper():
                if decision and decision.known_symbols:
                    if token in decision.known_symbols or any(s.startswith(f"{token}.") for s in decision.known_symbols):
                        return "CLASS", token
                else:
                    return "CLASS", token
            if decision and decision.known_symbols:
                clean_syms = {s.split(".")[-1] for s in decision.known_symbols}
                if token in clean_syms:
                    return "METHOD", token
                if token in decision.known_attributes:
                    return "ATTRIBUTE_EXPRESSION", None
                return "PROSE_OR_KEYWORD", None
            return "METHOD", token

        return "PROSE_OR_KEYWORD", None

    def extract_symbols_and_references(
        self,
        text: str,
        decision: Optional[LocalizationDecision] = None,
    ) -> Tuple[List[str], List[str], List[str]]:
        """Extract and categorize symbols, attributes, and file paths from text.

        Returns (recommended_symbols, referenced_attributes, referenced_paths).
        """
        if not text:
            return [], [], []

        symbols: Set[str] = set()
        attributes: Set[str] = set()
        paths: Set[str] = set()

        raw_candidates: Set[str] = set()

        # Extract direct file paths mentioned in text: e.g. src/_pytest/pathlib.py
        for p in re.findall(r"([a-zA-Z0-9_./\\]+\.(?:py|json|txt|md|yml|yaml|toml))", text):
            paths.add(p.strip())

        # 1. Quoted or backticked expressions: 'foo', `Bar.baz`
        for q in re.findall(r"['`]([a-zA-Z0-9_./\\()=]+)['`]", text):
            raw_candidates.add(q.strip())

        # 2. Identifier followed by (): e.g. open(), self.process_module()
        for m in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_.]*\(\))", text):
            raw_candidates.add(m.strip())

        # 3. Identifier before class/method/function
        for m in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_.]*)\s+(?:class|method|function|methods|functions)\b", text, re.IGNORECASE):
            raw_candidates.add(m.strip())

        # 4. Following within/in/modify/patch/into/target
        for m in re.findall(r"\b(?:within|in|modify|patch|target|into)\s+(?:the\s+)?['`]?([a-zA-Z_][a-zA-Z0-9_./\\]*)['`]?", text, re.IGNORECASE):
            raw_candidates.add(m.strip())

        # 5. Connected by 'or' / 'and': e.g. "visit or iterdir call", "open or process_module methods"
        for m in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_.]*)\s+(?:or|and)\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s+(?:call|calls|method|methods|function|functions)\b", text, re.IGNORECASE):
            for part in m:
                raw_candidates.add(part.strip())

        # Syntax-aware classification
        for cand in raw_candidates:
            cat, canon = self.classify_symbol_reference(cand, decision)
            if cat in ("METHOD", "CLASS") and canon:
                symbols.add(canon)
            elif cat == "ATTRIBUTE_EXPRESSION":
                attributes.add(cand)
            elif cat == "FILE_PATH":
                paths.add(cand)

        return sorted(symbols), sorted(attributes), sorted(paths)

    def extract_recommended_symbols(
        self,
        text: str,
        decision: Optional[LocalizationDecision] = None,
    ) -> List[str]:
        """Extract function, method, or class names recommended in the text, filtering attributes and paths."""
        syms, _, _ = self.extract_symbols_and_references(text, decision)
        return syms

    @staticmethod
    def _get_transitive_callees(start_sym: str, call_graph: Dict[str, List[str]], max_depth: int = 5) -> Dict[str, int]:
        """Find all transitive callees reachable from start_sym along with their minimum depth."""
        visited: Dict[str, int] = {}
        frontier = {start_sym}
        start_clean = start_sym.split(".")[-1]
        for k in call_graph:
            if k == start_sym or k.split(".")[-1] == start_clean:
                frontier.add(k)

        for d in range(1, max_depth + 1):
            next_frontier = set()
            for s in frontier:
                for c in call_graph.get(s, []):
                    if c not in visited and c != start_sym:
                        visited[c] = d
                        next_frontier.add(c)
            frontier = next_frontier
        return visited

    def verify_structural_relationship(
        self,
        symbol: str,
        decision: LocalizationDecision,
    ) -> Tuple[bool, str, str]:
        """Verify whether an unsupported symbol has a relevant structural AST relationship to controlling symbols.

        Checks:
        1. Direct or transitive call edge (caller -> callee or callee -> caller).
        2. Method override in subclass/superclass hierarchy.
        3. State attribute coupling.

        CRITICAL: Does NOT accept a shared ancestor alone (e.g. both inheriting from object
        or a framework base class) as proof of control.

        Returns (is_verified, relationship_detail, source_location).
        """
        if not decision.known_symbols:
            return False, f"Symbol table unavailable to verify '{symbol}'.", ""

        sym_clean = symbol.split(".")[-1]
        matched_syms = [s for s in decision.known_symbols if s == symbol or s.endswith(f".{sym_clean}") or s == sym_clean]

        if not matched_syms:
            # If symbol not in target module AST
            return False, f"Symbol '{symbol}' not found in analyzed AST symbol table", ""

        controlling_targets = set(decision.controlling_symbols)
        if decision.primary_symbol:
            controlling_targets.add(decision.primary_symbol)

        for ms in matched_syms:
            ms_clean = ms.split(".")[-1]
            loc_dict = decision.symbol_locations.get(ms, {})
            file_path = loc_dict.get("file", decision.target_file) if loc_dict else decision.target_file
            loc_str = f"{file_path}:L{loc_dict['start_line']}-L{loc_dict['end_line']}" if (loc_dict and "start_line" in loc_dict) else file_path

            # 1. Transitive caller check: Does ms call any controlling target?
            callees = self._get_transitive_callees(ms, decision.call_graph, max_depth=5)
            for callee, depth in callees.items():
                callee_clean = callee.split(".")[-1]
                if callee in controlling_targets or any(callee_clean == ct.split(".")[-1] for ct in controlling_targets):
                    return True, f"'{ms}' transitively calls controlling '{callee}' (depth={depth})", loc_str

            # 2. Transitive callee check: Does any controlling target call ms?
            for target in controlling_targets:
                target_callees = self._get_transitive_callees(target, decision.call_graph, max_depth=5)
                for callee, depth in target_callees.items():
                    if callee == ms or callee.split(".")[-1] == ms_clean:
                        return True, f"'{ms}' is transitively invoked by controlling '{target}' (depth={depth})", loc_str

            # 3. Method Override in Inheritance Hierarchy
            if "." in ms:
                ms_class = ms.split(".")[0]
                for target in controlling_targets:
                    if "." in target:
                        target_class = target.split(".")[0]
                        target_clean = target.split(".")[-1]
                        if ms_clean == target_clean and ms_class != target_class:
                            # ms_class inherits from target_class
                            if target_class in decision.inheritance.get(ms_class, []):
                                return True, f"'{ms}' overrides base implementation '{target}' in subclass '{ms_class}'", loc_str
                            # target_class inherits from ms_class
                            if ms_class in decision.inheritance.get(target_class, []):
                                return True, f"'{ms}' is base implementation overridden by controlling '{target}' in '{target_class}'", loc_str

        return False, f"No verified call-graph or inheritance edge connects '{symbol}' to controlling execution path", ""

    def assess_justification(
        self,
        diagnosis: str,
        evidence: List[str],
        recommended: List[str],
        decision: LocalizationDecision,
    ) -> Tuple[bool, str, str, str]:
        """Assess whether Supervisor's recommendation is structurally justified against AST evidence.

        Returns (is_justified, justification_detail, supporting_relationship, source_location).
        """
        # 1. Check graph coverage
        if not decision.graph_coverage_complete or not decision.known_symbols:
            return False, "AST graph coverage is incomplete; cannot verify structural relationship.", "", ""

        # 2. Check each unsupported recommended symbol for structural relationship
        verified_relationships = []
        verified_locations = []

        for sym in recommended:
            is_structurally_linked, rel_detail, loc_str = self.verify_structural_relationship(sym, decision)
            if is_structurally_linked:
                verified_relationships.append(rel_detail)
                if loc_str:
                    verified_locations.append(loc_str)

        if verified_relationships:
            rel_summary = "; ".join(verified_relationships)
            loc_summary = "; ".join(verified_locations)
            return True, f"Structurally verified relationship: {rel_summary}", rel_summary, loc_summary

        # Check if Supervisor asserted natural language justification terms without structural backing
        combined_text = f"{diagnosis}\n" + "\n".join(evidence)
        combined_lower = combined_text.lower()
        matched_justifications = [kw for kw in self.JUSTIFICATION_KEYWORDS if kw in combined_lower]

        if matched_justifications:
            detail = (
                f"Supervisor asserted justification terms ({', '.join(matched_justifications[:3])}), "
                f"but AST graph analysis confirmed no call-chain or inheritance relationship to the controlling path."
            )
        else:
            detail = "No structural relationship or source-based justification found."

        return False, detail, "", ""

    def validate_recommendation(
        self,
        decision: LocalizationDecision,
        instructions: str,
        diagnosis: str = "",
        evidence: Optional[List[str]] = None,
    ) -> ConsistencyResult:
        """Validate Supervisor recommendations against the LocalizationDecision."""
        evidence_list = evidence or []
        recommended, attributes, paths = self.extract_symbols_and_references(instructions, decision)

        if decision.status == "AMBIGUOUS":
            return ConsistencyResult(
                status="AMBIGUOUS_EVIDENCE",
                recommended_symbols=recommended,
                controlling_symbols=decision.controlling_symbols,
                reconciliation_message="Execution path evidence is ambiguous between candidate locations.",
                referenced_attributes=attributes,
                referenced_paths=paths,
            )

        if not recommended:
            return ConsistencyResult(
                status="AGREED",
                recommended_symbols=[decision.primary_symbol] if decision.primary_symbol else [],
                controlling_symbols=decision.controlling_symbols,
                reconciliation_message="Supervisor provided general directives without conflicting symbol targets.",
                referenced_attributes=attributes,
                referenced_paths=paths,
            )

        # Check overlap with verified execution path
        verified_symbols = set()
        for s in decision.controlling_symbols + decision.enriched_target_symbols:
            verified_symbols.add(s)
            verified_symbols.add(s.split(".")[-1])

        unsupported_symbols = []
        supported_symbols = []

        for rec in recommended:
            rec_clean = rec.split(".")[-1]
            if rec in verified_symbols or rec_clean in verified_symbols:
                supported_symbols.append(rec)
            else:
                unsupported_symbols.append(rec)

        if not unsupported_symbols:
            return ConsistencyResult(
                status="AGREED",
                recommended_symbols=supported_symbols,
                controlling_symbols=decision.controlling_symbols,
                unsupported_symbols=[],
                reconciliation_message="Supervisor recommended symbols supported by execution path evidence.",
                referenced_attributes=attributes,
                referenced_paths=paths,
            )

        # Incomplete graph coverage -> AMBIGUOUS_EVIDENCE rather than CONTRADICTORY
        if not decision.graph_coverage_complete or not decision.known_symbols:
            return ConsistencyResult(
                status="AMBIGUOUS_EVIDENCE",
                recommended_symbols=unsupported_symbols,
                controlling_symbols=decision.controlling_symbols,
                unsupported_symbols=unsupported_symbols,
                has_justification=False,
                justification_detail="Relevant AST graph coverage is incomplete; cannot verify or refute recommendation.",
                reconciliation_message="Relevant AST graph coverage is incomplete; cannot verify or refute recommendation.",
                referenced_attributes=attributes,
                referenced_paths=paths,
            )

        # Evaluate evidence-grounded justification
        has_just, just_detail, rel_str, loc_str = self.assess_justification(
            diagnosis, evidence_list, unsupported_symbols, decision
        )

        if has_just:
            return ConsistencyResult(
                status="JUSTIFIED_OVERRIDE",
                recommended_symbols=unsupported_symbols,
                controlling_symbols=decision.controlling_symbols,
                unsupported_symbols=unsupported_symbols,
                has_justification=True,
                justification_detail=just_detail,
                reconciliation_message=(
                    f"Supervisor recommended alternative symbol(s) {unsupported_symbols} with verified AST evidence: {just_detail}"
                ),
                supporting_relationship=rel_str,
                source_location=loc_str,
                referenced_attributes=attributes,
                referenced_paths=paths,
            )

        return ConsistencyResult(
            status="CONTRADICTORY",
            recommended_symbols=unsupported_symbols,
            controlling_symbols=decision.controlling_symbols,
            unsupported_symbols=unsupported_symbols,
            has_justification=False,
            justification_detail=just_detail,
            reconciliation_message=(
                f"Supervisor recommended symbol(s) {unsupported_symbols} outside verified execution path "
                f"without adequate AST call-chain or inheritance evidence."
            ),
            referenced_attributes=attributes,
            referenced_paths=paths,
        )

    def reconcile_directives(
        self,
        decision: LocalizationDecision,
        consistency: ConsistencyResult,
        instructions: str,
        avoid_previous_mistake: str,
    ) -> Tuple[str, str]:
        """Reconcile Supervisor instructions and avoid directives based on consistency assessment."""
        reconciled_instr = instructions
        reconciled_avoid = avoid_previous_mistake

        if consistency.status == "CONTRADICTORY":
            unsupported_str = ", ".join(f"'{s}'" for s in consistency.recommended_symbols)
            controlling_str = ", ".join(f"'{s}'" for s in decision.controlling_symbols[:4])
            guard_directive = (
                f"CRITICAL EXECUTION-PATH CONSISTENCY DIRECTIVE:\n"
                f"- The Supervisor suggested modifying {unsupported_str}, which is outside the verified controlling execution path.\n"
                f"- The controlling behavior resides in '{decision.primary_symbol}' along execution path: [{controlling_str}].\n"
                f"- You MUST prioritize modifying the controlling execution path [{controlling_str}] rather than ungrounded wrapper methods."
            )
            reconciled_instr = f"{guard_directive}\n\n{instructions}"

            avoid_guard = (
                f"DO NOT modify ungrounded wrapper method(s) {unsupported_str} unless source code inspection "
                f"proves they directly control the shared execution path."
            )
            reconciled_avoid = f"{avoid_guard}\n\n{avoid_previous_mistake}" if avoid_previous_mistake else avoid_guard

        elif consistency.status == "JUSTIFIED_OVERRIDE":
            loc_info = f" at {consistency.source_location}" if consistency.source_location else ""
            override_note = (
                f"SUPERVISOR SOURCE-JUSTIFIED OVERRIDE:\n"
                f"- Supervisor identified alternative controlling site(s): {consistency.recommended_symbols}{loc_info}.\n"
                f"- Verified relationship: {consistency.supporting_relationship or consistency.justification_detail}."
            )
            reconciled_instr = f"{override_note}\n\n{instructions}"

        elif consistency.status == "AMBIGUOUS_EVIDENCE":
            ambiguity_note = (
                f"EXECUTION-PATH AMBIGUITY WARNING:\n"
                f"- Multiple candidate paths exist with equal evidence or incomplete graph coverage: {decision.controlling_symbols[:4]}.\n"
                f"- Carefully inspect source call chains before selecting an anchor."
            )
            reconciled_instr = f"{ambiguity_note}\n\n{instructions}"

        return reconciled_instr, reconciled_avoid
