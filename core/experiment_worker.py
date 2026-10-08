"""Isolated child worker execution logic for a single task and experiment condition."""

from __future__ import annotations

import datetime
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base import AgentExecutionResult, AgentInputMetadata
from agents.coder import CoderAgent
from agents.locator import LocatorAgent
from agents.patch_critic import PatchCriticAgent, PatchCriticOutput
from agents.supervisor import SupervisorAgent, SupervisorDecision
from agents.tester import TesterAgent
from agents.test_understanding import RootCauseAnalysis, TestUnderstandingAgent
from core.conditions import ExperimentCondition
from core.config import DDIVConfig, ExecutionMode, ProviderType
from core.experiment_record import ConditionJobStatus, ExperimentConditionRecord
from evaluation.backends import (
    EvaluationOutcome,
    EvaluationResult,
    EvaluationTier,
    InternalSWEBenchBackend,
    OfficialSWEbenchBackend,
    TwoTierEvaluator,
)
from evaluation.command_runner import CommandRunner
from evaluation.context_builder import TargetedContext, TargetedContextBuilder
from evaluation.patch_builder import DeterministicPatchBuilder, PatchBuilderResult
from evaluation.patch_manager import PatchManager, PatchValidationResult
from evaluation.swebench_loader import SWEBenchLoader, SWEBenchRecord, SWEBenchTask
from evaluation.swebench_runner import SWEBenchRunner, TestExecutionResult
from evaluation.workspace import TaskWorkspace, WorkspaceManager
from recovery.failure_detector import DetectionResult, FailureDetector
from memory.memory_store import MemoryStore
from memory.retrieval import MemoryRetriever
from memory.schemas import MemoryRecord
from memory.trust_ledger import TrustLedger
from models.base import ModelConfig
from models.providers import MockModelProvider, OpenAICompatibleProvider
from models.registry import ModelRegistry


class ExperimentWorker:
    """Executes a single (task, condition) repair attempt inside an isolated workspace."""

    def __init__(
        self,
        task_id: str,
        condition: ExperimentCondition,
        experiment_id: str,
        workspace_root: str | Path,
        provider: str = "mock",
        dataset: Optional[str] = None,
        config: Optional[DDIVConfig] = None,
        log_file: Optional[str | Path] = None,
    ):
        self.task_id = task_id
        self.condition = condition
        self.experiment_id = experiment_id
        self.workspace_root = Path(workspace_root).resolve()
        self.provider = provider
        self.dataset = dataset or "swebench_verified"
        self.config = config or DDIVConfig.load_from_env()
        self.log_file = Path(log_file).resolve() if log_file else None

        # Map condition to config mode
        self.config.mode = self.condition.to_execution_mode()
        if self.provider == "real":
            self.config.provider_type = ProviderType.OPENAI_COMPATIBLE
        else:
            self.config.provider_type = ProviderType.MOCK

    def run(self) -> ExperimentConditionRecord:
        """Execute the end-to-end task condition run and return an independent result record."""
        start_time = time.time()
        start_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Load Task & Ground Truth
        loader = SWEBenchLoader()
        record: Optional[SWEBenchRecord] = None

        candidate_paths: List[Path] = []
        if self.dataset:
            p_user = Path(self.dataset)
            if p_user.is_file():
                candidate_paths.append(p_user.resolve())
            p_sub = Path("data/swebench") / self.dataset
            if p_sub.is_file():
                candidate_paths.append(p_sub.resolve())

        swe_dir = Path("data/swebench")
        candidate_paths.extend([
            swe_dir / "test-00000-of-00001.parquet",
            swe_dir / "princeton-nlp__SWE-bench_Verified-test.parquet",
        ])
        if swe_dir.exists():
            for ext in ("*.parquet", "*.jsonl", "*.json"):
                for f in sorted(swe_dir.glob(ext)):
                    if f.is_file():
                        candidate_paths.append(f.resolve())

        # Deduplicate paths while preserving discovery order
        seen_paths = set()
        unique_candidate_paths: List[Path] = []
        for cp in candidate_paths:
            if cp.exists() and cp not in seen_paths:
                seen_paths.add(cp)
                unique_candidate_paths.append(cp)

        for dataset_path in unique_candidate_paths:
            try:
                records = loader.load_from_file(dataset_path)
                for r in records:
                    if r.task.instance_id == self.task_id:
                        record = r
                        break
                if record is not None:
                    break
            except Exception:
                continue

        if record is None:
            if self.provider == "real":
                searched = [str(p) for p in unique_candidate_paths]
                raise ValueError(
                    f"Task '{self.task_id}' not found in any SWE-bench dataset files (searched: {searched}). "
                    f"Cannot run real experiment with fallback mock task."
                )
            # Fall back to loader mock or synthesizer for mock provider
            record = loader.get_mock_record(self.task_id)

        task: SWEBenchTask = record.task

        # 2. Setup Dedicated Workspaces for this worker
        ws_mgr = WorkspaceManager(base_workspace_dir=self.workspace_root)
        patch_mgr = PatchManager()
        cmd_runner = CommandRunner()
        swe_runner = SWEBenchRunner()

        agent_ws = ws_mgr.create_workspace(
            task_id=f"{task.instance_id}-agent",
            init_git=True,
            subfolder="agent_ws",
        )
        eval_ws = ws_mgr.create_workspace(
            task_id=f"{task.instance_id}-eval",
            init_git=True,
            subfolder="eval_ws",
        )

        # Checkout / provision repository
        if "mock" in self.task_id or (self.provider == "mock" and not Path(f"data/repos/{task.repo}").exists()):
            ws_mgr.provision_mock_task(agent_ws)
            ws_mgr.provision_mock_task(eval_ws)
        else:
            chk_agent = ws_mgr.checkout_repository(agent_ws, repo=task.repo, base_commit=task.base_commit, timeout=180)
            if not chk_agent.success:
                raise RuntimeError(
                    f"Failed to checkout agent repository {task.repo}@{task.base_commit}: {chk_agent.error}"
                )
            chk_eval = ws_mgr.checkout_repository(eval_ws, repo=task.repo, base_commit=task.base_commit, timeout=180)
            if not chk_eval.success:
                raise RuntimeError(
                    f"Failed to checkout eval repository {task.repo}@{task.base_commit}: {chk_eval.error}"
                )

        # Ensure pristine git state
        base_ref = task.base_commit if task.base_commit else "HEAD"
        ws_mgr.runner.run(["git", "reset", "--hard", base_ref], cwd=agent_ws.path)
        ws_mgr.runner.run(["git", "clean", "-fd"], cwd=agent_ws.path)
        ws_mgr.runner.run(["git", "reset", "--hard", base_ref], cwd=eval_ws.path)
        ws_mgr.runner.run(["git", "clean", "-fd"], cwd=eval_ws.path)

        # 3. Model Providers & Agents
        if self.provider == "mock":
            loc_prov = MockModelProvider(ModelConfig(name="Locator", model_id="mock-locator", provider="mock"))
            code_prov = MockModelProvider(ModelConfig(name="Coder", model_id="mock-coder", provider="mock"))
            test_prov = MockModelProvider(ModelConfig(name="Tester", model_id="mock-tester", provider="mock"))
            sup_prov = MockModelProvider(ModelConfig(name="Supervisor", model_id="mock-supervisor", provider="mock"))
            rca_prov = MockModelProvider(ModelConfig(name="TestUnderstanding", model_id="mock-rca", provider="mock"))
            critic_prov = MockModelProvider(ModelConfig(name="PatchCritic", model_id="mock-critic", provider="mock"))

            # Supply mock task defaults if task is pallets__flask-5014
            if task.instance_id == "pallets__flask-5014":
                custom_mock_responses = {
                    "Locator": {
                        "relevant_files": ["src/flask/blueprints.py"],
                        "relevant_symbols": ["Blueprint", "Blueprint.__init__"],
                        "reasoning_summary": "Located Blueprint in src/flask/blueprints.py",
                        "confidence": 0.95,
                    },
                    "Coder": {
                        "modifications": [
                            {
                                "path": "src/flask/blueprints.py",
                                "target_symbol": "Blueprint.__init__",
                                "operation": "insert_after",
                                "anchor": "root_path=root_path,\n        )",
                                "code": "        if not name:\n            raise ValueError(\"'name' may not be empty.\")\n",
                                "reason": "Raise ValueError if blueprint name is empty",
                            }
                        ],
                        "modified_files": ["src/flask/blueprints.py"],
                        "reasoning_summary": "Validate non-empty name in Blueprint.__init__",
                        "confidence": 0.95,
                    },
                    "Tester": {
                        "assessment": "Patch adds name validation guard",
                        "suspected_failures": [],
                        "recommended_tests": ["tests/test_blueprints.py::test_dotted_name_not_allowed"],
                        "confidence": 0.90,
                    },
                    "Supervisor": {
                        "should_retry": True,
                        "detected_failure": "F2",
                        "diagnosis": "Logic error in patch.",
                        "recovery_strategy": "A2",
                        "intervention_instructions": "Check edge cases.",
                        "avoid_previous_mistake": "Do not omit empty string check.",
                        "confidence": 0.85,
                    },
                    "TestUnderstanding": {
                        "root_cause": "Blueprint.__init__ permits empty name string, violating naming contract.",
                        "behavioral_contract": "Blueprint name must be non-empty string.",
                        "expected_behavior": "Raise ValueError on empty name.",
                        "current_behavior": "Silent initialization allowed.",
                        "relevant_symbols": ["Blueprint.__init__"],
                        "relevant_tests": ["tests/test_blueprints.py"],
                        "required_change": "Add check for non-empty name.",
                        "regression_risks": ["Breaking valid non-empty blueprint names."],
                    },
                    "PatchCritic": {
                        "approved": True,
                        "risk_level": "LOW",
                        "concerns": [],
                        "recommended_changes": [],
                        "reasoning": "Patch directly validates empty blueprint name as requested.",
                    },
                }
                loc_prov.custom_responses = custom_mock_responses
                code_prov.custom_responses = custom_mock_responses
                test_prov.custom_responses = custom_mock_responses
                sup_prov.custom_responses = custom_mock_responses
                rca_prov.custom_responses = custom_mock_responses
                critic_prov.custom_responses = custom_mock_responses
        else:
            self.config.validate_for_execution()
            registry = ModelRegistry(self.config)
            loc_prov = registry.get_provider_for_agent(self.config.locator)
            code_prov = registry.get_provider_for_agent(self.config.coder)
            test_prov = registry.get_provider_for_agent(self.config.tester)
            sup_prov = registry.get_provider_for_agent(self.config.supervisor)
            rca_prov = test_prov
            critic_prov = sup_prov

        locator = LocatorAgent(loc_prov)
        coder = CoderAgent(code_prov)
        tester = TesterAgent(test_prov)
        supervisor = SupervisorAgent(sup_prov)
        test_understanding = TestUnderstandingAgent(rca_prov)
        patch_critic = PatchCriticAgent(critic_prov)
        context_builder = TargetedContextBuilder(char_budget=10000)
        failure_detector = FailureDetector()
        patch_builder = DeterministicPatchBuilder(patch_mgr)

        # 4. Evaluation Backend & Subsystems
        two_tier = TwoTierEvaluator(
            internal_backend=InternalSWEBenchBackend(patch_manager=patch_mgr, command_runner=cmd_runner),
            official_backend=OfficialSWEbenchBackend(command_runner=cmd_runner),
        )

        # Clean-Base Health Check (executed ONCE per task before attempts)
        clean_base_health = two_tier.check_clean_base_health(eval_ws, record)
        print(f"[{task.instance_id}] Clean-Base Health Check: passed={clean_base_health.clean_base_passed} (error: {clean_base_health.error_message or 'None'})")

        memory_store = None
        memory_retriever = None
        if self.condition.is_memory_enabled:
            mem_db = self.workspace_root / "ddiv_memory.db"
            memory_store = MemoryStore(mem_db)
            memory_retriever = MemoryRetriever(memory_store)

        trust_ledger = None
        if self.condition.is_trust_enabled:
            trust_ledger = TrustLedger(
                memory_store=memory_store or MemoryStore(self.workspace_root / "trust_mem.db"),
                initial_trust={"Locator": 0.87, "Coder": 0.74, "Tester": 0.91, "Supervisor": 0.84},
            )

        # 5. Multi-attempt Execution Loop
        max_attempts = self.condition.max_attempts
        attempt = 1
        is_resolved = False
        final_patch = ""
        attempt_logs: List[Dict[str, Any]] = []
        last_eval_res: Optional[EvaluationResult] = None

        recovery_instructions = ""
        avoid_previous_mistake = ""
        last_candidate_patch = ""
        locator_guidance = ""
        prev_attempts_feedback: List[str] = []
        located_files: List[str] = []
        located_symbols: List[str] = []
        loc_res: Optional[AgentExecutionResult] = None

        # Discover repository files
        repo_files = []
        for p in agent_ws.path.glob("**/*.py"):
            if ".git" not in p.parts:
                repo_files.append(str(p.relative_to(agent_ws.path)).replace("\\", "/"))

        while attempt <= max_attempts and not is_resolved:
            print(f"[{task.instance_id}][{self.condition.value.upper()}] === Attempt {attempt}/{max_attempts} ===")
            meta = AgentInputMetadata(
                task_id=task.instance_id,
                run_id=f"worker_{self.experiment_id}_{task.instance_id}_{self.condition.value}_{int(time.time())}",
                attempt=attempt,
            )

            # Ensure clean workspaces before attempt
            patch_mgr.revert_workspace(agent_ws.path)
            patch_mgr.revert_workspace(eval_ws.path)

            # 5a. Locator
            if attempt == 1 or (self.condition.is_supervisor_enabled and (locator_guidance or not located_files)) or self.condition == ExperimentCondition.RETRY_ONLY:
                print(f"[{task.instance_id}] Running LocatorAgent...")
                loc_input = {
                    "issue": task.problem_statement,
                    "repo_structure": f"Repository: {task.repo}\nFiles:\n" + "\n".join(f" - {f}" for f in repo_files[:100]),
                    "recovery_guidance": locator_guidance if self.condition.is_intervention_enabled else "",
                }
                loc_res = locator.execute(loc_input, meta)
                if loc_res.success and loc_res.output:
                    located_files = getattr(loc_res.output, "relevant_files", [])
                    located_symbols = getattr(loc_res.output, "relevant_symbols", [])
                    print(f"[{task.instance_id}] Locator located: {located_files} (symbols: {located_symbols})")
                else:
                    print(f"[{task.instance_id}] Locator error: {loc_res.error}")

            # 5b. Targeted Context Building
            targeted_ctx: TargetedContext = context_builder.build_context(
                agent_ws.path,
                located_files,
                target_symbols=located_symbols,
            )
            source_code_context = targeted_ctx.formatted_source_code or "No source code available."
            repo_tests_context = targeted_ctx.formatted_tests_context or ""

            # 5c. Test Understanding & Root Cause Analysis (FULL_DDIV)
            rca_res = None
            rca_dict: Dict[str, Any] = {}
            if self.condition == ExperimentCondition.FULL_DDIV:
                print(f"[{task.instance_id}] Running TestUnderstandingAgent (RCA)...")
                rca_input = {
                    "issue": task.problem_statement,
                    "located_symbols": located_symbols,
                    "source_code": source_code_context,
                    "repo_tests": repo_tests_context,
                    "prior_failure_evidence": prev_attempts_feedback[-1] if prev_attempts_feedback else "",
                }
                rca_res = test_understanding.execute(rca_input, meta)
                if rca_res.success and rca_res.output:
                    rca_dict = rca_res.output.model_dump()
                    print(f"[{task.instance_id}] RCA: Contract: {rca_dict.get('behavioral_contract', '')[:90]}...")

            memory_context = ""
            if self.condition.is_memory_enabled and memory_retriever:
                matches = memory_retriever.retrieve_context_for_supervisor(
                    task_id=task.instance_id,
                    repository=task.repo,
                    current_failure_candidate=attempt_logs[-1].get("failure_category") if attempt_logs else None,
                    failed_tests=last_eval_res.details.get("failed_f2p_tests", []) if last_eval_res else None,
                    subsystem=located_files[0].split("/")[0] if located_files else None,
                )
                memory_context = memory_retriever.format_matches_for_prompt(matches)

            # 5d. Coder
            print(f"[{task.instance_id}] Running CoderAgent...")
            coder_input = {
                "issue": task.problem_statement,
                "locator_result": loc_res.output.model_dump() if (loc_res and loc_res.output) else {},
                "source_files": source_code_context,
                "test_understanding": rca_dict if self.condition == ExperimentCondition.FULL_DDIV else {},
                "repo_tests": repo_tests_context if self.condition == ExperimentCondition.FULL_DDIV else "",
                "memory_context": memory_context if self.condition.is_memory_enabled else "",
                "previous_attempts": "\n\n".join(prev_attempts_feedback[-2:]) if self.condition.is_intervention_enabled else "",
                "previous_patch": last_candidate_patch if (self.condition.is_intervention_enabled and attempt > 1) else "",
                "recovery_instructions": recovery_instructions if self.condition.is_intervention_enabled else "",
                "avoid_previous_mistake": avoid_previous_mistake if self.condition.is_intervention_enabled else "",
            }

            coder_res = coder.execute(coder_input, meta)
            candidate_patch = ""
            pb_ops: List[str] = []
            coder_proposals: List[Dict[str, Any]] = []
            coder_error_code: Optional[str] = None
            coder_error_msg: Optional[str] = None

            if coder_res.success and coder_res.output:
                mods = getattr(coder_res.output, "modifications", [])
                raw_patch = (getattr(coder_res.output, "patch", "") or "").strip()
                if mods:
                    coder_proposals = [m.model_dump() if hasattr(m, "model_dump") else dict(m) for m in mods]
                    pb_ops = [getattr(m, "operation", None) or m.get("operation", "unknown") for m in mods]
                    print(f"[{task.instance_id}] Coder provided {len(mods)} modification(s). Building deterministic patch...")
                    pb_res: PatchBuilderResult = patch_builder.build_patch(mods, agent_ws.path)
                    if pb_res.success:
                        candidate_patch = pb_res.unified_diff
                        print(f"[{task.instance_id}] Deterministic patch built successfully ({len(candidate_patch.splitlines())} diff lines)")
                    else:
                        print(f"[{task.instance_id}] PatchBuilder failed: {pb_res.error_message}. Falling back to raw patch.")
                        candidate_patch = raw_patch
                        if not candidate_patch:
                            coder_error_code = "PATCH_BUILDER_FAILED"
                            coder_error_msg = f"PatchBuilder failed: {pb_res.error_message}"
                elif raw_patch:
                    candidate_patch = raw_patch
                    print(f"[{task.instance_id}] Coder provided raw patch ({len(candidate_patch.splitlines())} diff lines)")
                else:
                    coder_error_code = "CODER_NO_VALID_MODIFICATION"
                    coder_error_msg = "Coder output returned valid JSON schema but both modifications and patch are empty."
                    print(f"[{task.instance_id}] Coder output empty: {coder_error_code}")
            else:
                coder_error_code = getattr(coder_res, "error_code", None) or "CODER_ERROR"
                coder_error_msg = coder_res.error or "Unknown Coder error"
                print(f"[{task.instance_id}] Coder error: [{coder_error_code}] {coder_error_msg}")

            if candidate_patch:
                final_patch = candidate_patch

            # 5e. Patch Critic (Non-blocking Diagnostic Advisory)
            critic_res = None
            critic_dict: Dict[str, Any] = {}
            if self.condition == ExperimentCondition.FULL_DDIV and candidate_patch:
                print(f"[{task.instance_id}] Running PatchCriticAgent (non-blocking)...")
                critic_input = {
                    "issue": task.problem_statement,
                    "patch_text": candidate_patch,
                    "changed_files": getattr(coder_res.output, "modified_files", []) if (coder_res and coder_res.output) else [],
                    "root_cause_analysis": rca_dict.get("root_cause", "") if rca_dict else "",
                    "prior_failure": prev_attempts_feedback[-1] if prev_attempts_feedback else "",
                }
                critic_res = patch_critic.execute(critic_input, meta)
                if critic_res.success and critic_res.output:
                    critic_dict = critic_res.output.model_dump()
                    print(f"[{task.instance_id}] PatchCritic: approved={critic_dict.get('approved')} (risk: {critic_dict.get('risk_level')})")

            # 5c. Validate Patch Structure
            val_res: PatchValidationResult = patch_mgr.validate_patch(candidate_patch)
            print(f"[{task.instance_id}] Patch valid: {val_res.is_valid} (error: {val_res.error_message or 'None'})")

            # 5d. Tester Review
            print(f"[{task.instance_id}] Running TesterAgent...")
            tester_input = {
                "issue": task.problem_statement,
                "candidate_patch": candidate_patch,
                "relevant_code": source_code_context,
            }
            tester_res = tester.execute(tester_input, meta)
            rec_tests = getattr(tester_res.output, "recommended_tests", []) if (tester_res and tester_res.output) else []
            print(f"[{task.instance_id}] Tester recommended tests: {rec_tests}")

            # 5e. Agent Workspace Test
            agent_apply_res = patch_mgr.apply_patch(agent_ws.path, val_res.sanitized_patch if val_res.is_valid else candidate_patch)
            agent_test_res: TestExecutionResult = TestExecutionResult(passed=False, raw_stdout="", raw_stderr="Patch not applied")
            if agent_apply_res.is_success:
                valid_targets = []
                for t in rec_tests:
                    if isinstance(t, str):
                        for token in t.strip().split():
                            clean_tok = token.strip("'\";,")
                            file_cand = clean_tok.split("::")[0]
                            if file_cand and file_cand.endswith(".py") and (agent_ws.path / file_cand).exists():
                                valid_targets.append(clean_tok)
                                break
                test_targets = valid_targets
                if not test_targets:
                    for lf in located_files:
                        fname = Path(lf).stem
                        for p in agent_ws.path.glob(f"**/test_{fname}*.py"):
                            rel_p = str(p.relative_to(agent_ws.path)).replace("\\", "/")
                            test_targets.append(rel_p)
                            break
                if not test_targets and "flask" in task.repo:
                    test_targets = ["tests/test_blueprints.py"]
                agent_test_res = swe_runner.run_task_at_base_commit(
                    agent_ws, task, test_targets=test_targets or None, timeout=60
                )
            print(f"[{task.instance_id}] Agent WS test status: {agent_test_res.status_label}")

            # 5f. Tier 1 Internal Evaluation (Clean eval_ws)
            print(f"[{task.instance_id}] Running Tier 1 Internal SWE-bench evaluation...")
            eval_res: EvaluationResult = two_tier.evaluate_internal(
                workspace=eval_ws,
                record=record,
                candidate_patch=val_res.sanitized_patch if val_res.is_valid else candidate_patch,
                clean_base_passed=clean_base_health.clean_base_passed,
                clean_base_error=clean_base_health.error_message,
            )
            last_eval_res = eval_res
            print(f"[{task.instance_id}] Tier 1 Verdict: {eval_res.verdict} (Resolved: {eval_res.outcome == EvaluationOutcome.RESOLVED})")

            # 5g. Objective Failure Detection
            det_res: DetectionResult = failure_detector.evaluate(
                patch_valid=val_res.is_valid,
                patch_applied=agent_apply_res.is_success,
                test_passed=(eval_res.outcome == EvaluationOutcome.RESOLVED),
                test_output=f"{eval_res.raw_output}\n{eval_res.details.get('failure_summary', '')}",
                located_files=located_files,
                modified_files=getattr(coder_res.output, "modified_files", []) if (coder_res and coder_res.output) else [],
                current_patch=candidate_patch,
                previous_attempts=attempt_logs,
                coder_error_code=coder_error_code,
                coder_error_detail=coder_error_msg,
                clean_base_passed=clean_base_health.clean_base_passed,
                f2p_passed=eval_res.details.get("all_f2p_passed"),
                p2p_passed=eval_res.details.get("all_p2p_passed"),
                failed_f2p_tests=eval_res.details.get("failed_f2p_tests", []),
                failed_p2p_tests=eval_res.details.get("failed_p2p_tests", []),
            )

            # Gather invocations, tokens, and timings for this attempt
            invocations = []
            att_prompt_tokens = 0
            att_comp_tokens = 0
            att_total_tokens = 0
            has_tokens = False

            if loc_res:
                invocations.append({
                    "agent": "Locator",
                    "model": getattr(loc_res, "model_id", "") or "",
                    "provider": getattr(loc_res, "provider", "") or "",
                    "prompt_tokens": loc_res.prompt_tokens,
                    "completion_tokens": loc_res.completion_tokens,
                    "total_tokens": loc_res.total_tokens,
                    "latency_seconds": loc_res.latency_seconds,
                })
                if loc_res.total_tokens > 0:
                    has_tokens = True
                    att_prompt_tokens += loc_res.prompt_tokens
                    att_comp_tokens += loc_res.completion_tokens
                    att_total_tokens += loc_res.total_tokens

            if rca_res:
                invocations.append({
                    "agent": "TestUnderstanding",
                    "model": getattr(rca_res, "model_id", "") or "",
                    "provider": getattr(rca_res, "provider", "") or "",
                    "prompt_tokens": rca_res.prompt_tokens,
                    "completion_tokens": rca_res.completion_tokens,
                    "total_tokens": rca_res.total_tokens,
                    "latency_seconds": rca_res.latency_seconds,
                })
                if rca_res.total_tokens > 0:
                    has_tokens = True
                    att_prompt_tokens += rca_res.prompt_tokens
                    att_comp_tokens += rca_res.completion_tokens
                    att_total_tokens += rca_res.total_tokens

            if coder_res:
                invocations.append({
                    "agent": "Coder",
                    "model": getattr(coder_res, "model_id", "") or "",
                    "provider": getattr(coder_res, "provider", "") or "",
                    "prompt_tokens": coder_res.prompt_tokens,
                    "completion_tokens": coder_res.completion_tokens,
                    "total_tokens": coder_res.total_tokens,
                    "latency_seconds": coder_res.latency_seconds,
                })
                if coder_res.total_tokens > 0:
                    has_tokens = True
                    att_prompt_tokens += coder_res.prompt_tokens
                    att_comp_tokens += coder_res.completion_tokens
                    att_total_tokens += coder_res.total_tokens

            if critic_res:
                invocations.append({
                    "agent": "PatchCritic",
                    "model": getattr(critic_res, "model_id", "") or "",
                    "provider": getattr(critic_res, "provider", "") or "",
                    "prompt_tokens": critic_res.prompt_tokens,
                    "completion_tokens": critic_res.completion_tokens,
                    "total_tokens": critic_res.total_tokens,
                    "latency_seconds": critic_res.latency_seconds,
                })
                if critic_res.total_tokens > 0:
                    has_tokens = True
                    att_prompt_tokens += critic_res.prompt_tokens
                    att_comp_tokens += critic_res.completion_tokens
                    att_total_tokens += critic_res.total_tokens

            if tester_res:
                invocations.append({
                    "agent": "Tester",
                    "model": getattr(tester_res, "model_id", "") or "",
                    "provider": getattr(tester_res, "provider", "") or "",
                    "prompt_tokens": tester_res.prompt_tokens,
                    "completion_tokens": tester_res.completion_tokens,
                    "total_tokens": tester_res.total_tokens,
                    "latency_seconds": tester_res.latency_seconds,
                })
                if tester_res.total_tokens > 0:
                    has_tokens = True
                    att_prompt_tokens += tester_res.prompt_tokens
                    att_comp_tokens += tester_res.completion_tokens
                    att_total_tokens += tester_res.total_tokens

            agent_timings = {
                "locator": loc_res.latency_seconds if loc_res else 0.0,
                "coder": coder_res.latency_seconds if coder_res else 0.0,
                "tester": tester_res.latency_seconds if tester_res else 0.0,
                "supervisor": 0.0,
            }

            attempt_snapshot = {
                "attempt": attempt,
                "coder_proposals": coder_proposals,
                "patch_operations": pb_ops,
                "generated_patch": candidate_patch,
                "patch_generated": bool(candidate_patch.strip()),
                "patch_valid": val_res.is_valid,
                "patch_validation_error": val_res.error_message,
                "coder_error_code": coder_error_code,
                "coder_error_detail": coder_error_msg,
                "agent_apply_success": agent_apply_res.is_success,
                "agent_test_status": agent_test_res.status_label,
                "internal_resolved": (eval_res.outcome == EvaluationOutcome.RESOLVED),
                "verdict": eval_res.verdict,
                "f2p_passed": eval_res.details.get("all_f2p_passed", False),
                "p2p_passed": eval_res.details.get("all_p2p_passed", False),
                "failed_f2p_tests": eval_res.details.get("failed_f2p_tests", []),
                "failed_p2p_tests": eval_res.details.get("failed_p2p_tests", []),
                "final_patch_correct": (eval_res.outcome == EvaluationOutcome.RESOLVED) if val_res.is_valid else False,
                "regression_detected": bool(val_res.is_valid and agent_apply_res.is_success and not eval_res.details.get("all_p2p_passed", True)),
                "located_files": located_files,
                "latency_seconds": eval_res.duration_seconds,
                "agent_timings": agent_timings,
                "token_usage": {
                    "prompt_tokens": att_prompt_tokens,
                    "completion_tokens": att_comp_tokens,
                    "total_tokens": att_total_tokens,
                } if has_tokens else None,
                "model_invocations": invocations,
                "context_characters": targeted_ctx.character_size,
                "root_cause_analysis": rca_dict if rca_dict else None,
                "patch_critic": critic_dict if critic_dict else None,
                "failure_detector": det_res.model_dump(),
                "memory_retrieved": bool(memory_context),
            }

            if eval_res.outcome == EvaluationOutcome.RESOLVED:
                is_resolved = True
                if self.condition.is_trust_enabled and trust_ledger:
                    trust_ledger.update_trust("Coder", task.instance_id, attempt, True, "Patch passed internal tests")
                    trust_ledger.update_trust("Locator", task.instance_id, attempt, True, "Correct localization")
                if self.condition.is_memory_enabled and memory_store:
                    memory_store.insert_record(
                        MemoryRecord(
                            task_id=task.instance_id,
                            repository=task.repo,
                            issue_summary=task.problem_statement[:200],
                            failure_type="NONE",
                            diagnosis="Resolved successfully",
                            recovery_action="NONE",
                            attempt=attempt,
                            result="SUCCESS",
                            relevant_files=located_files,
                            agent="Coder",
                        )
                    )
                attempt_logs.append(attempt_snapshot)
                break

            # If not resolved: check condition policy
            if self.condition == ExperimentCondition.BASELINE:
                # Baseline terminates immediately after Attempt 1 without Supervisor intervention
                attempt_snapshot["supervisor_diagnosis"] = "Baseline mode does not perform recovery or retries."
                attempt_snapshot["should_retry"] = False
                attempt_logs.append(attempt_snapshot)
                break

            elif self.condition == ExperimentCondition.RETRY_ONLY:
                # Blind retry: re-execute from clean attempt state up to max_attempts without supervisor/diagnosis/intervention
                if attempt < max_attempts:
                    attempt_snapshot["failure_category"] = "UNRESOLVED_RETRY"
                    attempt_snapshot["recovery_strategy"] = "BLIND_RETRY"
                    attempt_snapshot["supervisor_diagnosis"] = "Blind retry mode: rerunning repair workflow from clean attempt state without supervisor intervention."
                    attempt_snapshot["supervisor_instructions"] = ""
                    attempt_snapshot["should_retry"] = True
                    attempt_logs.append(attempt_snapshot)
                    attempt += 1
                    continue
                else:
                    attempt_snapshot["failure_category"] = "UNRESOLVED_RETRY"
                    attempt_snapshot["recovery_strategy"] = "BLIND_RETRY"
                    attempt_snapshot["supervisor_diagnosis"] = "Maximum attempts reached (blind retry exhausted)."
                    attempt_snapshot["supervisor_instructions"] = ""
                    attempt_snapshot["should_retry"] = False
                    attempt_logs.append(attempt_snapshot)
                    break

            elif self.condition == ExperimentCondition.FULL_DDIV:
                # Supervisor Recovery for FULL_DDIV
                if attempt < max_attempts:
                    coder_err_repr = f" [{coder_error_code}] {coder_error_msg}" if coder_error_code else ""
                    sup_input = {
                        "task_id": task.instance_id,
                        "max_attempts": max_attempts,
                        "issue": task.problem_statement,
                        "locator_summary": f"Located files: {located_files}, symbols: {located_symbols}",
                        "coder_summary": f"Patch valid: {val_res.is_valid}, applied: {agent_apply_res.is_success}{coder_err_repr}",
                        "tester_summary": f"Assessment: {getattr(tester_res.output, 'assessment', 'None')}",
                        "verification_summary": f"Agent WS: {agent_test_res.status_label}, Internal: {eval_res.verdict}",
                        "objective_detector_result": det_res.model_dump(),
                        "failed_f2p_tests": eval_res.details.get("failed_f2p_tests", []),
                        "failed_p2p_tests": eval_res.details.get("failed_p2p_tests", []),
                        "traceback": eval_res.details.get("traceback", ""),
                        "attempt_history": [
                            {
                                "attempt": attempt,
                                "patch_valid": val_res.is_valid,
                                "coder_error_code": coder_error_code,
                                "error": coder_error_msg or val_res.error_message or agent_apply_res.stderr or "Tests failed",
                            }
                        ],
                        "trust_scores": trust_ledger.get_all_scores() if trust_ledger else {},
                    }
                    print(f"[{task.instance_id}] Running SupervisorAgent (FULL_DDIV recovery)...")
                    sup_res = supervisor.execute(sup_input, meta)
                    if sup_res.success and sup_res.output:
                        dec: SupervisorDecision = sup_res.output
                        print(f"[{task.instance_id}] Supervisor diagnosed {dec.detected_failure} -> strategy {dec.recovery_strategy} (retry={dec.should_retry})")
                        print(f"[{task.instance_id}] Supervisor diagnosis: {dec.diagnosis}")
                        print(f"[{task.instance_id}] Supervisor instructions: {dec.intervention_instructions}")
                        print(f"[{task.instance_id}] Supervisor avoid: {dec.avoid_previous_mistake}")
                        attempt_snapshot["failure_category"] = dec.detected_failure
                        attempt_snapshot["recovery_strategy"] = dec.recovery_strategy
                        attempt_snapshot["supervisor_diagnosis"] = dec.diagnosis
                        attempt_snapshot["supervisor_instructions"] = dec.intervention_instructions
                        attempt_snapshot["avoid_previous_mistake"] = dec.avoid_previous_mistake
                        attempt_snapshot["should_retry"] = dec.should_retry

                        attempt_snapshot["agent_timings"]["supervisor"] = sup_res.latency_seconds
                        attempt_snapshot["model_invocations"].append({
                            "agent": "Supervisor",
                            "model": getattr(sup_res, "model_id", "") or "",
                            "provider": getattr(sup_res, "provider", "") or "",
                            "prompt_tokens": sup_res.prompt_tokens,
                            "completion_tokens": sup_res.completion_tokens,
                            "total_tokens": sup_res.total_tokens,
                            "latency_seconds": sup_res.latency_seconds,
                        })
                        if sup_res.total_tokens > 0:
                            toks = attempt_snapshot.get("token_usage") or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                            toks["prompt_tokens"] += sup_res.prompt_tokens
                            toks["completion_tokens"] += sup_res.completion_tokens
                            toks["total_tokens"] += sup_res.total_tokens
                            attempt_snapshot["token_usage"] = toks

                        recovery_instructions = dec.intervention_instructions
                        avoid_previous_mistake = dec.avoid_previous_mistake
                        last_candidate_patch = candidate_patch
                        if dec.detected_failure == "F1" or dec.recovery_strategy == "A1" or not located_files:
                            locator_guidance = dec.intervention_instructions
                        prev_attempts_feedback.append(
                            f"Attempt {attempt} failed ({dec.detected_failure}): {dec.diagnosis}. Directive: {dec.avoid_previous_mistake}"
                        )

                        is_regression = (eval_res.details.get("all_p2p_passed") is False or bool(eval_res.details.get("failed_p2p_tests")))
                        if self.condition.is_trust_enabled and trust_ledger:
                            trust_ledger.update_trust(
                                "Coder",
                                task.instance_id,
                                attempt,
                                False,
                                f"Failed: {dec.detected_failure}",
                                is_regression=is_regression,
                            )
                            if dec.detected_failure == "F1" or dec.recovery_strategy == "A1":
                                trust_ledger.update_trust(
                                    "Locator",
                                    task.instance_id,
                                    attempt,
                                    False,
                                    f"Faulty localization: {dec.detected_failure}",
                                )

                        if self.condition.is_memory_enabled and memory_store:
                            memory_store.insert_record(
                                MemoryRecord(
                                    task_id=task.instance_id,
                                    repository=task.repo,
                                    issue_summary=task.problem_statement[:200],
                                    failure_type=dec.detected_failure,
                                    failure_evidence=det_res.evidence_reasons,
                                    previous_patch=candidate_patch,
                                    failed_tests=eval_res.details.get("failed_f2p_tests", []) + eval_res.details.get("failed_p2p_tests", []),
                                    subsystem=located_files[0].split("/")[0] if located_files else None,
                                    diagnosis=dec.diagnosis,
                                    recovery_action=dec.recovery_strategy,
                                    attempt=attempt,
                                    result="FAILED",
                                    relevant_files=located_files,
                                    agent="Supervisor",
                                    metadata={
                                        "avoid_previous_mistake": dec.avoid_previous_mistake,
                                        "granular_failure_type": det_res.granular_failure_type.value if det_res.granular_failure_type else None,
                                        "is_regression": is_regression,
                                    },
                                )
                            )

                        attempt_logs.append(attempt_snapshot)
                        if not dec.should_retry:
                            break
                    else:
                        attempt_snapshot["supervisor_error"] = sup_res.error
                        attempt_logs.append(attempt_snapshot)
                        break
                else:
                    attempt_snapshot["supervisor_diagnosis"] = "Maximum attempts reached."
                    attempt_snapshot["should_retry"] = False
                    attempt_logs.append(attempt_snapshot)

                attempt += 1

        # 6. Tier 2 Official SWE-bench Evaluation Probe
        tier2_res: EvaluationResult = two_tier.evaluate_official(
            record=record,
            candidate_patch=final_patch,
        )

        total_duration = time.time() - start_time
        completed_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Save patch file to workspace
        patch_file_path = self.workspace_root / f"{task.instance_id}__{self.condition.value}.patch"
        patch_file_path.write_text(final_patch, encoding="utf-8")

        # 7. Compute Evaluation Metrics & Failure Detection
        from core.metrics import compute_task_metrics, compute_task_failure_detection

        task_metrics = compute_task_metrics({
            "condition": self.condition.value,
            "resolved": is_resolved,
            "attempts": len(attempt_logs),
            "attempt_history": attempt_logs,
            "execution_duration_seconds": total_duration,
        })
        task_failure_det = compute_task_failure_detection({
            "attempt_history": attempt_logs,
        })

        record_obj = ExperimentConditionRecord(
            experiment_id=self.experiment_id,
            task_id=self.task_id,
            condition=self.condition,
            status=ConditionJobStatus.COMPLETED,
            resolved=is_resolved,
            pass_at_1=task_metrics.pass_at_1,
            attempts=len(attempt_logs),
            attempt_history=attempt_logs,
            candidate_patch=final_patch,
            candidate_patch_path=str(patch_file_path),
            metrics=task_metrics.model_dump(),
            failure_detection=task_failure_det.model_dump() if task_failure_det else None,
            internal_evaluation={
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
            official_evaluation={
                "tier": EvaluationTier.TIER_2_OFFICIAL.value,
                "backend_name": tier2_res.backend_name,
                "available": tier2_res.is_available,
                "outcome": tier2_res.outcome.value,
                "verdict": tier2_res.verdict,
                "duration_seconds": round(tier2_res.duration_seconds, 2),
                "details": tier2_res.details,
                "error_message": tier2_res.error_message,
            },
            trust_scores=trust_ledger.get_all_scores() if trust_ledger else None,
            execution_duration_seconds=round(total_duration, 2),
            worker_pid=os.getpid(),
            worker_exit_code=0,
            log_file_path=str(self.log_file) if self.log_file else "",
            workspace_path=str(self.workspace_root),
            error_message=None,
            started_at=start_iso,
            completed_at=completed_iso,
        )

        return record_obj
