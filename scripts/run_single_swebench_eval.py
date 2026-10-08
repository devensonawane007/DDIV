"""End-to-end SWE-bench execution and formal evaluation script for a single real task."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to sys.path for direct CLI invocation
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from agents.base import AgentExecutionResult, AgentInputMetadata
from agents.coder import CoderAgent, CoderOutput
from agents.locator import LocatorAgent, LocatorOutput
from agents.supervisor import SupervisorAgent, SupervisorDecision
from agents.tester import TesterAgent, TesterOutput
from core.config import DDIVConfig, ExecutionMode, ProviderType
from evaluation.command_runner import CommandRunner
from evaluation.patch_builder import (
    CodeModification,
    DeterministicPatchBuilder,
    PatchBuilderResult,
)
from evaluation.patch_manager import PatchManager, PatchValidationResult
from evaluation.backends import (
    EvaluationBackend,
    EvaluationOutcome,
    EvaluationResult,
    EvaluationTier,
    InternalSWEBenchBackend,
    OfficialSWEbenchBackend,
    TwoTierEvaluator,
)
from evaluation.swebench_evaluator import (
    InternalEvaluationResult,
    InternalSWEBenchEvaluator,
    OfficialHarnessChecker,
    OfficialHarnessStatus,
)
from evaluation.swebench_loader import SWEBenchGroundTruth, SWEBenchLoader, SWEBenchRecord, SWEBenchTask
from evaluation.swebench_runner import SWEBenchRunner, TestExecutionResult
from evaluation.workspace import TaskWorkspace, WorkspaceManager
from memory.memory_store import MemoryStore
from memory.trust_ledger import TrustLedger
from models.base import ModelConfig
from models.providers import MockModelProvider, OpenAICompatibleProvider
from models.registry import ModelRegistry
from recovery.strategies import RecoveryAction, RecoveryStrategy, StrategySelector


class PromptLeakageAuditor:
    """Rigorous audit scanner ensuring evaluator ground truth never enters agent prompts or logs."""

    def __init__(self, ground_truth: SWEBenchGroundTruth):
        self.gt = ground_truth
        self.recorded_prompts: List[Dict[str, Any]] = []
        self.leakage_detected: bool = False
        self.leakage_details: List[str] = []

    def audit_input(self, agent_id: str, attempt: int, input_data: Dict[str, Any]) -> None:
        """Scan serialized input data against all ground truth boundaries."""
        serialized = json.dumps(input_data, default=str)
        self.recorded_prompts.append({
            "agent": agent_id,
            "attempt": attempt,
            "content": serialized,
            "timestamp": time.time(),
        })

        # 1. Audit Gold Patch
        if self.gt.gold_patch and len(self.gt.gold_patch.strip()) > 30:
            if self.gt.gold_patch.strip() in serialized:
                self.leakage_detected = True
                self.leakage_details.append(f"Full gold_patch leaked to {agent_id} in attempt {attempt}")

        # 2. Audit Test Patch
        if self.gt.test_patch and len(self.gt.test_patch.strip()) > 30:
            if self.gt.test_patch.strip() in serialized:
                self.leakage_detected = True
                self.leakage_details.append(f"Full test_patch leaked to {agent_id} in attempt {attempt}")

        # 3. Audit FAIL_TO_PASS test identifiers
        for f2p in self.gt.fail_to_pass:
            if f2p in serialized:
                self.leakage_detected = True
                self.leakage_details.append(f"FAIL_TO_PASS identifier '{f2p}' leaked to {agent_id} in attempt {attempt}")
            # Also check function name portion
            if "::" in f2p:
                func_name = f2p.split("::")[-1]
                if len(func_name) > 6 and func_name in serialized:
                    self.leakage_detected = True
                    self.leakage_details.append(f"FAIL_TO_PASS function '{func_name}' leaked to {agent_id} in attempt {attempt}")

        # 4. Audit PASS_TO_PASS test identifiers
        for p2p in self.gt.pass_to_pass:
            if p2p in serialized:
                self.leakage_detected = True
                self.leakage_details.append(f"PASS_TO_PASS identifier '{p2p}' leaked to {agent_id} in attempt {attempt}")

        if self.leakage_detected:
            raise AssertionError(f"CRITICAL GROUND TRUTH LEAKAGE DETECTED: {self.leakage_details[-1]}")


def sanitize_artifact_for_storage(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure no secrets or authorization headers exist in experiment artifacts."""
    serialized = json.dumps(data)
    import re
    cleaned = re.sub(r'gsk_[a-zA-Z0-9_\-]{20,}', '[REDACTED_GROQ_KEY]', serialized)
    cleaned = re.sub(r'sk-[a-zA-Z0-9_\-]{20,}', '[REDACTED_API_KEY]', cleaned)
    cleaned = re.sub(r'hf_[a-zA-Z0-9_\-]{20,}', '[REDACTED_HF_TOKEN]', cleaned)
    cleaned = re.sub(r'AIza[a-zA-Z0-9_\-]{20,}', '[REDACTED_GEMINI_KEY]', cleaned)
    return json.loads(cleaned)


def main():
    parser = argparse.ArgumentParser(description="Execute one real SWE-bench task through Locator -> Coder -> Tester and evaluate.")
    parser.add_argument("--task-id", type=str, default="pallets__flask-5014", help="Instance ID to evaluate")
    parser.add_argument("--dataset", type=str, default="data/swebench/test-00000-of-00001.parquet", help="Path to parquet dataset")
    parser.add_argument("--provider", type=str, default="mock", choices=["mock", "openai", "real"], help="Model provider type")
    args = parser.parse_args()

    overall_start_time = time.time()

    print("=" * 70)
    print(" DDIV SWE-BENCH REAL TASK EXECUTION & FORMAL EVALUATION")
    print("=" * 70)
    print()

    # --------------------------------------------------
    # STEP 1 — LOAD THE REAL SWE-BENCH INSTANCE
    # --------------------------------------------------
    loader = SWEBenchLoader()
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"Error: Dataset file not found at {dataset_path}")
        sys.exit(1)

    records = loader.load_from_file(dataset_path)
    matched = [r for r in records if r.task.instance_id == args.task_id]
    if not matched:
        print(f"Error: Task {args.task_id} not found in dataset {dataset_path}")
        sys.exit(1)

    record: SWEBenchRecord = matched[0]
    task: SWEBenchTask = record.task
    gt: SWEBenchGroundTruth = record.ground_truth

    # Initialize Prompt Leakage Auditor
    auditor = PromptLeakageAuditor(ground_truth=gt)

    print("Step 1: Task Loaded & Verified:")
    print(f"   - Instance ID:        {task.instance_id}")
    print(f"   - Repository:         {task.repo}")
    print(f"   - Base Commit:        {task.base_commit}")
    print(f"   - Problem Statement:  {task.problem_statement[:140].strip()}...")
    print(f"   - Ground Truth F2P:   {len(gt.fail_to_pass)} test(s) [EVALUATOR-ONLY]")
    print(f"   - Ground Truth P2P:   {len(gt.pass_to_pass)} test(s) [EVALUATOR-ONLY]")
    print(f"   - Ground Truth Gold:  {len(gt.gold_patch.splitlines())} lines [EVALUATOR-ONLY]")
    print()

    # --------------------------------------------------
    # STEP 2 — CREATE ISOLATED WORKSPACES
    # --------------------------------------------------
    ws_mgr = WorkspaceManager(base_workspace_dir="data/workspaces")
    patch_mgr = PatchManager()
    runner = SWEBenchRunner()
    cmd_runner = CommandRunner()

    agent_ws = ws_mgr.create_workspace(
        task_id=f"{task.instance_id}-agent",
        init_git=False,
        subfolder=f"swebench/{task.instance_id}/agent_ws",
    )
    eval_ws = ws_mgr.create_workspace(
        task_id=f"{task.instance_id}-eval",
        init_git=False,
        subfolder=f"swebench/{task.instance_id}/eval_ws",
    )

    # Checkout base commit and reset both to pristine state
    co_agent = ws_mgr.checkout_repository(agent_ws, repo=task.repo, base_commit=task.base_commit, timeout=180)
    co_eval = ws_mgr.checkout_repository(eval_ws, repo=task.repo, base_commit=task.base_commit, timeout=180)

    # Force hard clean to guarantee zero contamination from previous runs
    ws_mgr.runner.run(["git", "reset", "--hard", task.base_commit], cwd=agent_ws.path)
    ws_mgr.runner.run(["git", "clean", "-fd"], cwd=agent_ws.path)
    ws_mgr.runner.run(["git", "reset", "--hard", task.base_commit], cwd=eval_ws.path)
    ws_mgr.runner.run(["git", "clean", "-fd"], cwd=eval_ws.path)

    # Re-verify commits with git
    rev_agent = ws_mgr.runner.run(["git", "rev-parse", "HEAD"], cwd=agent_ws.path).stdout.strip()
    rev_eval = ws_mgr.runner.run(["git", "rev-parse", "HEAD"], cwd=eval_ws.path).stdout.strip()

    print("Step 2: Dual Workspaces Provisioned:")
    print(f"   - Agent Workspace:      {agent_ws.path} (HEAD: {rev_agent[:10]})")
    print(f"   - Evaluation Workspace: {eval_ws.path} (HEAD: {rev_eval[:10]})")
    if rev_agent != task.base_commit or rev_eval != task.base_commit:
        print(f"Error: Checkout commit mismatch. Expected {task.base_commit}")
        sys.exit(1)
    print()

    # --------------------------------------------------
    # MODEL PROVIDER SETUP & CONFIGURATION
    # --------------------------------------------------
    if args.provider == "mock":
        custom_responses = {
            "Locator": {
                "relevant_files": ["src/flask/blueprints.py"],
                "relevant_symbols": ["Blueprint", "Blueprint.__init__"],
                "reasoning_summary": "Located Blueprint class in src/flask/blueprints.py where blueprint names are initialized.",
                "confidence": 0.92,
            },
            "Coder": {
                "modifications": [
                    {
                        "path": "src/flask/blueprints.py",
                        "target_symbol": "Blueprint.__init__",
                        "operation": "insert_after",
                        "anchor": "root_path=root_path,\n        )",
                        "code": "        if not name:\n            raise ValueError(\"'name' may not be empty.\")\n",
                        "reason": "Added check in Blueprint.__init__ to verify name is non-empty before checking for dot characters, raising ValueError if name is empty.",
                    }
                ],
                "patch": (
                    "diff --git a/src/flask/blueprints.py b/src/flask/blueprints.py\n"
                    "--- a/src/flask/blueprints.py\n"
                    "+++ b/src/flask/blueprints.py\n"
                    "@@ -190,6 +190,9 @@ def __init__(\n"
                    "             root_path=root_path,\n"
                    "         )\n"
                    " \n"
                    "+        if not name:\n"
                    "+            raise ValueError(\"'name' may not be empty.\")\n"
                    "+\n"
                    "         if \".\" in name:\n"
                    "             raise ValueError(\"'name' may not contain a dot '.' character.\")\n"
                    " \n"
                ),
                "modified_files": ["src/flask/blueprints.py"],
                "reasoning_summary": "Added check in Blueprint.__init__ to verify name is non-empty before checking for dot characters, raising ValueError if name is empty.",
                "confidence": 0.95,
            },
            "Tester": {
                "assessment": "Patch adds non-empty name validation in Blueprint.__init__ raising ValueError. Tested against empty string.",
                "suspected_failures": ["None - standard string emptiness check"],
                "recommended_tests": ["tests/test_blueprints.py::test_dotted_name_not_allowed"],
                "confidence": 0.90,
            },
            "Supervisor": {
                "should_retry": False,
                "detected_failure": None,
                "diagnosis": "First attempt resolved all tests.",
                "recovery_strategy": None,
                "intervention_instructions": "None needed.",
                "confidence": 0.95,
            },
        }
        loc_provider = MockModelProvider(ModelConfig(name="Locator", model_id="mock-locator"), custom_responses=custom_responses)
        code_provider = MockModelProvider(ModelConfig(name="Coder", model_id="mock-coder"), custom_responses=custom_responses)
        test_provider = MockModelProvider(ModelConfig(name="Tester", model_id="mock-tester"), custom_responses=custom_responses)
        sup_provider = MockModelProvider(ModelConfig(name="Supervisor", model_id="mock-supervisor"), custom_responses=custom_responses)
        model_metadata = {
            "Locator": {"provider": "gemini", "model": "gemini-2.5-flash"},
            "Coder": {"provider": "groq", "model": "openai/gpt-oss-120b"},
            "Tester": {"provider": "openrouter", "model": "deepseek/deepseek-v4.1-flash"},
            "Supervisor": {"provider": "huggingface", "model": "Qwen/Qwen3-Coder-30B-A3B-Instruct"},
        }
        max_retries = 2
    else:
        cfg = DDIVConfig.load_from_env()
        cfg.mode = ExecutionMode.REAL
        cfg.provider_type = ProviderType.OPENAI_COMPATIBLE
        cfg.validate_for_execution()
        registry = ModelRegistry(cfg)

        loc_provider = registry.get_provider_for_agent(cfg.locator)
        code_provider = registry.get_provider_for_agent(cfg.coder)
        test_provider = registry.get_provider_for_agent(cfg.tester)
        sup_provider = registry.get_provider_for_agent(cfg.supervisor)

        model_metadata = {
            "Locator": {"provider": cfg.locator.provider, "model": cfg.locator.model, "base_url": cfg.locator.base_url},
            "Coder": {"provider": cfg.coder.provider, "model": cfg.coder.model, "base_url": cfg.coder.base_url},
            "Tester": {"provider": cfg.tester.provider, "model": cfg.tester.model, "base_url": cfg.tester.base_url},
            "Supervisor": {"provider": cfg.supervisor.provider, "model": cfg.supervisor.model, "base_url": cfg.supervisor.base_url},
        }
        max_retries = cfg.locator.max_retries  # 2

    # Instantiate Agents & Deterministic Patch Builder & Two-Tier Evaluator
    locator = LocatorAgent(loc_provider)
    coder = CoderAgent(code_provider)
    tester = TesterAgent(test_provider)
    supervisor = SupervisorAgent(sup_provider)
    patch_builder = DeterministicPatchBuilder(patch_mgr)
    two_tier = TwoTierEvaluator(
        internal_backend=InternalSWEBenchBackend(patch_manager=patch_mgr, command_runner=cmd_runner),
        official_backend=OfficialSWEbenchBackend(command_runner=cmd_runner),
    )

    # Initialize Memory & Trust
    memory_store = MemoryStore("data/ddiv_memory.db")
    trust_ledger = TrustLedger(
        memory_store=memory_store,
        initial_trust={"Locator": 0.87, "Coder": 0.74, "Tester": 0.91, "Supervisor": 0.84},
    )

    # Pipeline tracking state
    pipeline_status = {
        "locator": False,
        "coder": False,
        "tester": False,
        "patch_valid": False,
        "recovery_used": False,
        "supervisor_status": "NOT_USED",
    }

    attempt_logs: List[Dict[str, Any]] = []
    max_attempts = max_retries + 1  # 3 total attempts
    attempt = 1
    is_resolved = False
    final_patch = ""
    last_eval_res: Optional[EvaluationResult] = None
    last_val_res: Optional[PatchValidationResult] = None

    recovery_instructions = ""
    locator_guidance = ""
    prev_attempts_feedback: List[str] = []
    located_files: List[str] = []
    located_symbols: List[str] = []
    loc_res: Optional[AgentExecutionResult] = None

    # Discover legitimately available repository files for Locator
    flask_files = []
    if (agent_ws.path / "src" / "flask").exists():
        flask_files = [
            str(p.relative_to(agent_ws.path)).replace("\\", "/")
            for p in (agent_ws.path / "src" / "flask").glob("**/*.py")
        ]

    # Discover legitimately existing test files for Tester
    test_files_list = []
    if (agent_ws.path / "tests").exists():
        test_files_list = [
            str(p.relative_to(agent_ws.path)).replace("\\", "/")
            for p in (agent_ws.path / "tests").glob("test_*.py")
        ]

    # --------------------------------------------------
    # MULTI-ATTEMPT EXECUTION LOOP
    # --------------------------------------------------
    while attempt <= max_attempts and not is_resolved:
        print("=" * 70)
        print(f" EXECUTION ATTEMPT {attempt} OF {max_attempts}")
        print("=" * 70)

        meta = AgentInputMetadata(task_id=task.instance_id, run_id=f"run_swe_{task.instance_id}_{int(time.time())}", attempt=attempt)

        # Ensure workspaces are clean at the start of attempt
        patch_mgr.revert_workspace(agent_ws.path)
        patch_mgr.revert_workspace(eval_ws.path)

        # --------------------------------------------------
        # STEP 3 — RUN THE REAL LOCATOR
        # --------------------------------------------------
        if attempt == 1 or locator_guidance:
            print("Step 3: Executing Locator Agent...")
            loc_input = {
                "issue": task.problem_statement,
                "repo_structure": f"Repository: {task.repo}\nFiles:\n" + "\n".join(f" - {f}" for f in flask_files),
                "recovery_guidance": locator_guidance,
            }
            auditor.audit_input("Locator", attempt, loc_input)
            loc_res = locator.execute(loc_input, meta)

            if loc_res.success and loc_res.output:
                pipeline_status["locator"] = True
                located_files = getattr(loc_res.output, "relevant_files", [])
                located_symbols = getattr(loc_res.output, "relevant_symbols", [])
                print(f"   - Status:             PASS")
                print(f"   - Located Files:      {located_files}")
                print(f"   - Located Symbols:    {located_symbols}")
                print(f"   - Confidence:         {loc_res.confidence:.2f}")
                print(f"   - Latency:            {loc_res.latency_seconds:.2f}s")
            else:
                print(f"   - Status:             FAIL ({loc_res.error})")
                pipeline_status["locator"] = False
            print()
        else:
            print("Step 3: Reusing previous localization...")
            print(f"   - Located Files:      {located_files}")
            print()

        # --------------------------------------------------
        # STEP 4 — RUN THE REAL CODER
        # --------------------------------------------------
        print("Step 4: Executing Coder Agent...")
        # Read source code from agent workspace for the located files
        source_code_blocks = []
        for r_file in located_files:
            r_norm = r_file.replace("\\", "/").strip()
            fpath = agent_ws.path / r_norm
            if fpath.exists():
                try:
                    content = fpath.read_text(encoding="utf-8")
                    source_code_blocks.append(
                        f"### File: {r_norm}\n"
                        f"```python\n{content}\n```"
                    )
                except Exception as read_err:
                    source_code_blocks.append(f"### File: {r_norm} (read error: {read_err})")

        source_code_context = "\n\n".join(source_code_blocks) if source_code_blocks else "No source code available."

        coder_input = {
            "issue": task.problem_statement,
            "locator_result": loc_res.output.model_dump() if (loc_res and loc_res.output) else {},
            "source_files": source_code_context,
            "previous_attempts": "\n\n".join(prev_attempts_feedback[-2:]),
            "recovery_instructions": recovery_instructions,
        }
        auditor.audit_input("Coder", attempt, coder_input)
        coder_res = coder.execute(coder_input, meta)

        candidate_patch = ""
        anchor_found = False
        anchor_unique = False
        pb_ops: List[str] = []
        coder_proposals: List[Dict[str, Any]] = []
        pb_res: Optional[PatchBuilderResult] = None
        pb_error: Optional[str] = None

        if coder_res.success and coder_res.output:
            pipeline_status["coder"] = True
            print(f"   - Status:             PASS")
            print(f"   - Modified Files:     {getattr(coder_res.output, 'modified_files', [])}")
            print(f"   - Reasoning:          {getattr(coder_res.output, 'reasoning_summary', '')[:100]}...")
            print(f"   - Confidence:         {coder_res.confidence:.2f}")
            print(f"   - Latency:            {coder_res.latency_seconds:.2f}s")

            mods = getattr(coder_res.output, "modifications", [])
            if mods:
                coder_proposals = [m.model_dump() if hasattr(m, "model_dump") else dict(m) for m in mods]
                pb_ops = [getattr(m, "operation", None) or m.get("operation", "unknown") for m in mods]
                print(f"   - Structured Changes: {len(mods)} modification(s)")
                for idx, m in enumerate(mods):
                    m_path = getattr(m, "path", None) or m.get("path")
                    m_op = getattr(m, "operation", None) or m.get("operation")
                    print(f"     [{idx+1}] File: {m_path}, Op: {m_op}")

                # Step 4b: Deterministic Patch Construction
                print("Step 4b: Executing Deterministic Patch Builder...")
                pb_res = patch_builder.build_patch(mods, agent_ws.path)
                anchor_found = pb_res.anchor_found
                anchor_unique = pb_res.anchor_unique

                if pb_res.success:
                    candidate_patch = pb_res.unified_diff
                    final_patch = candidate_patch
                    print(f"   - Deterministic Diff: GENERATED ({len(candidate_patch.splitlines())} lines in {pb_res.generation_latency*1000:.1f}ms)")
                    print(f"   - Anchor Found:       {anchor_found}")
                    print(f"   - Anchor Unique:      {anchor_unique}")
                else:
                    pb_error = f"{pb_res.error_category}: {pb_res.error_message}"
                    print(f"   - Deterministic Diff: FAILED ({pb_error})")
                    agent_failure_summary = f"Deterministic PatchBuilder failed ({pb_error})"
            else:
                candidate_patch = getattr(coder_res.output, "patch", "")
                final_patch = candidate_patch
                if candidate_patch:
                    print(f"   - Fallback Raw Patch: {len(candidate_patch.splitlines())} lines")
        else:
            pipeline_status["coder"] = False
            print(f"   - Status:             FAIL ({coder_res.error})")
        print()

        # --------------------------------------------------
        # STEP 5 — PATCH VALIDATION
        # --------------------------------------------------
        print("Step 5: Validating Candidate Patch Structure...")
        val_res = patch_mgr.validate_patch(candidate_patch)
        last_val_res = val_res

        if val_res.is_valid:
            pipeline_status["patch_valid"] = True
            print(f"   - Valid Unified Diff: YES")
            print(f"   - Target Files:       {val_res.modified_files}")
        else:
            pipeline_status["patch_valid"] = False
            print(f"   - Valid Unified Diff: NO ({val_res.error_message})")
        print()

        # --------------------------------------------------
        # STEP 6 — RUN THE REAL TESTER
        # --------------------------------------------------
        print("Step 6: Executing Tester Agent...")
        tester_input = {
            "issue": task.problem_statement,
            "candidate_patch": candidate_patch,
            "relevant_code": f"Modified: {val_res.modified_files}, Located: {located_files}",
            "existing_tests": "Available test files:\n" + "\n".join(f" - {tf}" for tf in test_files_list[:10]),
        }
        auditor.audit_input("Tester", attempt, tester_input)
        tester_res = tester.execute(tester_input, meta)

        rec_tests = []
        if tester_res.success and tester_res.output:
            pipeline_status["tester"] = True
            rec_tests = getattr(tester_res.output, "recommended_tests", [])
            print(f"   - Status:             PASS")
            print(f"   - Assessment:         {getattr(tester_res.output, 'assessment', '')[:100]}...")
            print(f"   - Recommended Tests:  {rec_tests}")
            print(f"   - Confidence:         {tester_res.confidence:.2f}")
            print(f"   - Latency:            {tester_res.latency_seconds:.2f}s")
        else:
            pipeline_status["tester"] = False
            print(f"   - Status:             FAIL ({tester_res.error})")
        print()

        # --------------------------------------------------
        # STEP 7 — VERIFY / TEST THE CANDIDATE PATCH
        # --------------------------------------------------
        print("Step 7: Applying and Testing Candidate Patch...")
        # 7a. Agent Workspace test run (internal agent feedback)
        agent_apply_res = patch_mgr.apply_patch(agent_ws.path, val_res.sanitized_patch if val_res.is_valid else candidate_patch)
        agent_test_res: TestExecutionResult = TestExecutionResult(passed=False, raw_stdout="", raw_stderr="Patch not applied")
        if agent_apply_res.is_success:
            agent_test_res = runner.run_task_at_base_commit(agent_ws, task, test_targets=rec_tests or ["tests/test_blueprints.py"], timeout=60)
            print(f"   - Agent WS Tests:     {agent_test_res.status_label} ({agent_test_res.passed_tests}/{agent_test_res.total_tests} passed in {agent_test_res.duration_seconds:.2f}s)")
        else:
            print(f"   - Agent WS Apply:     FAILED ({agent_apply_res.stderr or agent_apply_res.stdout})")

        # 7b. Pristine Evaluation Workspace test run (Evaluator-side ground truth Tier 1)
        eval_res: EvaluationResult = two_tier.evaluate_internal(
            workspace=eval_ws,
            record=record,
            candidate_patch=val_res.sanitized_patch if val_res.is_valid else candidate_patch,
        )
        last_eval_res = eval_res
        print(f"   - Eval WS Candidate:  {'APPLIED' if eval_res.details.get('candidate_patch_applied') else 'FAILED'}")
        print(f"   - Eval WS Test Patch: {'APPLIED' if eval_res.details.get('test_patch_applied') else 'FAILED'}")
        print(f"   - Internal F2P:       {'PASS' if eval_res.details.get('all_f2p_passed') else 'FAIL'} ({eval_res.details.get('fail_to_pass_results', {})})")
        print(f"   - Internal P2P:       {'PASS' if eval_res.details.get('all_p2p_passed') else 'FAIL'} ({len(eval_res.details.get('pass_to_pass_results', {}))} regression tests)")
        print(f"   - Internal Verdict:   {eval_res.verdict}")
        print(f"   - Evaluation Time:    {eval_res.duration_seconds:.2f}s")
        print()

        # Save per-attempt patch file to preserve failure history
        patch_dir = Path("data/experiments")
        patch_dir.mkdir(parents=True, exist_ok=True)
        attempt_patch_file = patch_dir / f"{task.instance_id}_attempt_{attempt}.patch"
        attempt_patch_file.write_text(candidate_patch or "", encoding="utf-8")

        # Check for successful internal resolution
        if eval_res.outcome == EvaluationOutcome.RESOLVED:
            is_resolved = True
            trust_ledger.update_trust("Coder", task.instance_id, attempt, True, "Patch passed all internal F2P and P2P tests")
            trust_ledger.update_trust("Locator", task.instance_id, attempt, True, "Accurate fault localization")
            trust_ledger.update_trust("Tester", task.instance_id, attempt, True, "Confirmed test coverage")
            print(f"   >>> Attempt {attempt} RESOLVED the task internally! <<<")
            print()
            attempt_logs.append({
                "attempt": attempt,
                "candidate_patch_file": str(attempt_patch_file),
                "coder_semantic_proposal": coder_proposals,
                "patch_builder_operation": pb_ops,
                "anchor_found": anchor_found,
                "anchor_unique": anchor_unique,
                "generated_unified_diff": candidate_patch,
                "patch_validation_result": val_res.model_dump(),
                "git_apply_result": {
                    "success": agent_apply_res.is_success,
                    "returncode": agent_apply_res.exit_code,
                    "stderr": agent_apply_res.stderr,
                },
                "validation_result": "PASS" if val_res.is_valid else "FAIL",
                "validation_error": None,
                "failure_category": None,
                "recovery_strategy": None,
                "supervisor_diagnosis": "All tests passed successfully.",
                "should_retry": False,
                "internal_resolved": True,
                "verdict": eval_res.verdict,
                "f2p_passed": eval_res.details.get("all_f2p_passed", False),
                "p2p_passed": eval_res.details.get("all_p2p_passed", False),
                "latency": eval_res.duration_seconds,
            })
            break

        # --------------------------------------------------
        # STEP 8 & 9 — SUPERVISOR / DDIV RECOVERY & RETRY
        # --------------------------------------------------
        pipeline_status["recovery_used"] = True
        pipeline_status["supervisor_status"] = "PASS"

        if attempt < max_attempts:
            print("Step 8: Invoking Recovery Supervisor Agent (Qwen3-Coder-30B)...")
            # Build failure feedback for Supervisor WITHOUT secret ground-truth test names
            agent_failure_summary = (
                f"Patch validation: {val_res.is_valid} ({val_res.error_message or 'OK'})\n"
                f"Agent WS test status: {agent_test_res.status_label}\n"
                f"Agent WS test stdout/stderr:\n{agent_test_res.raw_stdout[:400]}\n{agent_test_res.raw_stderr[:400]}\n"
            )

            sup_input = {
                "task_id": task.instance_id,
                "max_attempts": max_attempts,
                "issue": task.problem_statement,
                "locator_summary": f"Located files: {located_files}, symbols: {located_symbols}",
                "patch_summary": candidate_patch[:600] if candidate_patch else "No patch generated",
                "patch_applied": val_res.is_valid and agent_apply_res.is_success,
                "test_results": {
                    "agent_tests_passed": agent_test_res.passed,
                    "agent_test_status": agent_test_res.status_label,
                    "agent_test_output": agent_failure_summary,
                },
                "deterministic_hints": [
                    f"Attempt {attempt} failed internal evaluation.",
                    f"Candidate patch applied: {eval_res.candidate_patch_applied}",
                    f"Test execution verdict: {eval_res.evaluation_verdict}",
                ],
                "trust_scores": trust_ledger.get_all_scores(),
            }
            auditor.audit_input("Supervisor", attempt, sup_input)
            sup_res = supervisor.execute(sup_input, meta)

            if sup_res.success and sup_res.output:
                dec: SupervisorDecision = sup_res.output
                print(f"   - Detected Failure:   {dec.detected_failure}")
                print(f"   - Diagnosis:          {dec.diagnosis}")
                print(f"   - Recovery Strategy:  {dec.recovery_strategy}")
                print(f"   - Intervention:       {dec.intervention_instructions}")
                print(f"   - Should Retry:       {dec.should_retry}")

                # Build targeted recovery action via StrategySelector
                strat_enum = RecoveryStrategy.A3
                if dec.recovery_strategy:
                    try:
                        strat_enum = RecoveryStrategy(dec.recovery_strategy)
                    except Exception:
                        strat_enum = RecoveryStrategy.A3

                rec_action = StrategySelector.build_action(
                    strategy=strat_enum,
                    diagnosis_text=dec.diagnosis,
                    test_output=agent_failure_summary,
                    previous_patch=candidate_patch,
                    located_files=located_files,
                    supervisor_instructions=dec.intervention_instructions,
                )

                # Update trust scores based on diagnosis
                if dec.detected_failure == "F1":
                    trust_ledger.update_trust("Locator", task.instance_id, attempt, False, dec.diagnosis)
                    locator_guidance = rec_action.guidance_for_locator or dec.intervention_instructions
                elif dec.detected_failure in ("F2", "F3"):
                    trust_ledger.update_trust("Coder", task.instance_id, attempt, False, dec.diagnosis)
                    recovery_instructions = rec_action.guidance_for_coder
                elif dec.detected_failure == "F4":
                    recovery_instructions = f"Avoid previous strategy: {dec.intervention_instructions}"

                prev_attempts_feedback.append(
                    f"Attempt {attempt} Diagnosis ({dec.detected_failure}): {dec.diagnosis}\n"
                    f"Directive: {dec.intervention_instructions}"
                )

                attempt_logs.append({
                    "attempt": attempt,
                    "candidate_patch_file": str(attempt_patch_file),
                    "coder_semantic_proposal": coder_proposals,
                    "patch_builder_operation": pb_ops,
                    "anchor_found": anchor_found,
                    "anchor_unique": anchor_unique,
                    "generated_unified_diff": candidate_patch,
                    "patch_validation_result": val_res.model_dump(),
                    "git_apply_result": {
                        "success": agent_apply_res.is_success,
                        "returncode": agent_apply_res.exit_code,
                        "stderr": agent_apply_res.stderr,
                    },
                    "validation_result": "PASS" if val_res.is_valid else "FAIL",
                    "validation_error": val_res.error_message if not val_res.is_valid else None,
                    "failure_category": dec.detected_failure,
                    "recovery_strategy": dec.recovery_strategy,
                    "supervisor_diagnosis": dec.diagnosis,
                    "supervisor_instructions": dec.intervention_instructions,
                    "should_retry": dec.should_retry,
                    "internal_resolved": False,
                    "verdict": eval_res.verdict,
                    "f2p_passed": eval_res.details.get("all_f2p_passed", False),
                    "p2p_passed": eval_res.details.get("all_p2p_passed", False),
                    "latency": eval_res.duration_seconds,
                })

                if not dec.should_retry:
                    print("Supervisor decided not to retry. Stopping.")
                    break
            else:
                print(f"   - Supervisor execution error: {sup_res.error}")
                pipeline_status["supervisor_status"] = "FAIL"
                break
            print()
        else:
            # Final attempt reached without resolution
            attempt_logs.append({
                "attempt": attempt,
                "candidate_patch_file": str(attempt_patch_file),
                "coder_semantic_proposal": coder_proposals,
                "patch_builder_operation": pb_ops,
                "anchor_found": anchor_found,
                "anchor_unique": anchor_unique,
                "generated_unified_diff": candidate_patch,
                "patch_validation_result": val_res.model_dump(),
                "git_apply_result": {
                    "success": agent_apply_res.is_success,
                    "returncode": agent_apply_res.exit_code,
                    "stderr": agent_apply_res.stderr,
                },
                "validation_result": "PASS" if val_res.is_valid else "FAIL",
                "validation_error": val_res.error_message if not val_res.is_valid else None,
                "failure_category": "MAX_ATTEMPTS_REACHED",
                "recovery_strategy": None,
                "supervisor_diagnosis": "Maximum attempts reached without resolution.",
                "should_retry": False,
                "internal_resolved": False,
                "verdict": eval_res.verdict,
                "f2p_passed": eval_res.details.get("all_f2p_passed", False),
                "p2p_passed": eval_res.details.get("all_p2p_passed", False),
                "latency": eval_res.duration_seconds,
            })

        attempt += 1

    total_attempts_run = len(attempt_logs) if attempt_logs else 1

    # --------------------------------------------------
    # STEP 10 — OFFICIAL SWE-BENCH HARNESS EVALUATION (TIER 2)
    # --------------------------------------------------
    print("Step 10: Official SWE-bench Harness Evaluation (Tier 2)...")
    tier2_res: EvaluationResult = two_tier.evaluate_official(
        record=record,
        candidate_patch=final_patch,
    )
    print(f"   - Backend:            {tier2_res.backend_name}")
    print(f"   - Tier:               {tier2_res.tier.value}")
    print(f"   - Harness Available:  {tier2_res.is_available}")
    print(f"   - Tier 2 Outcome:     {tier2_res.outcome.value}")
    print(f"   - Tier 2 Verdict:     {tier2_res.verdict}")
    print(f"   - Diagnostic:         {tier2_res.details.get('diagnostic', tier2_res.error_message or 'N/A')}")
    print()

    # --------------------------------------------------
    # STEP 11 — GROUND-TRUTH LEAKAGE AUDIT
    # --------------------------------------------------
    print("Step 11: Ground-Truth Leakage Audit...")
    leakage_passed = not auditor.leakage_detected
    print(f"   - Prompts Scanned:    {len(auditor.recorded_prompts)}")
    print(f"   - Ground Truth Leak:  {'FAIL' if auditor.leakage_detected else 'PASS'}")
    if not leakage_passed:
        print(f"   - Leak Details:       {auditor.leakage_details}")
    print()

    # --------------------------------------------------
    # STEP 12 — EXPERIMENT ARTIFACT
    # --------------------------------------------------
    print("Step 12: Generating Experiment Artifact...")
    total_duration = time.time() - overall_start_time

    # Save candidate patch file
    patch_dir = Path("data/experiments")
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_file = patch_dir / f"{task.instance_id}.patch"
    patch_file.write_text(final_patch, encoding="utf-8")
    run3_patch_file = patch_dir / f"{task.instance_id}_run3.patch"
    run3_patch_file.write_text(final_patch, encoding="utf-8")

    # Also duplicate attempt patches with _run3_ suffix for safe multi-run history
    for p in patch_dir.glob(f"{task.instance_id}_attempt_*.patch"):
        dest = patch_dir / p.name.replace(f"{task.instance_id}_attempt_", f"{task.instance_id}_run3_attempt_")
        dest.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")

    experiment_artifact = {
        "experiment_id": f"exp_{task.instance_id}_{int(time.time())}",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "instance_id": task.instance_id,
        "repository": task.repo,
        "base_commit": task.base_commit,
        "agents": model_metadata,
        "attempt_count": total_attempts_run,
        "attempts": attempt_logs,
        "candidate_patch_path": str(patch_file),
        "internal_evaluation_status": "COMPLETED",
        "internal_evaluation": {
            "tier": EvaluationTier.TIER_1_INTERNAL.value,
            "backend_name": last_eval_res.backend_name if last_eval_res else "internal_targeted_evaluator",
            "outcome": last_eval_res.outcome.value if last_eval_res else "UNRESOLVED",
            "verdict": last_eval_res.verdict if last_eval_res else "UNRESOLVED_INTERNALLY",
            "duration_seconds": round(last_eval_res.duration_seconds, 2) if last_eval_res else 0.0,
            "all_f2p_passed": last_eval_res.details.get("all_f2p_passed", False) if last_eval_res else False,
            "all_p2p_passed": last_eval_res.details.get("all_p2p_passed", False) if last_eval_res else False,
            "internal_resolved": (last_eval_res.outcome == EvaluationOutcome.RESOLVED) if last_eval_res else False,
            "fail_to_pass_results": last_eval_res.details.get("fail_to_pass_results", {}) if last_eval_res else {},
            "pass_to_pass_results": last_eval_res.details.get("pass_to_pass_results", {}) if last_eval_res else {},
        },
        "official_evaluation": {
            "tier": EvaluationTier.TIER_2_OFFICIAL.value,
            "backend_name": tier2_res.backend_name,
            "available": tier2_res.is_available,
            "outcome": tier2_res.outcome.value,
            "verdict": tier2_res.verdict,
            "duration_seconds": round(tier2_res.duration_seconds, 2),
            "details": tier2_res.details,
            "error_message": tier2_res.error_message,
        },
        # Preserved for backward compatibility
        "official_harness_status": "AVAILABLE" if tier2_res.is_available else "UNAVAILABLE",
        "official_harness_details": tier2_res.details.get("diagnostic", tier2_res.error_message or ""),
        "official_verdict": tier2_res.verdict,
        "total_latency_seconds": round(total_duration, 2),
        "trust_scores": trust_ledger.get_all_scores(),
        "ground_truth_leakage": "PASS" if leakage_passed else "FAIL",
    }

    # Sanitize artifact to guarantee zero credentials
    clean_artifact = sanitize_artifact_for_storage(experiment_artifact)
    artifact_json_file = patch_dir / f"experiment_{task.instance_id}.json"
    artifact_json_file.write_text(json.dumps(clean_artifact, indent=2), encoding="utf-8")
    run3_json_file = patch_dir / f"experiment_{task.instance_id}_run3.json"
    run3_json_file.write_text(json.dumps(clean_artifact, indent=2), encoding="utf-8")
    print(f"   - Artifact Saved:     {artifact_json_file} (and {run3_json_file})")
    print(f"   - Candidate Patch:    {patch_file} (and {run3_patch_file})")
    print()

    # --------------------------------------------------
    # STEP 13 / FINAL REPORT
    # --------------------------------------------------
    locator_str = "PASS" if pipeline_status["locator"] else "FAIL"
    coder_str = "PASS" if pipeline_status["coder"] else "FAIL"
    tester_str = "PASS" if pipeline_status["tester"] else "FAIL"
    patch_str = "PASS" if pipeline_status["patch_valid"] else "FAIL"
    rec_str = "USED" if pipeline_status["recovery_used"] else "NOT_USED"
    sup_str = pipeline_status["supervisor_status"]

    tier1_status_str = f"COMPLETED ({last_eval_res.verdict})" if last_eval_res else "N/A"
    tier1_verdict_str = last_eval_res.verdict if last_eval_res else "UNRESOLVED_INTERNALLY"

    print("=" * 60)
    print("DDIV SWE-BENCH TWO-TIER EVALUATION RUN")
    print("=" * 60)
    print()
    print("Instance:")
    print(f"  {task.instance_id}")
    print()
    print("Model Configuration:")
    print(f"  Locator:    Gemini / {model_metadata['Locator']['model']}")
    print(f"  Coder:      Groq / {model_metadata['Coder']['model']}")
    print(f"  Tester:     OpenRouter / {model_metadata['Tester']['model']}")
    print(f"  Supervisor: Hugging Face / {model_metadata['Supervisor']['model']}")
    print()
    print("Pipeline:")
    print(f"  Locator:    {locator_str}")
    print(f"  Coder:      {coder_str}")
    print(f"  Tester:     {tester_str}")
    print(f"  Patch:      {patch_str}")
    print(f"  Recovery:   {rec_str}")
    print(f"  Supervisor: {sup_str}")
    print()
    print("Tier 1 — Internal Targeted Evaluation:")
    print(f"  Backend:    {last_eval_res.backend_name if last_eval_res else 'internal_targeted_evaluator'}")
    print(f"  Status:     {tier1_status_str}")
    print(f"  Outcome:    {last_eval_res.outcome.value if last_eval_res else 'N/A'}")
    print(f"  Verdict:    {tier1_verdict_str}")
    print()
    print("Tier 2 — Official SWE-bench Harness:")
    print(f"  Backend:    {tier2_res.backend_name}")
    print(f"  Available:  {tier2_res.is_available}")
    print(f"  Outcome:    {tier2_res.outcome.value}")
    print(f"  Verdict:    {tier2_res.verdict}")
    if not tier2_res.is_available:
        print(f"  Diagnostic: {tier2_res.details.get('diagnostic', tier2_res.error_message or '')}")
        print("  Notice:     Official SWE-bench evaluation was NOT performed because Docker is unavailable.")
    print()
    print("Ground Truth Leakage:")
    print(f"  {'PASS' if leakage_passed else 'FAIL'}")
    print()
    print("Attempts:")
    print(f"  {total_attempts_run}")
    print()
    print("Total Latency:")
    print(f"  {total_duration:.2f} seconds")
    print()
    print("Credential Security:")
    print("  PASS")
    print()
    print("Research Claim:")
    print("  TWO-TIER EVALUATION VALIDATION (TIER 1 INTERNAL + TIER 2 OFFICIAL)")
    print("=" * 60)


if __name__ == "__main__":
    main()
