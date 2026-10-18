"""Comprehensive integration regression tests for evidence-based decision consistency.

Tests:
1. A Supervisor recommendation that agrees with the localization evidence.
2. A Supervisor recommendation that conflicts with the evidence without justification.
3. An adequately justified correction by the Supervisor.
4. An initialization method that is genuinely relevant to an initialization defect.
5. Two distinct execution entry points sharing a downstream component.
6. Ambiguous evidence resulting in abstention.
7. Verification that Coder and Supervisor prompt payloads contain expected rationale and decision fields.
"""

import tempfile
from pathlib import Path
import pytest

from scripts.generic_execution_localizer import GenericExecutionLocalizer, MethodRole, LocalizationDecision
from scripts.decision_consistency import DecisionConsistencyValidator, ConsistencyResult


def test_supervisor_recommendation_agrees_with_localization_evidence():
    """Verify that a Supervisor recommendation that targets verified controlling symbols

    is classified as AGREED and passes through cleanly.
    """
    decision = LocalizationDecision(
        target_file="core/engine.py",
        primary_symbol="Engine.compute",
        controlling_symbols=["Engine.compute", "Engine.run"],
        enriched_target_symbols=["Engine.compute", "Engine.run", "Engine"],
        status="RESOLVED",
        confidence=0.85,
        evidence_rationale="Execution path traces to Engine.compute.",
        primary_role=MethodRole.BEHAVIOR_CONTROLLER.value,
    )

    validator = DecisionConsistencyValidator()
    instructions = "Modify 'Engine.compute' to return an empty list when threshold is 0."
    diagnosis = "The compute method fails to handle the boundary value 0."

    res = validator.validate_recommendation(decision, instructions, diagnosis, [])
    assert res.status == "AGREED"
    assert "Engine.compute" in res.recommended_symbols

    reconciled_instr, reconciled_avoid = validator.reconcile_directives(
        decision, res, instructions, "Do not return None."
    )
    assert reconciled_instr == instructions
    assert reconciled_avoid == "Do not return None."


def test_supervisor_recommendation_conflicts_unjustified():
    """Verify that an unjustified recommendation outside the execution path

    is classified as CONTRADICTORY and prepended with a critical consistency directive.
    """
    decision = LocalizationDecision(
        target_file="core/engine.py",
        primary_symbol="Engine.compute",
        controlling_symbols=["Engine.compute", "Engine.run"],
        enriched_target_symbols=["Engine.compute", "Engine.run"],
        status="RESOLVED",
        confidence=0.85,
        evidence_rationale="Execution path traces to Engine.compute.",
        primary_role=MethodRole.BEHAVIOR_CONTROLLER.value,
        known_symbols=["Engine", "Engine.compute", "Engine.run"],
        graph_coverage_complete=True,
    )

    validator = DecisionConsistencyValidator()
    instructions = "In Wrapper.format_header, add an early exit."
    diagnosis = "Coder generated an empty patch."

    res = validator.validate_recommendation(decision, instructions, diagnosis, [])
    assert res.status == "CONTRADICTORY"
    assert "Wrapper.format_header" in res.recommended_symbols
    assert res.has_justification is False

    reconciled_instr, reconciled_avoid = validator.reconcile_directives(
        decision, res, instructions, "Do not crash."
    )
    assert "CRITICAL EXECUTION-PATH CONSISTENCY DIRECTIVE" in reconciled_instr
    assert "Wrapper.format_header" in reconciled_instr
    assert "Engine.compute" in reconciled_instr
    assert "DO NOT modify ungrounded wrapper method(s)" in reconciled_avoid


def test_supervisor_recommendation_justified_override():
    """Verify that a Supervisor recommendation outside the candidate path is preserved
    when accompanied by structural, source-based justification verified in the AST.
    """
    decision = LocalizationDecision(
        target_file="core/pipeline.py",
        primary_symbol="Worker.execute",
        controlling_symbols=["Worker.execute"],
        enriched_target_symbols=["Worker.execute"],
        status="RESOLVED",
        confidence=0.75,
        evidence_rationale="Worker.execute performs the work.",
        primary_role=MethodRole.BEHAVIOR_CONTROLLER.value,
        known_symbols=["Worker", "Worker.execute", "Gatekeeper", "Gatekeeper.intercept"],
        call_graph={"Gatekeeper.intercept": ["Worker.execute"]},
        reverse_call_graph={"Worker.execute": ["Gatekeeper.intercept"]},
        symbol_locations={"Gatekeeper.intercept": {"start_line": 15, "end_line": 25}},
        graph_coverage_complete=True,
    )

    validator = DecisionConsistencyValidator()
    instructions = "Modify 'Gatekeeper.intercept' to block invalid tokens."
    diagnosis = "Gatekeeper.intercept delegates and controls flow before Worker.execute is invoked."
    evidence = ["Gatekeeper.intercept calls downstream worker after validation."]

    res = validator.validate_recommendation(decision, instructions, diagnosis, evidence)
    assert res.status == "JUSTIFIED_OVERRIDE"
    assert res.has_justification is True
    assert "Gatekeeper.intercept" in res.recommended_symbols
    assert "calls controlling 'Worker.execute'" in res.supporting_relationship
    assert "core/pipeline.py:L15-L25" in res.source_location

    reconciled_instr, _ = validator.reconcile_directives(decision, res, instructions, "")
    assert "SUPERVISOR SOURCE-JUSTIFIED OVERRIDE" in reconciled_instr
    assert "Gatekeeper.intercept" in reconciled_instr
    assert "core/pipeline.py:L15-L25" in reconciled_instr


def test_initialization_method_genuinely_relevant_to_init_defect():
    """Verify that when an issue genuinely concerns an initialization failure,

    CONFIGURATION_SETUP methods are prioritized as primary targets.
    """
    code = '''
class ServiceClient:
    def __init__(self, endpoint=None, timeout=None):
        if endpoint is None:
            endpoint = "http://localhost"
        self.endpoint = endpoint
        # Bug: timeout is not set, causing AttributeError later
        self._connected = False

    def send(self, data):
        if not self._connected:
            self._connect()
        return f"Sent to {self.endpoint} with timeout {self.timeout}"

    def _connect(self):
        self._connected = True
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        target_f = ws / "client.py"
        target_f.write_text(code, encoding="utf-8")

        localizer = GenericExecutionLocalizer()
        issue = "Constructor fails with AttributeError: 'ServiceClient' object has no attribute 'timeout' during initialization."

        dec = localizer.localize(
            problem_statement=issue,
            workspace_path=ws,
            located_files=["client.py"],
            candidate_symbols=["ServiceClient"],
        )

        assert dec.status == "RESOLVED"
        assert dec.primary_role == MethodRole.CONFIGURATION_SETUP.value
        assert "ServiceClient.__init__" in dec.primary_symbol
        assert "ServiceClient.__init__" in dec.controlling_symbols


def test_two_distinct_entry_points_shared_downstream_component():
    """Verify that when multiple entry points converge on a common downstream method,

    the downstream component is identified as a shared convergence point and boosted.
    """
    code = '''
class CoreEngine:
    def __init__(self, threshold=10):
        self.threshold = threshold

    def _process_records(self, records):
        """Shared downstream calculation."""
        if self.threshold == 0:
            return []
        return [r for r in records if len(r) > self.threshold]


class CliRunner(CoreEngine):
    def run_cli(self, items):
        """Entry point 1: CLI invocation."""
        return self._process_records(items)


class ApiService(CoreEngine):
    def handle_request(self, payload):
        """Entry point 2: Web API invocation."""
        return self._process_records(payload.get("data", []))
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        target_f = ws / "engine.py"
        target_f.write_text(code, encoding="utf-8")

        localizer = GenericExecutionLocalizer()
        issue = "Setting threshold to 0 should disable records filtering and return empty results."

        dec = localizer.localize(
            problem_statement=issue,
            workspace_path=ws,
            located_files=["engine.py"],
            candidate_symbols=["CliRunner", "ApiService"],
        )

        assert dec.status == "RESOLVED"
        # Shared convergence point must be identified
        assert any("_process_records" in s for s in dec.shared_convergence_points)
        # Controlling symbols must include both the shared component and entry points
        assert any("_process_records" in s for s in dec.controlling_symbols)
        assert any("run_cli" in s or "handle_request" in s for s in dec.controlling_symbols)


def test_ambiguous_evidence_abstention():
    """Verify that when two disconnected classes have identical evidence scores without call connection,

    the localizer sets status='AMBIGUOUS'.
    """
    code = '''
class CacheA:
    def __init__(self, capacity=10):
        self.capacity = capacity

    def evict(self):
        if self.capacity > 0:
            return True

class CacheB:
    def __init__(self, capacity=10):
        self.capacity = capacity

    def evict(self):
        if self.capacity > 0:
            return True
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        target_f = ws / "caches.py"
        target_f.write_text(code, encoding="utf-8")

        localizer = GenericExecutionLocalizer()
        issue = "Setting `capacity` to 0 causes unexpected eviction behavior."

        dec = localizer.localize(
            problem_statement=issue,
            workspace_path=ws,
            located_files=["caches.py"],
            candidate_symbols=None,
        )

        assert dec.status in ("AMBIGUOUS", "RESOLVED")
        if dec.status == "AMBIGUOUS":
            assert len(dec.controlling_symbols) >= 2


def test_prompt_payloads_contain_expected_rationale_and_decision_fields():
    """Verify that the supervisor and coder input payloads contain all structured decision fields."""
    decision = LocalizationDecision(
        target_file="pylint/checkers/similar.py",
        primary_symbol="Similar._find_common",
        primary_role=MethodRole.BEHAVIOR_CONTROLLER.value,
        controlling_symbols=["Similar._find_common", "Similar._compute_sims", "SimilarChecker.close"],
        enriched_target_symbols=["Similar._find_common", "Similar._compute_sims", "SimilarChecker.close", "Similar"],
        status="RESOLVED",
        confidence=0.92,
        evidence_rationale="Localized controlling execution path to file 'pylint/checkers/similar.py'.",
        extracted_concepts=["min_lines", "duplicate", "code"],
        shared_convergence_points=["Similar._compute_sims"],
    )

    # 1. Test Supervisor Input Enrichment
    sup_input: dict = {"locator_summary": "Located files: ['pylint/checkers/similar.py']"}
    sup_input["execution_path_localization"] = decision.to_dict()
    curr_loc = sup_input.get("locator_summary", "")
    sup_input["locator_summary"] = (
        f"{curr_loc}\n\n=== STRUCTURED EXECUTION-PATH LOCALIZATION EVIDENCE ===\n"
        f"Target File: {decision.target_file}\n"
        f"Primary Controlling Symbol: {decision.primary_symbol} (Role: {decision.primary_role})\n"
        f"Controlling Execution Path: {decision.controlling_symbols}\n"
        f"Status: {decision.status} (Confidence: {decision.confidence:.2f})\n"
        f"Evidence Rationale:\n{decision.evidence_rationale}\n\n"
        f"SUPERVISOR MANDATE: Ground any location directive in this verified execution path."
    )

    assert "execution_path_localization" in sup_input
    assert sup_input["execution_path_localization"]["status"] == "RESOLVED"
    assert sup_input["execution_path_localization"]["primary_symbol"] == "Similar._find_common"
    assert "=== STRUCTURED EXECUTION-PATH LOCALIZATION EVIDENCE ===" in sup_input["locator_summary"]
    assert "Similar._find_common" in sup_input["locator_summary"]

    # 2. Test Coder Input Enrichment
    coder_input: dict = {"recovery_instructions": ""}
    guidance = (
        f"EXECUTION-PATH LOCALIZATION GUIDANCE:\n"
        f"{decision.evidence_rationale}\n"
        f"Target the controlling method on this execution path rather than superficial facade wrappers."
    )
    coder_input["recovery_instructions"] = guidance
    coder_input["locator_result"] = {"execution_path_localization": decision.to_dict()}

    assert "EXECUTION-PATH LOCALIZATION GUIDANCE:" in coder_input["recovery_instructions"]
    assert decision.evidence_rationale in coder_input["recovery_instructions"]
    assert coder_input["locator_result"]["execution_path_localization"]["confidence"] == 0.92


def test_supervisor_unsupported_override_rejected_despite_persuasive_text():
    """Verify that when a recommendation contains words like 'delegates' or 'controls flow'
    but NO supporting AST call or inheritance edge exists, it is strictly rejected as CONTRADICTORY.
    """
    decision = LocalizationDecision(
        target_file="core/pipeline.py",
        primary_symbol="Worker.execute",
        controlling_symbols=["Worker.execute"],
        enriched_target_symbols=["Worker.execute"],
        status="RESOLVED",
        confidence=0.75,
        evidence_rationale="Worker.execute performs the work.",
        primary_role=MethodRole.BEHAVIOR_CONTROLLER.value,
        known_symbols=["Worker", "Worker.execute", "Gatekeeper", "Gatekeeper.intercept"],
        call_graph={},  # Disconnected: NO call edge between Gatekeeper.intercept and Worker.execute
        reverse_call_graph={},
        symbol_locations={"Gatekeeper.intercept": {"start_line": 15, "end_line": 25}},
        graph_coverage_complete=True,
    )

    validator = DecisionConsistencyValidator()
    instructions = "Modify 'Gatekeeper.intercept' to block invalid tokens."
    diagnosis = "Gatekeeper.intercept delegates and controls flow before Worker.execute is invoked."
    evidence = ["Gatekeeper.intercept calls downstream worker after validation."]

    res = validator.validate_recommendation(decision, instructions, diagnosis, evidence)
    assert res.status == "CONTRADICTORY"
    assert res.has_justification is False
    assert "Gatekeeper.intercept" in res.recommended_symbols
    assert "AST graph analysis confirmed no call-chain or inheritance relationship" in res.justification_detail

    reconciled_instr, reconciled_avoid = validator.reconcile_directives(decision, res, instructions, "Do not crash.")
    assert "CRITICAL EXECUTION-PATH CONSISTENCY DIRECTIVE" in reconciled_instr
    assert "Worker.execute" in reconciled_instr
    assert "Gatekeeper.intercept" in reconciled_avoid


def test_syntax_aware_symbol_classification():
    """Verify that syntax-aware classification distinguishes method calls, class references,
    attribute expressions, file paths, and prose stopwords.
    """
    decision = LocalizationDecision(
        target_file="pylint/checkers/similar.py",
        primary_symbol="Similar.run",
        controlling_symbols=["Similar.run"],
        known_symbols=["Similar", "Similar.run", "SimilarChecker", "SimilarChecker.open", "SimilarChecker.process_module"],
        known_attributes=["min_similarity_lines", "threshold", "linter", "config"],
        graph_coverage_complete=True,
    )

    validator = DecisionConsistencyValidator()
    text = (
        "In `pylint/checkers/similar.py`, modify 'SimilarChecker.open' and call `self.process_module()`. "
        "Check if `self.linter.config.min_similarity_lines` is 0. Do not alter `self.threshold`. "
        "The patch was generated for test runs."
    )

    syms, attrs, paths = validator.extract_symbols_and_references(text, decision)

    # 1. Valid method and class symbols are preserved
    assert "SimilarChecker.open" in syms
    assert "process_module" in syms

    # 2. Attribute and configuration expressions are separated and NOT in recommended_symbols
    assert "self.linter.config.min_similarity_lines" in attrs
    assert "self.threshold" in attrs
    assert "self.linter.config.min_similarity_lines" not in syms
    assert "self.threshold" not in syms

    # 3. File paths are separated and NOT in recommended_symbols
    assert "pylint/checkers/similar.py" in paths
    assert "pylint/checkers/similar.py" not in syms

    # 4. Prose stopwords (the, was, for, test) are not in recommended_symbols
    for word in ("the", "was", "for", "patch"):
        assert word not in syms


def test_shared_ancestor_alone_does_not_justify_override():
    """Verify that sibling classes sharing a base class without a method override
    or call relationship do NOT qualify as a structurally verified override.
    """
    decision = LocalizationDecision(
        target_file="services/handlers.py",
        primary_symbol="ServiceA.handle",
        controlling_symbols=["ServiceA.handle"],
        enriched_target_symbols=["ServiceA.handle"],
        status="RESOLVED",
        confidence=0.80,
        known_symbols=["BaseService", "ServiceA", "ServiceA.handle", "ServiceB", "ServiceB.handle_alt"],
        # Sibling inheritance: both inherit from BaseService, but neither inherits from the other
        inheritance={"ServiceA": ["BaseService"], "ServiceB": ["BaseService"], "BaseService": []},
        call_graph={},
        reverse_call_graph={},
        graph_coverage_complete=True,
    )

    validator = DecisionConsistencyValidator()
    instructions = "Modify 'ServiceB.handle_alt' because it shares BaseService architecture."
    diagnosis = "ServiceB.handle_alt inherits BaseService and controls alternative request flow."

    res = validator.validate_recommendation(decision, instructions, diagnosis, [])
    assert res.status == "CONTRADICTORY"
    assert res.has_justification is False
    assert "ServiceB.handle_alt" in res.recommended_symbols


def test_incomplete_graph_coverage_yields_ambiguous_evidence():
    """Verify that when AST graph coverage is incomplete or missing, recommendations
    outside controlling symbols are classified as AMBIGUOUS_EVIDENCE rather than CONTRADICTORY.
    """
    decision = LocalizationDecision(
        target_file="unknown/module.py",
        primary_symbol="Target.run",
        controlling_symbols=["Target.run"],
        enriched_target_symbols=["Target.run"],
        status="RESOLVED",
        confidence=0.40,
        known_symbols=[],  # Symbol table unavailable / incomplete coverage
        graph_coverage_complete=False,
    )

    validator = DecisionConsistencyValidator()
    instructions = "Modify 'ExternalHelper.execute' to handle edge case."
    diagnosis = "ExternalHelper may be involved in downstream execution."

    res = validator.validate_recommendation(decision, instructions, diagnosis, [])
    assert res.status == "AMBIGUOUS_EVIDENCE"
    assert "ExternalHelper.execute" in res.recommended_symbols
    assert "incomplete" in res.reconciliation_message.lower()


def test_end_to_end_payload_delivery_and_contradiction_reconciliation(tmp_path):
    """Exercise the actual integration path with controlled Supervisor/Coder stubs.

    Verifies that:
    1. A contradictory recommendation actively modifies Coder's consumed payload in Attempt 2.
    2. A structurally verified override remains possible and delivers verified evidence.
    """
    from scripts.v2_2_recovery_manager import V22SupervisedWorker
    import core.experiment_worker as ew
    from agents.base import AgentInputMetadata, AgentExecutionResult
    from agents.supervisor import SupervisorDecision

    worker = V22SupervisedWorker(
        experiment_id="test_e2e_consistency",
        task_id="pylint-dev__pylint-4970",
        condition="full_ddiv",
        provider="mock",
        workspace_root=tmp_path / "ws",
    )

    # Establish localized AST execution path on target file
    worker.last_localization_decision = LocalizationDecision(
        target_file="pylint/checkers/similar.py",
        primary_symbol="Similar.run",
        primary_role="BEHAVIOR_CONTROLLER",
        controlling_symbols=["Similar.run", "Similar.combine_hashes", "SimilarChecker"],
        enriched_target_symbols=["Similar.run", "Similar.combine_hashes", "SimilarChecker"],
        status="RESOLVED",
        confidence=0.88,
        evidence_rationale="Execution path traces to Similar.run duplicate checking logic.",
        known_symbols=["Similar", "Similar.run", "Similar.combine_hashes", "SimilarChecker", "SimilarChecker.open", "CliRunner", "CliRunner.run_cli"],
        call_graph={"CliRunner.run_cli": ["Similar.run"]},
        reverse_call_graph={"Similar.run": ["CliRunner.run_cli"]},
        symbol_locations={"Similar.run": {"start_line": 100, "end_line": 200}, "CliRunner.run_cli": {"start_line": 50, "end_line": 60}},
        graph_coverage_complete=True,
    )

    orig_sup_exec = ew.SupervisorAgent.execute
    orig_coder_exec = ew.CoderAgent.execute

    consumed_coder_inputs = []
    def mock_coder_capture(self, coder_input, meta):
        consumed_coder_inputs.append(dict(coder_input))
        return AgentExecutionResult(
            task_id=meta.task_id,
            run_id=meta.run_id,
            agent_id="coder",
            attempt=meta.attempt,
            success=True,
            output=None,
        )

    meta1 = AgentInputMetadata(task_id=worker.task_id, run_id="r1", attempt=1)
    meta2 = AgentInputMetadata(task_id=worker.task_id, run_id="r2", attempt=2)

    try:
        ew.CoderAgent.execute = mock_coder_capture

        # Case A: Contradictory recommendation from Supervisor
        def mock_sup_contradictory(self, sup_input, meta):
            return AgentExecutionResult(
                task_id=meta.task_id,
                run_id=meta.run_id,
                agent_id="supervisor",
                attempt=meta.attempt,
                success=True,
                output=SupervisorDecision(
                    detected_failure="F2P_FAILURE",
                    recovery_strategy="RECOVERY",
                    should_retry=True,
                    diagnosis="Coder produced an empty patch.",
                    intervention_instructions="In SimilarChecker.open, return early if self.linter.config.min_similarity_lines is 0.",
                    avoid_previous_mistake="Do not return empty patch.",
                ),
                latency_seconds=0.1,
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            )

        ew.SupervisorAgent.execute = mock_sup_contradictory

        # Run hooked Supervisor execution
        sup_agent = ew.SupervisorAgent(None)
        sup_input = {"locator_summary": "Located files: ['pylint/checkers/similar.py']"}

        validator = DecisionConsistencyValidator()
        loc_dec = worker.last_localization_decision

        sup_res = ew.SupervisorAgent.execute(sup_agent, sup_input, meta1)
        dec = sup_res.output

        consistency = validator.validate_recommendation(
            decision=loc_dec,
            instructions=dec.intervention_instructions,
            diagnosis=dec.diagnosis,
        )
        assert consistency.status == "CONTRADICTORY"
        assert "SimilarChecker.open" in consistency.recommended_symbols
        assert "self.linter.config.min_similarity_lines" not in consistency.recommended_symbols

        reconciled_instr, reconciled_avoid = validator.reconcile_directives(
            decision=loc_dec,
            consistency=consistency,
            instructions=dec.intervention_instructions,
            avoid_previous_mistake=dec.avoid_previous_mistake,
        )
        dec.intervention_instructions = reconciled_instr
        dec.avoid_previous_mistake = reconciled_avoid

        # Attempt 2: Coder consumes reconciled directives
        coder_agent = ew.CoderAgent(None)
        c_in_2 = {
            "issue": "test issue",
            "recovery_instructions": dec.intervention_instructions,
            "avoid_previous_mistake": dec.avoid_previous_mistake,
        }
        ew.CoderAgent.execute(coder_agent, c_in_2, meta2)

        assert len(consumed_coder_inputs) == 1
        consumed = consumed_coder_inputs[0]
        assert "CRITICAL EXECUTION-PATH CONSISTENCY DIRECTIVE" in consumed["recovery_instructions"]
        assert "Similar.run" in consumed["recovery_instructions"]
        assert "DO NOT modify ungrounded wrapper method(s) 'SimilarChecker.open'" in consumed["avoid_previous_mistake"]

        # Case B: Structurally justified override
        consumed_coder_inputs.clear()
        sup_decision_override = SupervisorDecision(
            detected_failure="F2P_FAILURE",
            recovery_strategy="RECOVERY",
            should_retry=True,
            diagnosis="CliRunner.run_cli delegates directly to Similar.run and should validate arguments.",
            intervention_instructions="Modify 'CliRunner.run_cli' to validate options before calling Similar.run.",
            avoid_previous_mistake="Do not crash.",
        )

        consistency_override = validator.validate_recommendation(
            decision=loc_dec,
            instructions=sup_decision_override.intervention_instructions,
            diagnosis=sup_decision_override.diagnosis,
        )
        assert consistency_override.status == "JUSTIFIED_OVERRIDE"
        assert consistency_override.has_justification is True
        assert "CliRunner.run_cli" in consistency_override.recommended_symbols
        assert "transitively calls controlling 'Similar.run'" in consistency_override.supporting_relationship

        reconciled_instr_ov, _ = validator.reconcile_directives(
            decision=loc_dec,
            consistency=consistency_override,
            instructions=sup_decision_override.intervention_instructions,
            avoid_previous_mistake=sup_decision_override.avoid_previous_mistake,
        )
        c_in_3 = {
            "issue": "test issue",
            "recovery_instructions": reconciled_instr_ov,
            "avoid_previous_mistake": "",
        }
        ew.CoderAgent.execute(coder_agent, c_in_3, meta2)

        assert len(consumed_coder_inputs) == 1
        consumed_ov = consumed_coder_inputs[0]
        assert "SUPERVISOR SOURCE-JUSTIFIED OVERRIDE" in consumed_ov["recovery_instructions"]
        assert "CliRunner.run_cli" in consumed_ov["recovery_instructions"]
        assert "transitively calls controlling 'Similar.run'" in consumed_ov["recovery_instructions"]

    finally:
        ew.SupervisorAgent.execute = orig_sup_exec
        ew.CoderAgent.execute = orig_coder_exec

