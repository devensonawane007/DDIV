"""Core workflow orchestrator and state machine for Baseline and DDIV modes."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base import AgentInputMetadata
from agents.coder import CoderAgent, CoderOutput
from agents.locator import LocatorAgent, LocatorOutput
from agents.supervisor import SupervisorAgent, SupervisorDecision
from agents.tester import TesterAgent, TesterOutput
from core.config import DDIVConfig, ExecutionMode
from core.events import EventType
from core.state import AgentRole, AttemptRecord, RunState, TaskStatus
from evaluation.patch_manager import PatchManager, PatchValidationResult
from evaluation.swebench_runner import SWEBenchRunner, TestExecutionResult
from evaluation.workspace import TaskWorkspace, WorkspaceManager
from logging_system.trace_logger import TraceEvent, TraceLogger
from memory.memory_store import MemoryStore
from memory.retrieval import MemoryRetriever
from memory.schemas import MemoryRecord
from memory.trust_ledger import TrustLedger
from models.registry import ModelRegistry
from recovery.diagnosis import DiagnosisEngine, DiagnosisReport
from recovery.failure_detector import FailureDetector, FailureType
from recovery.strategies import RecoveryAction, RecoveryStrategy, StrategySelector


class DDIVOrchestrator:
    """Orchestrates the multi-agent repair workflow across Baseline and DDIV modes."""

    def __init__(self, config: Optional[DDIVConfig] = None):
        self.config = config or DDIVConfig.load_from_env()

        # Component initialization
        self.model_registry = ModelRegistry(self.config)
        self.workspace_mgr = WorkspaceManager(self.config.workspace_root)
        self.patch_mgr = PatchManager()
        self.test_runner = SWEBenchRunner()
        self.failure_detector = FailureDetector()

        # Memory & Trust
        self.memory_store = MemoryStore(self.config.memory_db_path)
        self.memory_retriever = MemoryRetriever(self.memory_store)
        self.trust_ledger = TrustLedger(
            memory_store=self.memory_store,
            initial_trust={
                "Locator": self.config.init_trust_locator,
                "Coder": self.config.init_trust_coder,
                "Tester": self.config.init_trust_tester,
                "Supervisor": self.config.init_trust_supervisor,
            },
        )

        # Instantiate 4 Agents with identical models across modes
        self.locator = LocatorAgent(self.model_registry.get_provider_for_agent(self.config.locator))
        self.coder = CoderAgent(self.model_registry.get_provider_for_agent(self.config.coder))
        self.tester = TesterAgent(self.model_registry.get_provider_for_agent(self.config.tester))
        self.supervisor = SupervisorAgent(self.model_registry.get_provider_for_agent(self.config.supervisor))

    def run_task(
        self,
        task_id: str,
        issue_description: str,
        repository: str = "repo",
        base_commit: str = "HEAD",
        existing_workspace_path: Optional[Path] = None,
    ) -> RunState:
        """Execute a full task repair run."""
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        state = RunState(
            task_id=task_id,
            run_id=run_id,
            repository=repository,
            base_commit=base_commit,
            issue_description=issue_description,
            max_attempts=1 if self.config.mode == ExecutionMode.BASELINE else self.config.max_recovery_attempts,
        )

        logger = TraceLogger(run_id=run_id, task_id=task_id, log_dir=self.config.logs_dir)
        state.trust_snapshot = self.trust_ledger.get_all_scores()

        # Prepare isolated workspace
        workspace: Optional[TaskWorkspace] = None
        if existing_workspace_path and existing_workspace_path.exists():
            workspace = TaskWorkspace(workspace_path=existing_workspace_path, task_id=task_id, is_temp=False)
        else:
            workspace = self.workspace_mgr.create_workspace(task_id=task_id)
            if self.config.mode == ExecutionMode.MOCK or "mock" in task_id:
                self.workspace_mgr.provision_mock_task(workspace)

        try:
            self._execute_workflow(state, workspace, logger)
        finally:
            state.end_time = time.time()
            if workspace and workspace.is_temp:
                workspace.cleanup()

            # Record final summary trace
            initial_fail = state.attempt_history[0].failure_type if state.attempt_history else None
            final_diag = state.attempt_history[-1].diagnosis if state.attempt_history else None
            duration = (state.end_time or 0) - state.start_time

            logger.print_terminal_summary(
                task_id=task_id,
                mode=self.config.mode.value,
                attempts=len(state.attempt_history),
                resolved=state.is_resolved,
                initial_failure=initial_fail,
                final_diagnosis=final_diag,
                trust_scores=self.trust_ledger.get_all_scores(),
                duration=duration,
            )

        return state

    def _execute_workflow(self, state: RunState, workspace: TaskWorkspace, logger: TraceLogger) -> None:
        state.current_status = TaskStatus.TASK_LOADED

        recovery_action: Optional[RecoveryAction] = None

        while state.attempt <= state.max_attempts:
            attempt_idx = state.attempt

            # 1. Fault Localization
            if attempt_idx == 1 or (recovery_action and recovery_action.rerun_locator):
                self._step_locate(state, recovery_action, logger)

            # 2. Patch Synthesis
            self._step_code(state, recovery_action, logger)

            # 3. Test Review
            self._step_test_review(state, logger)

            # 4. Patch Application & Safe Verification
            test_res, patch_valid, patch_applied = self._step_verify(state, workspace, logger)

            # Record attempt snapshot
            record = AttemptRecord(
                attempt=attempt_idx,
                patch=state.current_patch,
                modified_files=state.modified_files,
                test_passed=test_res.passed,
                test_output=f"{test_res.raw_stdout}\n{test_res.raw_stderr}".strip(),
                coder_reasoning=state.test_results.get("coder_reasoning"),
                tester_assessment=state.test_results.get("tester_assessment"),
            )

            # Check outcome
            if test_res.passed and patch_applied:
                state.current_status = TaskStatus.SUCCESS
                state.is_resolved = True
                record.diagnosis = "All tests passed successfully."
                state.attempt_history.append(record)

                if self._is_trust_active():
                    self.trust_ledger.update_trust("Coder", state.task_id, attempt_idx, True, "Patch passed tests")
                    self.trust_ledger.update_trust("Locator", state.task_id, attempt_idx, True, "Correct localization")

                if self._is_memory_active():
                    self._save_memory(state, record, "SUCCESS")

                logger.log_event(
                    TraceEvent(
                        task_id=state.task_id,
                        run_id=state.run_id,
                        attempt=attempt_idx,
                        event_type=EventType.RUN_COMPLETED.value,
                        final_result="SUCCESS",
                        trust_snapshot=self.trust_ledger.get_all_scores(),
                    )
                )
                break

            # If tests failed
            state.current_status = TaskStatus.FAILURE_DETECTED

            # In Baseline mode, stop immediately after 1 attempt without supervisor intervention
            if self.config.mode == ExecutionMode.BASELINE:
                state.current_status = TaskStatus.FAILED
                record.failure_type = "UNRESOLVED_BASELINE"
                record.diagnosis = "Baseline mode does not perform recovery or retries."
                state.attempt_history.append(record)
                break

            # 5. DDIV Supervision, Diagnosis, and Intervention Selection
            state.current_status = TaskStatus.DIAGNOSING
            diagnosis_report, supervisor_dec = self._step_supervise_and_diagnose(
                state, record, test_res, patch_valid, patch_applied, logger
            )

            record.failure_type = diagnosis_report.final_failure_type.value if diagnosis_report.final_failure_type else "UNKNOWN"
            record.diagnosis = diagnosis_report.diagnosis_summary
            record.supervisor_reasoning = supervisor_dec.intervention_instructions

            # Update Trust scores based on failure evidence
            if self._is_trust_active():
                self._update_trust_on_failure(state, diagnosis_report, attempt_idx)

            # Record experience into SQLite memory
            if self._is_memory_active():
                self._save_memory(state, record, "FAILED")

            state.attempt_history.append(record)

            # Check termination criteria
            if not supervisor_dec.should_retry or attempt_idx >= state.max_attempts:
                state.current_status = TaskStatus.FAILED
                break

            # 6. Build targeted intervention for next attempt
            state.current_status = TaskStatus.RECOVERING
            recovery_action = self._step_plan_recovery(diagnosis_report, supervisor_dec, record)
            state.recovery_action = recovery_action.model_dump()
            record.recovery_action = recovery_action.strategy.value

            state.attempt += 1
            state.current_status = TaskStatus.RETRYING

        if not state.is_resolved:
            state.final_status = TaskStatus.FAILED
        else:
            state.final_status = TaskStatus.SUCCESS

    # =========================================================================
    # Step Implementations
    # =========================================================================

    def _step_locate(self, state: RunState, recovery: Optional[RecoveryAction], logger: TraceLogger) -> None:
        state.current_status = TaskStatus.LOCATING
        state.current_agent = AgentRole.LOCATOR

        memory_ctx = ""
        if self._is_memory_active():
            matches = self.memory_retriever.retrieve_context_for_supervisor(state.task_id, state.repository)
            memory_ctx = self.memory_retriever.format_matches_for_prompt(matches)

        input_data = {
            "issue": state.issue_description,
            "repo_structure": f"Repository: {state.repository}",
            "memory_context": memory_ctx,
            "recovery_guidance": recovery.guidance_for_locator if recovery else "",
        }

        meta = AgentInputMetadata(task_id=state.task_id, run_id=state.run_id, attempt=state.attempt)
        res = self.locator.execute(input_data, meta)
        state.total_tokens_used += res.total_tokens

        if res.success and res.output:
            state.located_files = res.output.relevant_files
            state.located_symbols = res.output.relevant_symbols
            state.current_status = TaskStatus.LOCATED

        logger.log_event(
            TraceEvent(
                task_id=state.task_id,
                run_id=state.run_id,
                attempt=state.attempt,
                agent_id="Locator",
                event_type=EventType.LOCATE_COMPLETED.value,
                input_summary=state.issue_description[:100],
                output_summary=f"Files: {state.located_files}, Confidence: {res.confidence}",
                latency_seconds=res.latency_seconds,
                token_usage={"total": res.total_tokens},
            )
        )

    def _step_code(self, state: RunState, recovery: Optional[RecoveryAction], logger: TraceLogger) -> None:
        state.current_status = TaskStatus.CODING
        state.current_agent = AgentRole.CODER

        prev_attempts_summary = ""
        if state.attempt_history:
            prev = state.attempt_history[-1]
            prev_attempts_summary = f"Attempt {prev.attempt} failed with {prev.failure_type}. Test trace:\n{prev.test_output[:500]}"

        input_data = {
            "issue": state.issue_description,
            "locator_result": {"relevant_files": state.located_files, "relevant_symbols": state.located_symbols},
            "source_files": f"Target files: {', '.join(state.located_files)}",
            "previous_attempts": prev_attempts_summary,
            "recovery_instructions": recovery.guidance_for_coder if recovery else "",
        }

        meta = AgentInputMetadata(task_id=state.task_id, run_id=state.run_id, attempt=state.attempt)
        res = self.coder.execute(input_data, meta)
        state.total_tokens_used += res.total_tokens

        if res.success and res.output:
            state.current_patch = res.output.patch
            state.modified_files = res.output.modified_files
            state.test_results["coder_reasoning"] = res.output.reasoning_summary
            state.current_status = TaskStatus.PATCH_GENERATED

        logger.log_event(
            TraceEvent(
                task_id=state.task_id,
                run_id=state.run_id,
                attempt=state.attempt,
                agent_id="Coder",
                event_type=EventType.PATCH_GENERATED.value,
                output_summary=f"Modified: {state.modified_files}, Patch len: {len(state.current_patch or '')}",
                latency_seconds=res.latency_seconds,
                token_usage={"total": res.total_tokens},
            )
        )

    def _step_test_review(self, state: RunState, logger: TraceLogger) -> None:
        state.current_status = TaskStatus.TEST_REVIEW
        state.current_agent = AgentRole.TESTER

        input_data = {
            "issue": state.issue_description,
            "candidate_patch": state.current_patch or "",
            "relevant_code": f"Files: {', '.join(state.located_files)}",
        }

        meta = AgentInputMetadata(task_id=state.task_id, run_id=state.run_id, attempt=state.attempt)
        res = self.tester.execute(input_data, meta)
        state.total_tokens_used += res.total_tokens

        if res.success and res.output:
            state.test_results["tester_assessment"] = res.output.assessment
            state.test_results["suspected_failures"] = res.output.suspected_failures
            state.test_results["recommended_tests"] = res.output.recommended_tests

        logger.log_event(
            TraceEvent(
                task_id=state.task_id,
                run_id=state.run_id,
                attempt=state.attempt,
                agent_id="Tester",
                event_type=EventType.TEST_REVIEW_COMPLETED.value,
                output_summary=f"Assessment: {getattr(res.output, 'assessment', '')[:100]}",
                latency_seconds=res.latency_seconds,
                token_usage={"total": res.total_tokens},
            )
        )

    def _step_verify(
        self, state: RunState, workspace: TaskWorkspace, logger: TraceLogger
    ) -> tuple[TestExecutionResult, bool, bool]:
        state.current_status = TaskStatus.VERIFYING

        # Revert any previous patch before applying new attempt
        self.patch_mgr.revert_workspace(workspace.path)

        # 1. Validate Patch format
        val_res: PatchValidationResult = self.patch_mgr.validate_patch(state.current_patch or "")
        if not val_res.is_valid:
            test_res = TestExecutionResult(
                passed=False,
                exit_code=-1,
                raw_stderr=f"Patch validation failed: {val_res.error_message}",
            )
            return test_res, False, False

        # 2. Apply patch to isolated workspace
        apply_res = self.patch_mgr.apply_patch(workspace.path, val_res.sanitized_patch)
        if not apply_res.is_success:
            test_res = TestExecutionResult(
                passed=False,
                exit_code=apply_res.exit_code,
                raw_stderr=f"Patch application failed: {apply_res.stderr}\n{apply_res.stdout}",
            )
            return test_res, True, False

        # 3. Execute tests inside isolated workspace
        test_res = self.test_runner.run_tests(workspace, timeout=self.config.subprocess_timeout)

        logger.log_event(
            TraceEvent(
                task_id=state.task_id,
                run_id=state.run_id,
                attempt=state.attempt,
                event_type=EventType.VERIFICATION_COMPLETED.value,
                tool_action="swebench_test_runner",
                tool_result=f"Passed: {test_res.passed}, Exit: {test_res.exit_code}",
                latency_seconds=test_res.duration_seconds,
            )
        )

        return test_res, True, True

    def _step_supervise_and_diagnose(
        self,
        state: RunState,
        record: AttemptRecord,
        test_res: TestExecutionResult,
        patch_valid: bool,
        patch_applied: bool,
        logger: TraceLogger,
    ) -> tuple[DiagnosisReport, SupervisorDecision]:
        state.current_agent = AgentRole.SUPERVISOR

        # Deterministic detection
        hist_dicts = [h.model_dump() for h in state.attempt_history]
        combined_output = f"{test_res.raw_stdout}\n{test_res.raw_stderr}"
        det_result = self.failure_detector.evaluate(
            patch_valid=patch_valid,
            patch_applied=patch_applied,
            test_passed=test_res.passed,
            test_output=combined_output,
            located_files=state.located_files,
            modified_files=state.modified_files,
            current_patch=state.current_patch or "",
            previous_attempts=hist_dicts,
        )

        # Retrieve memory matches
        memory_matches = []
        if self._is_memory_active():
            candidate_type = det_result.candidate_failure_type.value if det_result.candidate_failure_type else None
            memory_matches = self.memory_retriever.retrieve_context_for_supervisor(
                state.task_id, state.repository, candidate_type
            )
            state.memory_matches = memory_matches

        # Prompt Supervisor
        input_data = {
            "task_id": state.task_id,
            "max_attempts": state.max_attempts,
            "issue": state.issue_description,
            "locator_summary": f"Located files: {state.located_files}",
            "patch_summary": (state.current_patch or "")[:600],
            "patch_applied": patch_applied,
            "test_results": {"passed": test_res.passed, "failures": test_res.failures, "exit_code": test_res.exit_code},
            "deterministic_hints": det_result.evidence_reasons,
            "trust_scores": self.trust_ledger.get_all_scores(),
            "memory_matches": memory_matches,
            "attempt_history": hist_dicts,
        }

        meta = AgentInputMetadata(task_id=state.task_id, run_id=state.run_id, attempt=state.attempt)
        sup_res = self.supervisor.execute(input_data, meta)
        state.total_tokens_used += sup_res.total_tokens

        decision: SupervisorDecision
        if sup_res.success and sup_res.output:
            decision = sup_res.output
        else:
            # Fallback deterministic decision if Supervisor model output is unavailable
            candidate_ft = det_result.candidate_failure_type or FailureType.F2
            strat = StrategySelector.map_failure_to_strategy(candidate_ft)
            decision = SupervisorDecision(
                should_retry=(state.attempt < state.max_attempts),
                detected_failure=candidate_ft.value,
                diagnosis="; ".join(det_result.evidence_reasons) or "Execution verification failed.",
                recovery_strategy=strat.value,
                intervention_instructions="Analyze failed test trace and regenerate patch with corrected logic.",
                confidence=det_result.confidence,
            )

        diagnosis_report = DiagnosisEngine.synthesize(
            detection=det_result,
            supervisor_failure=decision.detected_failure,
            supervisor_diagnosis=decision.diagnosis,
            supervisor_recovery=decision.recovery_strategy,
            supervisor_confidence=decision.confidence,
        )

        state.diagnosis = diagnosis_report.model_dump()

        logger.log_event(
            TraceEvent(
                task_id=state.task_id,
                run_id=state.run_id,
                attempt=state.attempt,
                agent_id="Supervisor",
                event_type=EventType.DIAGNOSIS_COMPLETED.value,
                output_summary=f"Type: {diagnosis_report.final_failure_type}, Should Retry: {decision.should_retry}",
                failure=diagnosis_report.final_failure_type.value if diagnosis_report.final_failure_type else None,
                diagnosis=diagnosis_report.diagnosis_summary,
                recovery=decision.recovery_strategy,
                latency_seconds=sup_res.latency_seconds,
                token_usage={"total": sup_res.total_tokens},
            )
        )

        return diagnosis_report, decision

    def _step_plan_recovery(
        self,
        diagnosis: DiagnosisReport,
        decision: SupervisorDecision,
        record: AttemptRecord,
    ) -> RecoveryAction:
        ftype = diagnosis.final_failure_type or FailureType.F2
        strategy = StrategySelector.map_failure_to_strategy(ftype)

        if decision.recovery_strategy:
            try:
                strategy = RecoveryStrategy(decision.recovery_strategy)
            except ValueError:
                pass

        action = StrategySelector.build_action(
            strategy=strategy,
            diagnosis_text=diagnosis.diagnosis_summary,
            test_output=record.test_output,
            previous_patch=record.patch or "",
            supervisor_instructions=decision.intervention_instructions,
        )
        return action

    # =========================================================================
    # Trust and Memory Helpers
    # =========================================================================

    def _update_trust_on_failure(self, state: RunState, diagnosis: DiagnosisReport, attempt: int) -> None:
        ftype = diagnosis.final_failure_type
        if ftype == FailureType.F1:
            self.trust_ledger.update_trust(
                "Locator", state.task_id, attempt, False, "Localization failure (F1): wrong files identified"
            )
        elif ftype == FailureType.F2:
            self.trust_ledger.update_trust(
                "Coder", state.task_id, attempt, False, "Code reasoning failure (F2): patch failed assertions"
            )
        elif ftype == FailureType.F3:
            self.trust_ledger.update_trust(
                "Coder", state.task_id, attempt, False, "Execution/patch failure (F3): diff malformed or rejected"
            )
        elif ftype == FailureType.F4:
            self.trust_ledger.update_trust(
                "Supervisor", state.task_id, attempt, False, "Coordination failure (F4): strategy loop detected"
            )

    def _save_memory(self, state: RunState, record: AttemptRecord, result: str) -> None:
        mem = MemoryRecord(
            task_id=state.task_id,
            repository=state.repository,
            issue_summary=state.issue_description[:200],
            failure_type=record.failure_type,
            diagnosis=record.diagnosis,
            recovery_action=record.recovery_action,
            attempt=record.attempt,
            result=result,
            relevant_files=state.located_files,
            agent=state.current_agent.value if state.current_agent else None,
            trust_before=state.trust_snapshot.get("Coder"),
            trust_after=self.trust_ledger.get_score("Coder"),
        )
        try:
            self.memory_store.insert_record(mem)
        except Exception:
            pass

    def _is_trust_active(self) -> bool:
        mode = self.config.mode
        return mode in (ExecutionMode.DDIV, ExecutionMode.FULL_DDIV, ExecutionMode.TRUST_ONLY, ExecutionMode.MOCK)

    def _is_memory_active(self) -> bool:
        mode = self.config.mode
        return mode in (ExecutionMode.DDIV, ExecutionMode.FULL_DDIV, ExecutionMode.MEMORY_ONLY, ExecutionMode.MOCK)
