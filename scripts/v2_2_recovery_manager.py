"""DDIV v2.2 Recovery Manager & Anti-Repetition Tracking.

Provides:
1. ProposalHistory: In-memory cache of past modification proposals to detect
   and prevent byte-for-byte or semantically identical repetition cycles.
2. FailureDisambiguator: Accurate mapping of raw execution and patch builder errors
   into disambiguated failure categories (TARGET_FILE_NOT_FOUND, SYNTAX_ERROR_INDENTATION,
   ANCHOR_NOT_FOUND, REPEATED_PATCH_CYCLE, F2P_FAILURE, P2P_REGRESSION).
3. Formatter: Generates negative constraints and actionable directives for Coder and Supervisor.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from pydantic import BaseModel, Field


def extract_source_grounding_context(
    workspace_path: Optional[Path],
    target_file: str,
    symbol_hint: Optional[str] = None,
    file_content: Optional[str] = None,
) -> str:
    """Extract real function signature, in-scope local variables, and actual return statements.

    Prevents hallucination of placeholder names ('result', 'temp') or hypothetical anchors ('return result').
    """
    if not file_content:
        if not workspace_path or not target_file:
            return ""
        full_path = workspace_path / target_file
        if not full_path.exists():
            return ""
        try:
            file_content = full_path.read_text(encoding="utf-8")
        except Exception:
            return ""

    if not file_content:
        return ""

    try:
        tree = ast.parse(file_content)
    except Exception:
        return ""

    target_nodes: List[Union[ast.FunctionDef, ast.AsyncFunctionDef]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if symbol_hint:
                clean_sym = symbol_hint.split(".")[-1]
                if node.name == clean_sym or node.name == symbol_hint:
                    target_nodes.append(node)
            else:
                target_nodes.append(node)

    if not target_nodes:
        target_nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    if not target_nodes:
        return ""

    fn = target_nodes[0]

    params = [a.arg for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs]
    if fn.args.vararg:
        params.append(f"*{fn.args.vararg.arg}")
    if fn.args.kwarg:
        params.append(f"**{fn.args.kwarg.arg}")

    local_vars: Set[str] = set()
    return_statements: List[str] = []
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Assign):
            for t in sub.targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        local_vars.add(n.id)
        elif isinstance(sub, ast.AnnAssign):
            for n in ast.walk(sub.target):
                if isinstance(n, ast.Name):
                    local_vars.add(n.id)
        elif isinstance(sub, ast.AugAssign):
            for n in ast.walk(sub.target):
                if isinstance(n, ast.Name):
                    local_vars.add(n.id)
        elif isinstance(sub, ast.Return):
            if sub.value:
                try:
                    ret_str = f"return {ast.unparse(sub.value)}"
                except Exception:
                    ret_str = "return <expr>"
            else:
                ret_str = "return"
            return_statements.append(ret_str)

    local_vars.difference_update(params)
    param_str = ", ".join(params) if params else "None"
    var_str = ", ".join(sorted(local_vars)) if local_vars else "None"
    ret_str = "\n".join(f"  - `{r}`" for r in return_statements) if return_statements else "  - None"

    actual_ret_preview = return_statements[0] if return_statements else "None"

    return (
        f"CRITICAL VERIFIED SOURCE GROUNDING (Target: `{target_file}` -> `{fn.name}`):\n"
        f"- Verified Parameters: {param_str}\n"
        f"- Verified Local Variables in Function: {var_str}\n"
        f"- Verified Return Statements in Source:\n{ret_str}\n"
        f"GROUNDING MANDATES:\n"
        f"1. Do NOT reference placeholder variable names (e.g. 'result', 'temp', 'data') unless that identifier is explicitly verified above.\n"
        f"2. Do NOT use nonexistent anchors like 'return result'. The actual return in source is: `{actual_ret_preview}`."
    )

def are_codes_ast_equivalent(code1: str, code2: str) -> bool:
    """Check if two Python code snippets have identical AST structure (ignoring comments/formatting)."""
    c1 = code1 or ""
    c2 = code2 or ""
    if not c1.strip() and not c2.strip():
        return True
    if not c1.strip() or not c2.strip():
        return False
    if "".join(c1.split()) == "".join(c2.split()):
        return True
    try:
        import textwrap
        dedented1 = textwrap.dedent(c1).strip()
        dedented2 = textwrap.dedent(c2).strip()
        tree1 = ast.parse(dedented1)
        tree2 = ast.parse(dedented2)
        return ast.dump(tree1, include_attributes=False) == ast.dump(tree2, include_attributes=False)
    except Exception:
        return "".join(c1.split()) == "".join(c2.split())


class ProposalRecord(BaseModel):
    attempt: int
    path: str
    operation: str
    anchor: str
    code: str
    target_symbol: Optional[str] = None
    target_class: Optional[str] = None
    error_category: str = "UNKNOWN"
    error_detail: str = ""
    f2p_passed: bool = False
    p2p_passed: bool = False


class ProposalHistory:
    """Tracks and checks modification proposals across attempts to eliminate repetition cycles."""

    def __init__(self):
        self.records: List[ProposalRecord] = []

    def record_attempt(
        self,
        attempt: int,
        path: str,
        operation: str,
        anchor: str,
        code: str,
        target_symbol: Optional[str] = None,
        target_class: Optional[str] = None,
        error_category: str = "UNKNOWN",
        error_detail: str = "",
        f2p_passed: bool = False,
        p2p_passed: bool = False,
    ) -> ProposalRecord:
        rec = ProposalRecord(
            attempt=attempt,
            path=path.strip().replace("\\", "/"),
            operation=operation.strip().lower(),
            anchor=anchor,
            code=code or "",
            target_symbol=target_symbol,
            target_class=target_class,
            error_category=error_category,
            error_detail=error_detail,
            f2p_passed=f2p_passed,
            p2p_passed=p2p_passed,
        )
        self.records.append(rec)
        return rec

    def is_repeated(
        self,
        path: str,
        operation: str,
        anchor: str,
        code: str,
        target_symbol: Optional[str] = None,
        target_class: Optional[str] = None,
    ) -> Optional[int]:
        """Check if proposed modification matches an earlier failed attempt.

        Returns the attempt index of the match if repeated, or None if novel.
        Permits retrying an ambiguous anchor if valid structural disambiguation is supplied.
        Blocks semantically equivalent failed edits to the same resolved target.
        """
        norm_path = path.strip().replace("\\", "/").lower()
        norm_op = operation.strip().lower()
        norm_anc = "".join(anchor.split())
        norm_code = "".join((code or "").split())

        for rec in self.records:
            r_path = rec.path.strip().replace("\\", "/").lower()
            r_op = rec.operation.strip().lower()
            if norm_path != r_path or norm_op != r_op:
                continue

            r_anc = "".join(rec.anchor.split())
            r_code = "".join((rec.code or "").split())

            # Case 1: Retry of an ambiguous anchor with new structural disambiguation
            is_rec_ambiguous = rec.error_category in (
                "ANCHOR_AMBIGUOUS",
                "ANCHOR_AMBIGUOUS_MULTI_CLASS",
                "ANCHOR_AMBIGUOUS_IN_SCOPE",
            )
            rec_has_target = bool(rec.target_symbol or rec.target_class)
            prop_has_target = bool(target_symbol or target_class)

            if norm_anc == r_anc and is_rec_ambiguous and (not rec_has_target) and prop_has_target:
                # New proposal supplies valid structural disambiguation for previously ambiguous anchor -> ALLOW
                continue

            # Case 2: Same resolved target (or both unscoped)
            same_target = (
                (rec.target_symbol == target_symbol and rec.target_class == target_class)
                or (not rec_has_target and not prop_has_target)
            )

            if same_target:
                # Exact identical edit
                if norm_anc == r_anc and norm_code == r_code:
                    return rec.attempt

                # AST equivalent code on same anchor
                if norm_anc == r_anc and are_codes_ast_equivalent(code, rec.code):
                    return rec.attempt

                # Repeated invalid anchors (nonexistent or ambiguous without new disambiguation)
                if norm_anc == r_anc and rec.error_category in (
                    "ANCHOR_AMBIGUOUS",
                    "ANCHOR_AMBIGUOUS_MULTI_CLASS",
                    "ANCHOR_NOT_FOUND",
                    "ANCHOR_NOT_IN_TARGET_SCOPE",
                ):
                    return rec.attempt

        return None

    def format_negative_constraints(self) -> str:
        """Format previous failed proposals as explicit negative directives for the next attempt."""
        if not self.records:
            return ""

        lines = [
            "CRITICAL DIRECTIVE: DO NOT REPEAT PREVIOUS FAILED PROPOSALS:",
        ]
        for rec in self.records:
            anc_preview = rec.anchor.strip()
            if len(anc_preview) > 60:
                anc_preview = anc_preview[:57] + "..."

            target_info = f" (target: '{rec.target_symbol}')" if rec.target_symbol else ""
            if rec.error_category in ("ANCHOR_AMBIGUOUS_MULTI_CLASS", "ANCHOR_AMBIGUOUS"):
                directive = (
                    f"- Attempt {rec.attempt}: Modified '{rec.path}'{target_info} at anchor '{anc_preview}'. "
                    f"Result: [{rec.error_category}] {rec.error_detail[:140]}. "
                    f"You MUST NOT repeat this ambiguous anchor without specifying 'target_symbol' (e.g. '<ClassName>.<method>') or 'target_class' to disambiguate."
                )
            elif rec.error_category == "STALE_ANCHOR":
                directive = (
                    f"- Attempt {rec.attempt}: Modified '{rec.path}'{target_info} at anchor '{anc_preview}'. "
                    f"Result: [STALE_ANCHOR] Source fingerprint mismatched. "
                    f"You MUST re-read the target file and use the current source content for anchor and source_fingerprint."
                )
            elif rec.error_category == "UNDEFINED_VARIABLE":
                directive = (
                    f"- Attempt {rec.attempt}: Modified '{rec.path}'{target_info}. "
                    f"Result: [UNDEFINED_VARIABLE] {rec.error_detail[:140]}. "
                    f"You MUST NOT introduce undefined variables. Only use variables verified in the function scope."
                )
            elif rec.error_category == "ANCHOR_NOT_FOUND":
                directive = (
                    f"- Attempt {rec.attempt}: Modified '{rec.path}'{target_info} at anchor '{anc_preview}'. "
                    f"Result: [ANCHOR_NOT_FOUND] {rec.error_detail[:140]}. "
                    f"You MUST NOT reuse this anchor. Copy an exact anchor line verbatim from the target source file."
                )
            elif rec.error_category in ("SYNTAX_ERROR_INDENTATION", "INVALID_SCOPE"):
                directive = (
                    f"- Attempt {rec.attempt}: Modified '{rec.path}'{target_info} at anchor '{anc_preview}'. "
                    f"Result: [{rec.error_category}] {rec.error_detail[:140]}. "
                    f"You MUST ensure code is placed inside a valid method (use 'insert_after' with method header), NOT at class body scope."
                )
            else:
                directive = (
                    f"- Attempt {rec.attempt}: Modified '{rec.path}'{target_info} (op: {rec.operation}) at anchor '{anc_preview}'. "
                    f"Result: [{rec.error_category}] {rec.error_detail[:120]}. "
                    f"You MUST NOT generate this semantically identical modification again."
                )
            lines.append(directive)

        return "\n".join(lines)


class FailureDisambiguator:
    """Disambiguates empirical failure modes while preserving original error details."""

    @staticmethod
    def classify(
        patch_valid: bool,
        patch_applied: bool,
        pb_error_category: Optional[str] = None,
        pb_error_message: Optional[str] = None,
        coder_error_code: Optional[str] = None,
        coder_error_msg: Optional[str] = None,
        f2p_passed: bool = False,
        p2p_passed: bool = False,
        is_repeated: bool = False,
        internal_resolved: bool = False,
    ) -> Tuple[str, str]:
        """Returns (normalized_failure_category, detailed_explanation)."""
        if internal_resolved:
            return "RESOLVED", "Patch passed all target and regression tests."

        if is_repeated:
            return "REPEATED_PATCH_CYCLE", "Proposed patch is identical to an earlier failed attempt."

        pb_cat = (pb_error_category or "").upper()
        pb_msg = pb_error_message or ""

        if pb_cat in (
            "ANCHOR_AMBIGUOUS_MULTI_CLASS",
            "ANCHOR_AMBIGUOUS_IN_SCOPE",
            "ANCHOR_NOT_IN_TARGET_SCOPE",
            "STALE_ANCHOR",
            "OUT_OF_RANGE_ANCHOR",
        ):
            return pb_cat, pb_msg

        if pb_cat == "FILE_NOT_FOUND" or "target file not found" in pb_msg.lower():
            return "TARGET_FILE_NOT_FOUND", pb_msg or "Target file does not exist in workspace."

        if pb_cat == "UNDEFINED_VARIABLE" or "undefined local variable" in pb_msg.lower():
            return "UNDEFINED_VARIABLE", pb_msg or "Patch referenced undefined local variable."

        if pb_cat == "INVALID_SCOPE" or "scope verification" in pb_msg.lower() or "class scope" in pb_msg.lower():
            return "SYNTAX_ERROR_INDENTATION", pb_msg or "Patch attempted to place statements in an invalid Python scope."

        if (
            pb_cat in ("SYNTAX_ERROR", "SYNTAX_ERROR_INDENTATION")
            or "syntax verification" in pb_msg.lower()
            or "unexpected indent" in pb_msg.lower()
            or "indentation" in pb_msg.lower()
        ):
            return "SYNTAX_ERROR_INDENTATION", pb_msg or "Modified file failed Python AST syntax verification."

        if pb_cat == "ANCHOR_NOT_FOUND" or "anchor not found" in pb_msg.lower():
            return "ANCHOR_NOT_FOUND", pb_msg or "Anchor string was not found in target file."

        if pb_cat == "ANCHOR_AMBIGUOUS":
            return "ANCHOR_AMBIGUOUS", pb_msg or "Anchor matched multiple locations in target file."

        if not patch_valid:
            return "PATCH_INVALID", coder_error_msg or pb_msg or "Patch failed validation."

        if not patch_applied:
            return "PATCH_APPLICATION_FAILED", "Patch could not be applied cleanly to workspace."

        if not p2p_passed:
            return "P2P_REGRESSION", "Patch caused regressions on existing passing tests."

        if not f2p_passed:
            return "F2P_FAILURE", "Target bug reproduction tests failed (incomplete or incorrect logic)."

        return "UNKNOWN_FAILURE", coder_error_msg or "Unclassified failure."

    @staticmethod
    def format_test_counts(
        internal_eval: Dict[str, Any],
        ground_truth_f2p_total: Optional[int] = None,
        ground_truth_p2p_total: Optional[int] = None,
    ) -> Tuple[str, str]:
        """Safely format F2P and P2P counts distinguishing unexecuted tests from 0-test denominators."""
        f2p_res = internal_eval.get("fail_to_pass_results") or {}
        p2p_res = internal_eval.get("pass_to_pass_results") or {}

        if f2p_res:
            f2p_p = sum(1 for v in f2p_res.values() if v is True)
            f2p_t = len(f2p_res)
            f2p_str = f"{f2p_p}/{f2p_t}"
        elif "Candidate patch application failed" in internal_eval.get("verdict", "") or internal_eval.get("candidate_patch_applied") is False:
            f2p_denom = f"{ground_truth_f2p_total}" if ground_truth_f2p_total is not None else "?"
            f2p_str = f"0/{f2p_denom} (Not Run - Apply Failed)"
        else:
            f2p_denom = f"{ground_truth_f2p_total}" if ground_truth_f2p_total is not None else "0"
            f2p_str = f"0/{f2p_denom}"

        if p2p_res:
            p2p_p = sum(1 for v in p2p_res.values() if v is True)
            p2p_t = len(p2p_res)
            p2p_str = f"{p2p_p}/{p2p_t}"
        elif "Candidate patch application failed" in internal_eval.get("verdict", "") or internal_eval.get("candidate_patch_applied") is False:
            p2p_denom = f"{ground_truth_p2p_total}" if ground_truth_p2p_total is not None else "?"
            p2p_str = f"0/{p2p_denom} (Not Run - Apply Failed)"
        else:
            p2p_denom = f"{ground_truth_p2p_total}" if ground_truth_p2p_total is not None else "0"
            p2p_str = f"0/{p2p_denom}"

        return f2p_str, p2p_str

    format_test_metrics = format_test_counts


format_test_metrics = FailureDisambiguator.format_test_counts


import core.experiment_worker as ew
from core.conditions import ExperimentCondition
from core.experiment_record import ExperimentConditionRecord
from core.experiment_worker import ExperimentWorker
from recovery.failure_detector import FailureType, GranularFailureType


class V22SupervisedWorker(ExperimentWorker):
    """ExperimentWorker enhanced with v2.2 Anti-Repetition and Failure Disambiguation.

    Guarantees:
    - Scoped strictly to supervisor-enabled conditions; passes through unmodified for other conditions.
    - Guaranteed restoration of patched methods in a finally block even on unhandled exceptions.
    - Zero state leakage across worker runs.
    """

    ANCHOR_RULES = (
        "CRITICAL ANCHOR GROUNDING RULES:\n"
        "1. The 'anchor' string MUST be copied VERBATIM from '=== SOURCE CODE IN RELEVANT FILES ==='.\n"
        "2. Do NOT invent, simplify, or reformat function signatures or parameters.\n"
        "3. Do NOT collapse multi-line definitions into a single line.\n"
        "4. Select 1 to 3 unique lines that appear EXACTLY as written in the target file.\n"
        "5. Target ONLY the relevant implementation files, NEVER test files.\n"
        "6. If the target method or anchor exists in multiple classes, specify 'target_symbol': 'ClassName.method_name' or 'target_class': 'ClassName' to bind the edit to the intended AST scope."
    )
    SCOPE_RULES = (
        "CRITICAL SCOPE DIRECTIVE:\n"
        "1. Do NOT insert statements before 'def' or at class body level.\n"
        "2. To place statements inside a method, use 'operation': 'insert_after' with the 'def ...:' method header as anchor, NOT 'insert_before'.\n"
        "3. 'return' is strictly illegal outside functions/methods."
    )

    def __init__(self, *args, **kwargs):
        if "condition" in kwargs and isinstance(kwargs["condition"], str):
            kwargs["condition"] = ExperimentCondition.from_str(kwargs["condition"])
        elif len(args) > 1 and isinstance(args[1], str):
            args = list(args)
            args[1] = ExperimentCondition.from_str(args[1])
            args = tuple(args)

        # Handle experiment_config model overrides
        experiment_config = kwargs.pop("experiment_config", None)
        if experiment_config is not None:
            import json
            import copy
            import os
            from pathlib import Path
            from core.config import DDIVConfig

            if isinstance(experiment_config, (str, Path)):
                with open(experiment_config, "r", encoding="utf-8") as f:
                    exp_cfg_dict = json.load(f)
            else:
                exp_cfg_dict = experiment_config

            base_cfg = kwargs.get("config") or DDIVConfig.load_from_env()
            worker_cfg = copy.deepcopy(base_cfg)
            models_spec = exp_cfg_dict.get("models", {})
            if "Coder" in models_spec:
                c_spec = models_spec["Coder"]
                worker_cfg.coder.provider = c_spec.get("provider", "ollama")
                worker_cfg.coder.model = c_spec.get("model_id", "qwen2.5-coder:7b")
                if worker_cfg.coder.provider == "ollama":
                    worker_cfg.coder.api_key = "ollama"
                    worker_cfg.coder.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
                    worker_cfg.coder.timeout = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "240"))
                    try:
                        from scripts.ollama_coder_adapter import register_ollama_provider
                        register_ollama_provider()
                    except ImportError:
                        pass
                if "temperature" in c_spec:
                    worker_cfg.coder.temperature = float(c_spec["temperature"])

            for role, attr in [("Supervisor", "supervisor"), ("Tester", "tester"), ("Locator", "locator")]:
                if role in models_spec:
                    spec = models_spec[role]
                    agent_cfg = getattr(worker_cfg, attr)
                    if "provider" in spec and spec["provider"]:
                        agent_cfg.provider = spec["provider"]
                    if "model_id" in spec and spec["model_id"]:
                        agent_cfg.model = spec["model_id"]
                    if "temperature" in spec and spec["temperature"] is not None:
                        agent_cfg.temperature = float(spec["temperature"])

            kwargs["config"] = worker_cfg

        super().__init__(*args, **kwargs)
        self.proposal_history = ProposalHistory()
        self.last_coder_mods: List[Any] = []

    def run(self) -> ExperimentConditionRecord:
        # Strictly enforce condition scoping: only supervisor-enabled conditions use recovery hooks
        if not self.condition.is_supervisor_enabled:
            return super().run()

        # Capture original class methods for guaranteed restoration
        from scripts.demo_patch_builder import DemoPatchBuilder
        original_coder_execute = ew.CoderAgent.execute
        original_sup_execute = ew.SupervisorAgent.execute
        original_fd_eval = ew.FailureDetector.evaluate
        original_patch_builder = ew.DeterministicPatchBuilder

        def coder_execute_hook(coder_self, coder_input, meta):
            if meta.attempt == 1:
                rules_block = f"{self.ANCHOR_RULES}\n\n{self.SCOPE_RULES}"
                loc_text = ""
                if hasattr(self, "last_localization_decision") and self.last_localization_decision:
                    dec = self.last_localization_decision
                    if dec.status == "RESOLVED":
                        loc_text = (
                            f"EXECUTION-PATH LOCALIZATION GUIDANCE:\n"
                            f"{dec.evidence_rationale}\n"
                            f"Target File: {dec.target_file}\n"
                            f"Primary Controlling Symbol: {dec.primary_symbol}\n"
                            f"Target the controlling method on this execution path rather than superficial facade wrappers.\n"
                            f"CRITICAL: Set 'target_symbol': '{dec.primary_symbol}' in your modification payload to ensure unambiguous AST anchoring."
                        )
                    elif dec.status == "AMBIGUOUS":
                        loc_text = (
                            f"EXECUTION-PATH AMBIGUITY WARNING:\n"
                            f"Multiple candidate execution paths detected ({dec.controlling_symbols}). "
                            f"Carefully verify call chains and method implementations before choosing an anchor."
                        )
                parts = [p for p in [loc_text, rules_block] if p]
                guidance = "\n\n".join(parts)
                curr_rec = coder_input.get("recovery_instructions") or ""
                coder_input["recovery_instructions"] = f"{curr_rec}\n\n{guidance}" if curr_rec else guidance

            res = original_coder_execute(coder_self, coder_input, meta)
            if res.success and res.output:
                # Ensure all structural metadata survives from raw response to DemoPatchBuilder
                try:
                    import json
                    from scripts.demo_patch_builder import StructuralCodeModification
                    raw_dict = None
                    if hasattr(res, "raw_response") and res.raw_response:
                        raw_str = res.raw_response.strip()
                        if "```json" in raw_str:
                            raw_str = raw_str.split("```json")[1].split("```")[0].strip()
                        elif "```" in raw_str:
                            raw_str = raw_str.split("```")[1].split("```")[0].strip()
                        raw_dict = json.loads(raw_str)

                    if raw_dict and "modifications" in raw_dict and isinstance(raw_dict["modifications"], list):
                        upgraded = []
                        for i, raw_m in enumerate(raw_dict["modifications"]):
                            if isinstance(raw_m, dict):
                                try:
                                    upgraded.append(StructuralCodeModification(**raw_m))
                                except Exception:
                                    if i < len(res.output.modifications):
                                        upgraded.append(res.output.modifications[i])
                            else:
                                if i < len(res.output.modifications):
                                    upgraded.append(res.output.modifications[i])
                        if upgraded:
                            res.output.modifications = upgraded
                except Exception:
                    pass

                self.last_coder_mods = getattr(res.output, "modifications", []) or []
            else:
                self.last_coder_mods = []
            return res

        def supervised_execute_hook(sup_self, sup_input, meta):
            # Record current mods into history before supervisor formats constraints
            from scripts.demo_patch_builder import DemoPatchBuilder
            last_pb = DemoPatchBuilder.last_result
            err_cat = "UNRESOLVED_ATTEMPT"
            err_msg = f"Attempt {meta.attempt} failed validation/tests."
            if last_pb and not last_pb.success:
                err_cat = last_pb.error_category or err_cat
                err_msg = last_pb.error_message or err_msg

            for m in self.last_coder_mods:
                p = (getattr(m, "path", None) if not isinstance(m, dict) else m.get("path")) or ""
                op = (getattr(m, "operation", None) if not isinstance(m, dict) else m.get("operation")) or ""
                anc = (getattr(m, "anchor", None) if not isinstance(m, dict) else m.get("anchor")) or ""
                c = (getattr(m, "code", None) if not isinstance(m, dict) else m.get("code")) or ""
                tsym = (getattr(m, "target_symbol", None) if not isinstance(m, dict) else m.get("target_symbol")) or None
                tcls = (getattr(m, "target_class", None) if not isinstance(m, dict) else m.get("target_class")) or None
                self.proposal_history.record_attempt(
                    attempt=meta.attempt,
                    path=p,
                    operation=op,
                    anchor=anc,
                    code=c,
                    target_symbol=tsym,
                    target_class=tcls,
                    error_category=err_cat,
                    error_detail=err_msg,
                )

            sup_res = original_sup_execute(sup_self, sup_input, meta)
            if sup_res.success and sup_res.output:
                dec = sup_res.output
                neg_constraints = self.proposal_history.format_negative_constraints()
                rules_block = f"{self.ANCHOR_RULES}\n\n{self.SCOPE_RULES}"

                # Extract verified source grounding context from target file
                grounding_context = ""
                target_file = None
                target_sym = None
                if self.last_coder_mods:
                    m = self.last_coder_mods[0]
                    target_file = (getattr(m, "path", None) if not isinstance(m, dict) else m.get("path")) or None
                    target_sym = (getattr(m, "target_symbol", None) if not isinstance(m, dict) else m.get("target_symbol")) or None
                elif hasattr(self, "last_localization_decision") and self.last_localization_decision:
                    target_file = getattr(self.last_localization_decision, "target_file", None)
                    target_sym = getattr(self.last_localization_decision, "primary_symbol", None)

                ws_dir = getattr(self, "current_agent_ws_path", None) or getattr(self, "agent_ws_path", None)
                if not ws_dir and hasattr(self, "current_agent_ws") and self.current_agent_ws:
                    ws_dir = getattr(self.current_agent_ws, "path", None)
                if not ws_dir and hasattr(self, "workspace_root"):
                    ws_dir = self.workspace_root

                if target_file and ws_dir:
                    grounding_context = extract_source_grounding_context(
                        workspace_path=Path(ws_dir),
                        target_file=target_file,
                        symbol_hint=target_sym,
                    )

                blocks = [rules_block]
                if grounding_context:
                    blocks.append(grounding_context)
                if neg_constraints:
                    blocks.append(neg_constraints)
                combined_constraints = "\n\n".join(blocks)

                current_avoid = dec.avoid_previous_mistake or ""
                if current_avoid:
                    dec.avoid_previous_mistake = f"{current_avoid}\n\n{combined_constraints}"
                else:
                    dec.avoid_previous_mistake = combined_constraints
            return sup_res

        def fd_eval_hook(fd_self, **kwargs):
            det_res = original_fd_eval(fd_self, **kwargs)
            coder_err = kwargs.get("coder_error_code")
            coder_detail = kwargs.get("coder_error_detail")
            f2p = kwargs.get("f2p_passed", False)
            p2p = kwargs.get("p2p_passed", False)
            patch_val = kwargs.get("patch_valid", False)
            patch_app = kwargs.get("patch_applied", False)

            # Check for patch cycle using proposal history
            is_rep = False
            for m in self.last_coder_mods:
                p = getattr(m, "path", None) if not isinstance(m, dict) else m.get("path")
                op = getattr(m, "operation", None) if not isinstance(m, dict) else m.get("operation")
                anc = getattr(m, "anchor", None) if not isinstance(m, dict) else m.get("anchor")
                c = getattr(m, "code", None) if not isinstance(m, dict) else m.get("code")
                if p and op and anc:
                    rep_att = self.proposal_history.is_repeated(p, op, anc, c or "")
                    if rep_att is not None and rep_att < kwargs.get("attempt", 1):
                        is_rep = True
                        break

            norm_cat, exp = FailureDisambiguator.classify(
                patch_valid=patch_val,
                patch_applied=patch_app,
                pb_error_category=getattr(det_res, "pb_error_category", None) or coder_err,
                pb_error_message=getattr(det_res, "pb_error_message", None) or coder_detail,
                coder_error_code=coder_err,
                coder_error_msg=coder_detail,
                f2p_passed=f2p,
                p2p_passed=p2p,
                is_repeated=is_rep,
                internal_resolved=(det_res.candidate_failure_type is None and not det_res.is_failure),
            )

            if is_rep:
                det_res.candidate_failure_type = FailureType.F4
                det_res.granular_failure_type = GranularFailureType.REPEATED_PATCH_CYCLE
                det_res.evidence_reasons.append(f"Disambiguated root cause: [REPEATED_PATCH_CYCLE] {exp}")
            elif norm_cat == "TARGET_FILE_NOT_FOUND":
                det_res.candidate_failure_type = FailureType.F3
                det_res.granular_failure_type = GranularFailureType.PATCH_INVALID
                det_res.evidence_reasons.append(f"Disambiguated root cause: [TARGET_FILE_NOT_FOUND] {exp}")
            elif norm_cat == "SYNTAX_ERROR_INDENTATION":
                det_res.candidate_failure_type = FailureType.F3
                det_res.granular_failure_type = GranularFailureType.PATCH_INVALID
                det_res.evidence_reasons.append(f"Disambiguated root cause: [SYNTAX_ERROR_INDENTATION] {exp}")
            elif norm_cat == "UNDEFINED_VARIABLE":
                det_res.candidate_failure_type = FailureType.F2
                det_res.granular_failure_type = GranularFailureType.PATCH_INVALID
                det_res.evidence_reasons.append(f"Disambiguated root cause: [UNDEFINED_VARIABLE] {exp}")
            elif norm_cat == "ANCHOR_NOT_FOUND":
                det_res.candidate_failure_type = FailureType.F3
                det_res.granular_failure_type = GranularFailureType.ANCHOR_NOT_FOUND
                det_res.evidence_reasons.append(f"Disambiguated root cause: [ANCHOR_NOT_FOUND] {exp}")

            return det_res

        # Apply monkey patches
        ew.CoderAgent.execute = coder_execute_hook
        ew.SupervisorAgent.execute = supervised_execute_hook
        ew.FailureDetector.evaluate = fd_eval_hook
        ew.DeterministicPatchBuilder = DemoPatchBuilder

        try:
            return super().run()
        finally:
            ew.CoderAgent.execute = original_coder_execute
            ew.SupervisorAgent.execute = original_sup_execute
            ew.FailureDetector.evaluate = original_fd_eval
            ew.DeterministicPatchBuilder = original_patch_builder
