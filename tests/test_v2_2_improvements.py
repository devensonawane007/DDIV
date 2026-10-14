"""Tests for DDIV v2.2 improvements (Indentation normalizer, Placeholder safety, Anti-repetition, Failure disambiguation)."""

import ast
from pathlib import Path
import pytest

from scripts.demo_patch_builder import DemoPatchBuilder
from evaluation.patch_builder import CodeModification
from evaluation.patch_manager import PatchManager
from scripts.v2_2_recovery_manager import (
    ProposalHistory,
    FailureDisambiguator,
)

SAMPLE_FILE = """class Runner:
    def process(self, item):
        total = 0
        if item is not None:
            total += 1
        return total
"""


def test_insert_after_header_block_indentation(tmp_path):
    """insert_after under 'def ...:' or 'if ...:' must indent inserted body to anchor + 4 spaces."""
    f = tmp_path / "mod.py"
    f.write_text(SAMPLE_FILE, encoding="utf-8")
    builder = DemoPatchBuilder()

    # Coder provides unindented snippet for inside process()
    mods = [
        CodeModification(
            path="mod.py",
            operation="insert_after",
            anchor="def process(self, item):",
            code="if item == 0:\n    return 0",
            reason="Early return guard",
        )
    ]
    res = builder.build_patch(mods, base_dir=tmp_path)
    assert res.success is True, res.error_message

    pmgr = PatchManager()
    apply_res = pmgr.apply_patch(tmp_path, res.unified_diff)
    assert apply_res.is_success is True

    patched = f.read_text(encoding="utf-8")
    ast.parse(patched)
    # def has 4 spaces, so body must have 8 spaces
    assert "        if item == 0:\n            return 0" in patched


def test_insert_after_statement_indentation(tmp_path):
    """insert_after under an existing statement must match that statement's indentation level."""
    f = tmp_path / "mod.py"
    f.write_text(SAMPLE_FILE, encoding="utf-8")
    builder = DemoPatchBuilder()

    # Coder provides snippet with arbitrary leading newline and spaces
    mods = [
        CodeModification(
            path="mod.py",
            operation="insert_after",
            anchor="total += 1",
            code="\n    print(f'Counted: {total}')",
            reason="Log total",
        )
    ]
    res = builder.build_patch(mods, base_dir=tmp_path)
    assert res.success is True, res.error_message

    pmgr = PatchManager()
    apply_res = pmgr.apply_patch(tmp_path, res.unified_diff)
    assert apply_res.is_success is True

    patched = f.read_text(encoding="utf-8")
    ast.parse(patched)
    # total += 1 has 12 spaces, so inserted print must have 12 spaces
    assert "            print(f'Counted: {total}')" in patched


def test_placeholder_path_rejected_when_not_unique_or_nonexistent(tmp_path):
    """Placeholder path like path/to/similar_checker.py must be rejected with FILE_NOT_FOUND when not in workspace."""
    f = tmp_path / "similar.py"
    f.write_text("x = 1\n", encoding="utf-8")
    builder = DemoPatchBuilder()

    mods = [
        CodeModification(
            path="path/to/similar_checker.py",
            operation="replace",
            anchor="x = 1",
            code="x = 2",
            reason="Test placeholder",
        )
    ]
    res = builder.build_patch(mods, base_dir=tmp_path)
    assert res.success is False
    assert res.error_category == "FILE_NOT_FOUND"
    assert "Target file not found in workspace" in res.error_message


def test_placeholder_path_resolved_when_exact_filename_uniquely_exists(tmp_path):
    """Placeholder path like path/to/run.py resolves safely IF and ONLY IF run.py uniquely exists."""
    sub = tmp_path / "pylint" / "lint"
    sub.mkdir(parents=True)
    f = sub / "run.py"
    f.write_text("def run():\n    pass\n", encoding="utf-8")
    builder = DemoPatchBuilder()

    mods = [
        CodeModification(
            path="path/to/run.py",
            operation="replace",
            anchor="pass",
            code="return 1",
            reason="Test unique resolve",
        )
    ]
    res = builder.build_patch(mods, base_dir=tmp_path)
    assert res.success is True, res.error_message
    assert "a/pylint/lint/run.py" in res.unified_diff


def test_anti_repetition_tracking():
    """ProposalHistory must detect byte-for-byte and whitespace-normalized duplicate proposals."""
    hist = ProposalHistory()
    hist.record_attempt(
        attempt=1,
        path="pylint/lint/run.py",
        operation="replace",
        anchor="return avail_cpu",
        code="return avail_cpu or 1",
        error_category="F2P_FAILURE",
        error_detail="Tests failed",
    )

    # Identical with slight whitespace variations in code
    match_attempt = hist.is_repeated(
        path="pylint/lint/run.py",
        operation="replace",
        anchor="return  avail_cpu",
        code="\n  return avail_cpu or 1\n",
    )
    assert match_attempt == 1

    # Novel proposal
    novel_attempt = hist.is_repeated(
        path="pylint/lint/run.py",
        operation="replace",
        anchor="avail_cpu = int(cpu_quota / cpu_period)",
        code="avail_cpu = max(int(cpu_quota / cpu_period), 1)",
    )
    assert novel_attempt is None


def test_failure_disambiguator():
    """Disambiguator must cleanly distinguish syntax errors, missing files, anchor failures, and regressions."""
    # 1. Syntax Error
    cat1, _ = FailureDisambiguator.classify(
        patch_valid=False,
        patch_applied=False,
        pb_error_category="SYNTAX_ERROR",
        pb_error_message="Patched file failed Python AST syntax verification at line 57: unexpected indent",
    )
    assert cat1 == "SYNTAX_ERROR_INDENTATION"

    # 2. File Not Found
    cat2, _ = FailureDisambiguator.classify(
        patch_valid=False,
        patch_applied=False,
        pb_error_category="FILE_NOT_FOUND",
        pb_error_message="Target file not found in workspace: sympy/matrices/expressions/matrix.py",
    )
    assert cat2 == "TARGET_FILE_NOT_FOUND"

    # 3. Anchor Not Found
    cat3, _ = FailureDisambiguator.classify(
        patch_valid=False,
        patch_applied=False,
        pb_error_category="ANCHOR_NOT_FOUND",
        pb_error_message="Anchor not found in 'sympy/matrices/matrices.py': def hermite_normal_form",
    )
    assert cat3 == "ANCHOR_NOT_FOUND"

    # 4. Repeated Patch
    cat4, _ = FailureDisambiguator.classify(
        patch_valid=True,
        patch_applied=True,
        is_repeated=True,
    )
    assert cat4 == "REPEATED_PATCH_CYCLE"

    # 5. Regression
    cat5, _ = FailureDisambiguator.classify(
        patch_valid=True,
        patch_applied=True,
        f2p_passed=True,
        p2p_passed=False,
    )
    assert cat5 == "P2P_REGRESSION"


def test_format_test_counts_reporting_unapplied_patch_distinction():
    """Verify that when a patch fails application, F2P/P2P denominators distinguish unexecuted tests from 0-test tasks."""
    # Case 1: Patch application failed (tests were not executed)
    eval_failed_apply = {
        "candidate_patch_applied": False,
        "verdict": "UNRESOLVED_INTERNALLY (Candidate patch application failed)",
        "fail_to_pass_results": {},
        "pass_to_pass_results": {},
    }
    f2p_str, p2p_str = FailureDisambiguator.format_test_counts(
        eval_failed_apply,
        ground_truth_f2p_total=1,
        ground_truth_p2p_total=17,
    )
    assert f2p_str == "0/1 (Not Run - Apply Failed)"
    assert p2p_str == "0/17 (Not Run - Apply Failed)"
    # Must NOT report misleading '0/0'
    assert "0/0" not in f2p_str
    assert "0/0" not in p2p_str

    # Case 2: Tests executed normally (e.g. 1 F2P failed, 8/8 P2P passed)
    eval_executed = {
        "candidate_patch_applied": True,
        "verdict": "UNRESOLVED_INTERNALLY (FAIL_TO_PASS tests failed)",
        "fail_to_pass_results": {"test_foo": False},
        "pass_to_pass_results": {f"test_p2p_{i}": True for i in range(8)},
    }
    f2p_str2, p2p_str2 = FailureDisambiguator.format_test_counts(
        eval_executed,
        ground_truth_f2p_total=1,
        ground_truth_p2p_total=8,
    )
    assert f2p_str2 == "0/1"
    assert p2p_str2 == "8/8"


from core.conditions import ExperimentCondition
from core.experiment_record import ExperimentConditionRecord, ConditionJobStatus
import core.experiment_worker as ew
from scripts.v2_2_recovery_manager import V22SupervisedWorker
from agents.base import AgentInputMetadata, AgentExecutionResult
from agents.supervisor import SupervisorDecision


def test_v22_supervised_worker_restoration_on_exception(tmp_path, monkeypatch):
    """Guaranteed try/finally restoration of agent class methods when worker raises an unhandled exception."""
    orig_coder = ew.CoderAgent.execute
    orig_sup = ew.SupervisorAgent.execute
    orig_fd = ew.FailureDetector.evaluate

    worker = V22SupervisedWorker(
        experiment_id="test_exp",
        task_id="pallets__flask-5014",
        condition="full_ddiv",
        provider="mock",
        workspace_root=tmp_path / "ws",
    )

    def mock_crashing_run(self):
        # Verify methods ARE hooked while running inside try block
        assert ew.CoderAgent.execute is not orig_coder
        assert ew.SupervisorAgent.execute is not orig_sup
        assert ew.FailureDetector.evaluate is not orig_fd
        raise RuntimeError("Deliberate unhandled failure during repair run")

    monkeypatch.setattr(ew.ExperimentWorker, "run", mock_crashing_run)

    with pytest.raises(RuntimeError, match="Deliberate unhandled failure"):
        worker.run()

    # Verify that all class methods are restored to their exact original references
    assert ew.CoderAgent.execute is orig_coder
    assert ew.SupervisorAgent.execute is orig_sup
    assert ew.FailureDetector.evaluate is orig_fd


def test_v22_supervised_worker_condition_scoping_and_isolation(tmp_path, monkeypatch):
    """BASELINE and RETRY_ONLY do not invoke recovery manager, hook methods, or leak state."""
    orig_coder = ew.CoderAgent.execute
    orig_sup = ew.SupervisorAgent.execute
    orig_fd = ew.FailureDetector.evaluate

    captured_in_run = []

    def mock_safe_run(self):
        captured_in_run.append({
            "condition": self.condition,
            "coder_is_original": (ew.CoderAgent.execute is orig_coder),
            "sup_is_original": (ew.SupervisorAgent.execute is orig_sup),
            "fd_is_original": (ew.FailureDetector.evaluate is orig_fd),
        })
        return ExperimentConditionRecord(
            experiment_id=self.experiment_id,
            task_id=self.task_id,
            condition=self.condition.value,
            status=ConditionJobStatus.COMPLETED,
            resolved=False,
            workflow_completed=True,
            attempts=1,
            execution_duration_seconds=1.0,
        )

    monkeypatch.setattr(ew.ExperimentWorker, "run", mock_safe_run)

    # 1. Run BASELINE: must not hook any methods
    worker_base = V22SupervisedWorker(
        experiment_id="test_exp",
        task_id="pallets__flask-5014",
        condition="baseline",
        provider="mock",
        workspace_root=tmp_path / "ws_base",
    )
    rec_base = worker_base.run()
    assert rec_base.status == ConditionJobStatus.COMPLETED
    assert len(captured_in_run) == 1
    assert captured_in_run[0]["coder_is_original"] is True
    assert captured_in_run[0]["sup_is_original"] is True
    assert captured_in_run[0]["fd_is_original"] is True

    # 2. Run RETRY_ONLY: must not hook any methods
    worker_retry = V22SupervisedWorker(
        experiment_id="test_exp",
        task_id="pallets__flask-5014",
        condition="retry_only",
        provider="mock",
        workspace_root=tmp_path / "ws_retry",
    )
    rec_retry = worker_retry.run()
    assert rec_retry.status == ConditionJobStatus.COMPLETED
    assert len(captured_in_run) == 2
    assert captured_in_run[1]["coder_is_original"] is True
    assert captured_in_run[1]["sup_is_original"] is True
    assert captured_in_run[1]["fd_is_original"] is True

    # 3. Verify ProposalHistory isolation: new workers have empty history
    assert len(worker_base.proposal_history.records) == 0
    assert len(worker_retry.proposal_history.records) == 0
    assert ew.CoderAgent.execute is orig_coder


def test_v22_supervised_worker_feedback_delivery_to_next_coder_prompt(tmp_path, monkeypatch):
    """Negative constraints from ProposalHistory are injected into Supervisor avoid instructions and reach the next Coder prompt."""
    orig_coder = ew.CoderAgent.execute
    orig_sup = ew.SupervisorAgent.execute
    orig_fd = ew.FailureDetector.evaluate

    worker = V22SupervisedWorker(
        experiment_id="test_exp",
        task_id="pallets__flask-5014",
        condition="full_ddiv",
        provider="mock",
        workspace_root=tmp_path / "ws_ddiv",
    )

    received_coder_inputs = []

    def mock_run_with_feedback(self):
        meta1 = AgentInputMetadata(task_id=self.task_id, run_id="r1", attempt=1)
        meta2 = AgentInputMetadata(task_id=self.task_id, run_id="r2", attempt=2)

        # Attempt 1: Coder generates modification that fails
        coder = ew.CoderAgent(None)
        c_in_1 = {"issue": "bug", "avoid_previous_mistake": ""}
        received_coder_inputs.append(c_in_1)

        # Call the hooked coder.execute
        coder_res1 = ew.CoderAgent.execute(
            coder,
            c_in_1,
            meta1,
        )

        # Mock supervisor execution for attempt 1 failure
        sup = ew.SupervisorAgent(None)
        sup_in_1 = {"task_id": self.task_id, "attempt": 1}
        sup_res1 = ew.SupervisorAgent.execute(sup, sup_in_1, meta1)

        # Verify Supervisor received negative constraints
        assert sup_res1.success is True
        avoid_text = sup_res1.output.avoid_previous_mistake
        assert "CRITICAL DIRECTIVE: DO NOT REPEAT PREVIOUS FAILED PROPOSALS" in avoid_text
        assert "Attempt 1: Modified 'src/flask/blueprints.py'" in avoid_text
        assert "You MUST NOT generate this identical modification again." in avoid_text

        # Attempt 2: Worker passes supervisor's avoid instructions into next coder prompt
        c_in_2 = {
            "issue": "bug",
            "avoid_previous_mistake": avoid_text,
        }
        received_coder_inputs.append(c_in_2)

        coder_res2 = ew.CoderAgent.execute(coder, c_in_2, meta2)

        return ExperimentConditionRecord(
            experiment_id=self.experiment_id,
            task_id=self.task_id,
            condition=self.condition.value,
            status=ConditionJobStatus.COMPLETED,
            resolved=False,
            workflow_completed=True,
            attempts=2,
            execution_duration_seconds=2.0,
        )

    from pydantic import BaseModel
    class MockCoderOut(BaseModel):
        modifications: list = []
        patch: str = ""
        modified_files: list = []
        reasoning_summary: str = ""
        confidence: float = 1.0

    mod1 = CodeModification(
        path="src/flask/blueprints.py",
        operation="replace",
        anchor="root_path=root_path,",
        code="        if not name: raise ValueError()",
        reason="Validation guard",
    )
    def dummy_orig_coder(coder_self, c_in, meta):
        return AgentExecutionResult(
            task_id=meta.task_id,
            run_id=meta.run_id,
            agent_id="Coder",
            attempt=meta.attempt,
            success=True,
            output=MockCoderOut(modifications=[mod1]),
        )

    def dummy_orig_sup(sup_self, s_in, meta):
        return AgentExecutionResult(
            task_id=meta.task_id,
            run_id=meta.run_id,
            agent_id="Supervisor",
            attempt=meta.attempt,
            success=True,
            output=SupervisorDecision(
                should_retry=True,
                detected_failure="F2",
                diagnosis="Syntax/logic error",
                recovery_strategy="A2",
                intervention_instructions="Fix logic",
                avoid_previous_mistake="Initial avoid hint",
                confidence=0.9,
            ),
        )

    monkeypatch.setattr(ew.CoderAgent, "execute", dummy_orig_coder)
    monkeypatch.setattr(ew.SupervisorAgent, "execute", dummy_orig_sup)
    monkeypatch.setattr(ew.ExperimentWorker, "run", mock_run_with_feedback)

    rec = worker.run()
    assert rec.status == ConditionJobStatus.COMPLETED

    # Verify attempt 2 received negative constraint
    assert len(received_coder_inputs) == 2
    assert received_coder_inputs[0]["avoid_previous_mistake"] == ""
    assert "Attempt 1: Modified 'src/flask/blueprints.py'" in received_coder_inputs[1]["avoid_previous_mistake"]
    assert "You MUST NOT generate this identical modification again." in received_coder_inputs[1]["avoid_previous_mistake"]

    # Verify restoration
    assert ew.CoderAgent.execute is dummy_orig_coder
    assert ew.SupervisorAgent.execute is dummy_orig_sup

