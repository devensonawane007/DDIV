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

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class ProposalRecord(BaseModel):
    attempt: int
    path: str
    operation: str
    anchor: str
    code: str
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
            error_category=error_category,
            error_detail=error_detail,
            f2p_passed=f2p_passed,
            p2p_passed=p2p_passed,
        )
        self.records.append(rec)
        return rec

    def is_repeated(self, path: str, operation: str, anchor: str, code: str) -> Optional[int]:
        """Check if proposed modification matches an earlier attempt (normalized whitespace).

        Returns the attempt index of the match if repeated, or None if novel.
        """
        norm_path = path.strip().replace("\\", "/").lower()
        norm_op = operation.strip().lower()
        norm_anc = "".join(anchor.split())
        norm_code = "".join((code or "").split())

        for rec in self.records:
            r_path = rec.path.strip().replace("\\", "/").lower()
            r_op = rec.operation.strip().lower()
            r_anc = "".join(rec.anchor.split())
            r_code = "".join((rec.code or "").split())

            if norm_path == r_path and norm_op == r_op and norm_anc == r_anc and norm_code == r_code:
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
            lines.append(
                f"- Attempt {rec.attempt}: Modified '{rec.path}' (op: {rec.operation}) at anchor '{anc_preview}'. "
                f"Result: [{rec.error_category}] {rec.error_detail[:120]}. "
                f"You MUST NOT generate this identical modification again."
            )

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

        if pb_cat == "FILE_NOT_FOUND" or "target file not found" in pb_msg.lower():
            return "TARGET_FILE_NOT_FOUND", pb_msg or "Target file does not exist in workspace."

        if pb_cat == "SYNTAX_ERROR" or "syntax verification" in pb_msg.lower() or "unexpected indent" in pb_msg.lower():
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


import core.experiment_worker as ew
from core.conditions import ExperimentCondition
from core.experiment_record import ExperimentConditionRecord
from core.experiment_worker import ExperimentWorker
from recovery.failure_detector import GranularFailureType


class V22SupervisedWorker(ExperimentWorker):
    """ExperimentWorker enhanced with v2.2 Anti-Repetition and Failure Disambiguation.

    Guarantees:
    - Scoped strictly to FULL_DDIV; passes through unmodified for other conditions.
    - Guaranteed restoration of patched methods in a finally block even on unhandled exceptions.
    - Zero state leakage across worker runs.
    """

    def __init__(self, *args, **kwargs):
        if "condition" in kwargs and isinstance(kwargs["condition"], str):
            kwargs["condition"] = ExperimentCondition.from_str(kwargs["condition"])
        elif len(args) > 1 and isinstance(args[1], str):
            args = list(args)
            args[1] = ExperimentCondition.from_str(args[1])
            args = tuple(args)
        super().__init__(*args, **kwargs)
        self.proposal_history = ProposalHistory()
        self.last_coder_mods: List[Any] = []

    def run(self) -> ExperimentConditionRecord:
        # Strictly enforce condition scoping: only FULL_DDIV uses recovery hooks
        if self.condition != ExperimentCondition.FULL_DDIV:
            return super().run()

        # Capture original class methods for guaranteed restoration
        original_coder_execute = ew.CoderAgent.execute
        original_sup_execute = ew.SupervisorAgent.execute
        original_fd_eval = ew.FailureDetector.evaluate

        def coder_execute_hook(coder_self, coder_input, meta):
            res = original_coder_execute(coder_self, coder_input, meta)
            if res.success and res.output:
                self.last_coder_mods = getattr(res.output, "modifications", []) or []
            else:
                self.last_coder_mods = []
            return res

        def supervised_execute_hook(sup_self, sup_input, meta):
            # Record current mods into history before supervisor formats constraints
            for m in self.last_coder_mods:
                p = (getattr(m, "path", None) if not isinstance(m, dict) else m.get("path")) or ""
                op = (getattr(m, "operation", None) if not isinstance(m, dict) else m.get("operation")) or ""
                anc = (getattr(m, "anchor", None) if not isinstance(m, dict) else m.get("anchor")) or ""
                c = (getattr(m, "code", None) if not isinstance(m, dict) else m.get("code")) or ""
                self.proposal_history.record_attempt(
                    attempt=meta.attempt,
                    path=p,
                    operation=op,
                    anchor=anc,
                    code=c,
                    error_category="UNRESOLVED_ATTEMPT",
                    error_detail=f"Attempt {meta.attempt} failed validation/tests.",
                )

            sup_res = original_sup_execute(sup_self, sup_input, meta)
            if sup_res.success and sup_res.output:
                dec = sup_res.output
                neg_constraints = self.proposal_history.format_negative_constraints()
                if neg_constraints:
                    current_avoid = dec.avoid_previous_mistake or ""
                    if current_avoid:
                        dec.avoid_previous_mistake = f"{current_avoid}\n\n{neg_constraints}"
                    else:
                        dec.avoid_previous_mistake = neg_constraints
            return sup_res

        def fd_eval_hook(fd_self, **kwargs):
            det_res = original_fd_eval(fd_self, **kwargs)
            coder_err = kwargs.get("coder_error_code")
            coder_detail = kwargs.get("coder_error_detail")
            f2p = kwargs.get("f2p_passed", False)
            p2p = kwargs.get("p2p_passed", False)
            patch_val = kwargs.get("patch_valid", False)
            patch_app = kwargs.get("patch_applied", False)

            cat, expl = FailureDisambiguator.classify(
                patch_valid=patch_val,
                patch_applied=patch_app,
                coder_error_code=coder_err,
                coder_error_msg=coder_detail,
                f2p_passed=f2p,
                p2p_passed=p2p,
            )
            if cat in GranularFailureType.__members__:
                det_res.granular_failure_type = GranularFailureType[cat]
            elif not patch_val:
                det_res.granular_failure_type = GranularFailureType.PATCH_INVALID
            elif not patch_app:
                det_res.granular_failure_type = GranularFailureType.PATCH_APPLICATION_FAILED
            else:
                det_res.granular_failure_type = GranularFailureType.F2P_FAILURE

            det_res.objective_failure_evidence["disambiguated_failure_type"] = cat
            det_res.objective_failure_evidence["disambiguated_explanation"] = expl
            det_res.evidence_reasons.append(f"Disambiguated root cause: [{cat}] {expl}")
            return det_res

        try:
            ew.CoderAgent.execute = coder_execute_hook
            ew.SupervisorAgent.execute = supervised_execute_hook
            ew.FailureDetector.evaluate = fd_eval_hook
            return super().run()
        finally:
            ew.CoderAgent.execute = original_coder_execute
            ew.SupervisorAgent.execute = original_sup_execute
            ew.FailureDetector.evaluate = original_fd_eval


