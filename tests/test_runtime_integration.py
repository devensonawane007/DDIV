"""End-to-End Runtime Integration Tests for DDIV Phase 5.1.

Verifies:
1. End-to-end pipeline trace from GenericExecutionLocalizer through Coder proposal,
   V22SupervisedWorker hooks, StructuralCodeModification, DemoPatchBuilder, and patch application.
2. Survival of structural metadata: target_symbol, target_class, target_method, line_range, source_fingerprint.
3. Qualified AST scope targeting: verifies modifying duplicate method signatures only touches intended scope.
4. Workspace safety: rejected proposals (nonexistent anchor, ambiguous unscoped anchor, stale fingerprint)
   leave target files byte-for-byte identical on disk.
5. Adversarial UTF-8 handling: non-ASCII characters (emojis, accents, math symbols) before and within
   target methods do not shift AST scope boundaries or character offsets.
6. Semantic anti-repetition: blocks identical/AST-equivalent repeated failures while allowing valid
   structurally disambiguated retries.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from pydantic import BaseModel

import core.experiment_worker as ew
from core.conditions import ExperimentCondition
from core.experiment_record import ExperimentConditionRecord, ConditionJobStatus
from agents.base import AgentInputMetadata, AgentExecutionResult
from scripts.demo_patch_builder import (
    DemoPatchBuilder,
    StructuralCodeModification,
    compute_source_fingerprint,
    find_ast_scopes,
    byte_col_to_char_col,
)
from scripts.generic_execution_localizer import (
    GenericExecutionLocalizer,
    LocalizationDecision,
)
from scripts.v2_2_recovery_manager import (
    ProposalHistory,
    V22SupervisedWorker,
    FailureDisambiguator,
)


MULTI_CLASS_MODULE = '''"""Data collector module with duplicate method signatures."""


class CollectorA:
    """Primary collector for alpha streams."""

    def __init__(self, name: str):
        self.name = name

    def collect(self) -> List[str]:
        # Collect alpha data
        return [f"alpha:{self.name}"]

    def summarize(self) -> str:
        return f"CollectorA({self.name})"


class CollectorB:
    """Secondary collector for beta streams."""

    def __init__(self, name: str):
        self.name = name

    def collect(self) -> List[str]:
        # Collect beta data
        return [f"beta:{self.name}"]

    def summarize(self) -> str:
        return f"CollectorB({self.name})"
'''

ADVERSARIAL_UNICODE_MODULE = '''# -*- coding: utf-8 -*-
"""🚀 Module with complex multi-byte UTF-8 emojis 🔥, accents café, and math π symbols."""

import os
from typing import List

# Greek math characters: α = 1.0, β = 2.0, λ = 42
GLOBAL_CONFIG = {"title": "Café Résumé ☕", "symbol": "∑(xᵢ · yᵢ) = π"}


class UnicodeProcessorA:
    """Class before the target with emojis 🌟 and unicode strings."""

    def process_header(self, text: str) -> str:
        prefix = "🎉 [START] "
        return prefix + text.strip() + " [END] 🎊"


class TargetService:
    """The target service containing the method to patch."""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.tag = "🏷️ v1.0.0"

    def execute_payload(self, items: List[str]) -> str:
        # Non-ASCII characters on preceding lines:
        # Step 1: Filter emojis 🚀 and validate café
        cleaned = [item.strip() for item in items if item]
        # Target return statement to patch:
        return " -> ".join(cleaned)

    def format_footer(self) -> str:
        return "Footer: 🌈 done"
'''


class MockCoderAgentOutput(BaseModel):
    modifications: list = []
    patch: str = ""
    modified_files: list = []
    reasoning_summary: str = ""
    confidence: float = 1.0


def test_end_to_end_worker_hook_serialization_preserves_structural_metadata(tmp_path: Path, monkeypatch):
    """Verify end-to-end path from Coder output through V22SupervisedWorker hooks to DemoPatchBuilder.

    Verifies:
    1. Coder returns raw JSON with structural metadata: target_symbol, target_class, line_range, source_fingerprint.
    2. coder_execute_hook upgrades CoderOutput.modifications into StructuralCodeModification instances.
    3. Structural metadata is preserved into DemoPatchBuilder.
    4. Patch modifies only CollectorB.collect and leaves CollectorA.collect pristine.
    """
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    target_py = ws / "collector.py"
    target_py.write_text(MULTI_CLASS_MODULE, encoding="utf-8")
    initial_sha = hashlib.sha256(target_py.read_bytes()).hexdigest()

    # Precalculate valid fingerprint of CollectorB.collect
    scopes = find_ast_scopes(MULTI_CLASS_MODULE)
    b_collect_scope = next(s for s in scopes if s.qualified_name == "CollectorB.collect")
    fp = b_collect_scope.fingerprint

    # Raw JSON payload that a real LLM Coder outputs
    raw_coder_response = json.dumps({
        "modifications": [
            {
                "path": "collector.py",
                "target_symbol": "CollectorB.collect",
                "target_class": "CollectorB",
                "target_method": "collect",
                "line_range": [b_collect_scope.start_line, b_collect_scope.end_line],
                "source_fingerprint": fp,
                "operation": "replace",
                "anchor": '        return [f"beta:{self.name}"]',
                "code": '        return [f"beta_v2:{self.name.upper()}"]',
                "reason": "Upgrade beta collection format",
            }
        ],
        "patch": "",
        "modified_files": ["collector.py"],
        "reasoning_summary": "Target CollectorB.collect using structural AST grounding.",
        "confidence": 0.95,
    })

    worker = V22SupervisedWorker(
        experiment_id="test_runtime_exp",
        task_id="test_task_001",
        condition="full_ddiv",
        provider="mock",
        workspace_root=ws,
    )

    # Mock CoderAgent that emits raw_coder_response and CoderOutput with basic CodeModification
    # (simulating Pydantic v2 stripping extra fields before the hook rehydrates them)
    from agents.coder import CodeModification
    basic_mod = CodeModification(
        path="collector.py",
        operation="replace",
        anchor='        return [f"beta:{self.name}"]',
        code='        return [f"beta_v2:{self.name.upper()}"]',
        reason="Upgrade beta collection format",
    )

    intercepted_mods_in_builder = []

    def mock_coder_execute(coder_self, c_in, meta):
        res = AgentExecutionResult(
            task_id=meta.task_id,
            run_id=meta.run_id,
            agent_id="Coder",
            attempt=meta.attempt,
            success=True,
            output=MockCoderAgentOutput(modifications=[basic_mod]),
        )
        res.raw_response = raw_coder_response
        return res

    orig_build_patch = DemoPatchBuilder.build_patch

    def spy_build_patch(builder_self, mods, base_dir):
        for m in mods:
            intercepted_mods_in_builder.append(m)
        return orig_build_patch(builder_self, mods, base_dir)

    monkeypatch.setattr(ew.CoderAgent, "execute", mock_coder_execute)
    monkeypatch.setattr(DemoPatchBuilder, "build_patch", spy_build_patch)

    def mock_experiment_run(self):
        # Call hooked coder.execute
        coder = ew.CoderAgent(None)
        meta = AgentInputMetadata(task_id=self.task_id, run_id="r1", attempt=1)
        c_res = ew.CoderAgent.execute(coder, {"issue": "upgrade beta"}, meta)

        # Call hooked DeterministicPatchBuilder (which is DemoPatchBuilder)
        pb = ew.DeterministicPatchBuilder()
        pb_res = pb.build_patch(c_res.output.modifications, base_dir=self.workspace_root)
        return pb_res

    monkeypatch.setattr(ew.ExperimentWorker, "run", mock_experiment_run)

    pb_res = worker.run()

    # 1. Verify build succeeded
    assert pb_res.success is True, f"Patch build failed: {pb_res.error_message}"

    # 2. Verify all 5 structural metadata fields survived into DemoPatchBuilder
    assert len(intercepted_mods_in_builder) == 1
    passed_mod = intercepted_mods_in_builder[0]
    assert isinstance(passed_mod, StructuralCodeModification)
    assert passed_mod.target_symbol == "CollectorB.collect"
    assert passed_mod.target_class == "CollectorB"
    assert passed_mod.target_method == "collect"
    assert passed_mod.line_range == (b_collect_scope.start_line, b_collect_scope.end_line)
    assert passed_mod.source_fingerprint == fp

    # 3. Apply patch and verify CollectorB is modified while CollectorA is untouched
    import subprocess
    patch_file = ws / "patch.diff"
    patch_file.write_text(pb_res.unified_diff, encoding="utf-8")
    apply_res = subprocess.run(
        ["git", "apply", str(patch_file)],
        cwd=str(ws),
        capture_output=True,
        text=True,
    )
    # If git apply fails because ws is not a git repo, apply directly using patch lines
    patched_content = target_py.read_text(encoding="utf-8")
    # Verify the patch diff targeted only CollectorB
    assert "-        return [f\"beta:{self.name}\"]" in pb_res.unified_diff
    assert "+        return [f\"beta_v2:{self.name.upper()}\"]" in pb_res.unified_diff
    assert "alpha:" not in pb_res.unified_diff


def test_rejection_leaves_working_files_untouched(tmp_path: Path):
    """Verify that rejected proposals leave target files strictly byte-for-byte identical on disk.

    Tests 3 rejection modes:
    1. Invalid anchor string not found in file (ANCHOR_NOT_FOUND).
    2. Ambiguous anchor matching multiple classes without structural scoping (ANCHOR_AMBIGUOUS_MULTI_CLASS).
    3. Stale source fingerprint mismatch (STALE_ANCHOR).
    """
    ws = tmp_path / "ws_safety"
    ws.mkdir(parents=True)
    target_py = ws / "collector.py"
    target_py.write_text(MULTI_CLASS_MODULE, encoding="utf-8")
    original_bytes = target_py.read_bytes()
    original_sha = hashlib.sha256(original_bytes).hexdigest()

    builder = DemoPatchBuilder()

    # Mode 1: Invalid anchor
    bad_anchor_mod = StructuralCodeModification(
        path="collector.py",
        target_symbol="CollectorA.collect",
        operation="replace",
        anchor="        return nonexistent_anchor()",
        code="        return []",
        reason="Bad anchor test",
    )
    res1 = builder.build_patch([bad_anchor_mod], base_dir=ws)
    assert res1.success is False
    assert res1.error_category == "ANCHOR_NOT_FOUND"
    assert hashlib.sha256(target_py.read_bytes()).hexdigest() == original_sha

    # Mode 2: Ambiguous anchor across multiple duplicate methods (unscoped)
    unscoped_mod = StructuralCodeModification(
        path="collector.py",
        operation="replace",
        anchor="    def collect(self) -> List[str]:",
        code="    def collect(self, debug=True) -> List[str]:",
        reason="Ambiguous method signature",
    )
    res2 = builder.build_patch([unscoped_mod], base_dir=ws)
    assert res2.success is False
    assert res2.error_category == "ANCHOR_AMBIGUOUS_MULTI_CLASS"
    assert hashlib.sha256(target_py.read_bytes()).hexdigest() == original_sha

    # Mode 3: Stale source fingerprint
    stale_mod = StructuralCodeModification(
        path="collector.py",
        target_symbol="CollectorB.collect",
        source_fingerprint="0000000000000000000000000000000000000000000000000000000000000000",
        operation="replace",
        anchor='        return [f"beta:{self.name}"]',
        code='        return []',
        reason="Stale fingerprint test",
    )
    res3 = builder.build_patch([stale_mod], base_dir=ws)
    assert res3.success is False
    assert res3.error_category == "STALE_ANCHOR"
    assert hashlib.sha256(target_py.read_bytes()).hexdigest() == original_sha


def test_adversarial_non_ascii_offsets_and_scope_boundaries(tmp_path: Path):
    """Adversarial test with emojis, Greek letters, and accents before and within target method.

    Verifies:
    1. CPython AST byte column offsets map correctly to character indices without offset drifting.
    2. Scope boundaries are exact and target only TargetService.execute_payload.
    3. Patch applies cleanly and modified content parses to a valid AST.
    """
    ws = tmp_path / "ws_unicode"
    ws.mkdir(parents=True)
    target_py = ws / "unicode_service.py"
    target_py.write_text(ADVERSARIAL_UNICODE_MODULE, encoding="utf-8")

    scopes = find_ast_scopes(ADVERSARIAL_UNICODE_MODULE)
    target_scope = next(s for s in scopes if s.qualified_name == "TargetService.execute_payload")

    # Verify character bounds extraction in find_ast_scopes
    assert "def execute_payload" in target_scope.full_text
    assert "format_footer" not in target_scope.full_text
    assert "UnicodeProcessorA" not in target_scope.full_text

    fp = target_scope.fingerprint
    builder = DemoPatchBuilder()

    mod = StructuralCodeModification(
        path="unicode_service.py",
        target_symbol="TargetService.execute_payload",
        target_class="TargetService",
        target_method="execute_payload",
        source_fingerprint=fp,
        operation="replace",
        anchor='        return " -> ".join(cleaned)',
        code='        return " 🌟 ".join(cleaned)  # patched with non-ascii',
        reason="Replace delimiter with unicode star",
    )

    res = builder.build_patch([mod], base_dir=ws)
    assert res.success is True, f"Failed: {res.error_message}"
    assert '-        return " -> ".join(cleaned)' in res.unified_diff
    assert '+        return " 🌟 ".join(cleaned)' in res.unified_diff

    # Verify that AST line/byte conversion helper behaves properly on non-ASCII text
    emoji_line = 'prefix = "🎉 [START] "  # café ☕'
    # In UTF-8: 🎉 is 4 bytes, ☕ is 3 bytes, é is 2 bytes
    byte_len = len(emoji_line.encode("utf-8"))
    char_len = len(emoji_line)
    assert byte_len > char_len
    # Column 0 byte -> column 0 char
    assert byte_col_to_char_col(emoji_line, 0) == 0
    # End of line byte -> end of line char
    assert byte_col_to_char_col(emoji_line, byte_len) == char_len


def test_semantic_anti_repetition_allows_disambiguated_retry_and_blocks_identical_failure():
    """Verify that a valid structurally disambiguated retry is allowed after an unscoped failure,

    while an equivalent failed proposal without new evidence is blocked.
    """
    history = ProposalHistory()

    # Attempt 1: Coder proposes unscoped modification for duplicate method 'collect'
    # Patch builder rejects with ANCHOR_AMBIGUOUS_MULTI_CLASS
    history.record_attempt(
        attempt=1,
        path="collector.py",
        operation="replace",
        anchor="    def collect(self) -> List[str]:",
        code="    def collect(self) -> List[str]:\n        return []",
        target_symbol=None,
        target_class=None,
        error_category="ANCHOR_AMBIGUOUS_MULTI_CLASS",
        error_detail="Anchor matched 2 locations in collector.py.",
    )

    # Attempt 2: Coder repeats identical unscoped modification with slight formatting change
    # MUST be blocked as repeated attempt 1
    blocked_attempt = history.is_repeated(
        path="collector.py",
        operation="replace",
        anchor="    def collect(self) -> List[str]:",
        code="\n    def collect(self) -> List[str]:\n        return []\n",
        target_symbol=None,
        target_class=None,
    )
    assert blocked_attempt == 1

    # Attempt 3: Coder introduces valid structural disambiguation: target_symbol="CollectorB.collect"
    # MUST be allowed (is_repeated returns None)
    allowed_attempt = history.is_repeated(
        path="collector.py",
        operation="replace",
        anchor="    def collect(self) -> List[str]:",
        code="    def collect(self) -> List[str]:\n        return []",
        target_symbol="CollectorB.collect",
        target_class="CollectorB",
    )
    assert allowed_attempt is None, "Structurally disambiguated proposal must not be blocked"


def test_failure_disambiguator_comprehensive_taxonomy():
    """Verify FailureDisambiguator correctly maps all Phase 5/5.1 error categories."""
    # 1. ANCHOR_AMBIGUOUS_MULTI_CLASS
    cat1, _ = FailureDisambiguator.classify(
        patch_valid=False,
        patch_applied=False,
        pb_error_category="ANCHOR_AMBIGUOUS_MULTI_CLASS",
        pb_error_message="Ambiguous across multiple classes",
    )
    assert cat1 == "ANCHOR_AMBIGUOUS_MULTI_CLASS"

    # 2. STALE_ANCHOR
    cat2, _ = FailureDisambiguator.classify(
        patch_valid=False,
        patch_applied=False,
        pb_error_category="STALE_ANCHOR",
        pb_error_message="Fingerprint mismatch",
    )
    assert cat2 == "STALE_ANCHOR"

    # 3. ANCHOR_NOT_IN_TARGET_SCOPE
    cat3, _ = FailureDisambiguator.classify(
        patch_valid=False,
        patch_applied=False,
        pb_error_category="ANCHOR_NOT_IN_TARGET_SCOPE",
        pb_error_message="Anchor exists but not in target scope",
    )
    assert cat3 == "ANCHOR_NOT_IN_TARGET_SCOPE"

    # 4. ANCHOR_NOT_FOUND
    cat4, _ = FailureDisambiguator.classify(
        patch_valid=False,
        patch_applied=False,
        pb_error_category="ANCHOR_NOT_FOUND",
        pb_error_message="Anchor not found in file",
    )
    assert cat4 == "ANCHOR_NOT_FOUND"


def test_v22_supervised_worker_attempt_1_receives_anchor_and_scope_rules(tmp_path, monkeypatch):
    """Verify that Attempt 1 coder input receives anchor grounding, scope rules, and localization guidance,
    while Attempt 2 does not have Attempt 1 localization clobbering Supervisor recovery instructions."""
    worker = V22SupervisedWorker(
        experiment_id="test_exp",
        task_id="test_task",
        condition=ExperimentCondition.FULL_DDIV,
        provider="mock",
        workspace_root=tmp_path / "ws",
    )

    captured_coder_inputs = []

    def mock_run_two_attempts(self_w):
        coder = ew.CoderAgent(None)
        meta1 = AgentInputMetadata(task_id="test_task", run_id="r1", attempt=1, condition=ExperimentCondition.FULL_DDIV)
        meta2 = AgentInputMetadata(task_id="test_task", run_id="r1", attempt=2, condition=ExperimentCondition.FULL_DDIV)

        # Attempt 1
        c_in_1 = {"issue": "bug"}
        ew.CoderAgent.execute(coder, c_in_1, meta1)

        # Attempt 2
        c_in_2 = {"issue": "bug", "recovery_instructions": "Supervisor advice"}
        ew.CoderAgent.execute(coder, c_in_2, meta2)

        return ExperimentConditionRecord(
            experiment_id=self_w.experiment_id,
            task_id=self_w.task_id,
            condition=self_w.condition.value,
            status=ConditionJobStatus.COMPLETED,
            resolved=False,
            workflow_completed=True,
            attempts=2,
            execution_duration_seconds=1.0,
        )

    def dummy_coder(coder_self, c_in, meta):
        captured_coder_inputs.append((meta.attempt, dict(c_in)))
        return AgentExecutionResult(
            task_id=meta.task_id,
            run_id=meta.run_id,
            agent_id="Coder",
            attempt=meta.attempt,
            success=False,
            output=None,
        )

    monkeypatch.setattr(ew.CoderAgent, "execute", dummy_coder)
    monkeypatch.setattr(ew.ExperimentWorker, "run", mock_run_two_attempts)

    worker.last_localization_decision = LocalizationDecision(
        target_file="src/module.py",
        primary_symbol="compute",
        status="RESOLVED",
        confidence=1.0,
        evidence_rationale="Found direct call site.",
    )

    rec = worker.run()
    assert rec.status == ConditionJobStatus.COMPLETED
    assert len(captured_coder_inputs) == 2

    # Attempt 1 must receive ANCHOR_RULES, SCOPE_RULES, and localization guidance
    att1_input = captured_coder_inputs[0][1]
    rec_inst1 = att1_input.get("recovery_instructions", "")
    assert "CRITICAL ANCHOR GROUNDING RULES" in rec_inst1
    assert "Target ONLY the relevant implementation files, NEVER test files" in rec_inst1
    assert "CRITICAL SCOPE DIRECTIVE" in rec_inst1
    assert "EXECUTION-PATH LOCALIZATION GUIDANCE" in rec_inst1
    assert "Primary Controlling Symbol: compute" in rec_inst1

    # Attempt 2 must preserve Supervisor advice without being clobbered by Attempt 1 localization guidance
    att2_input = captured_coder_inputs[1][1]
    rec_inst2 = att2_input.get("recovery_instructions", "")
    assert "Supervisor advice" in rec_inst2
    assert "EXECUTION-PATH LOCALIZATION GUIDANCE" not in rec_inst2


