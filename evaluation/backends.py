"""Two-tier evaluation backend abstraction for DDIV.

Enforces formal separation between:
- Tier 1: Internal Targeted Evaluator (clean evaluation workspace, pytest FAIL_TO_PASS + PASS_TO_PASS)
- Tier 2: Authoritative Official SWE-bench Harness (Docker containerized evaluation via swebench)
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from evaluation.command_runner import CommandRunner, CommandResult
from evaluation.patch_manager import PatchManager
from evaluation.swebench_evaluator import (
    CleanBaseHealthResult,
    InternalEvaluationResult,
    InternalSWEBenchEvaluator,
    OfficialHarnessChecker,
    OfficialHarnessStatus,
)
from evaluation.swebench_loader import SWEBenchRecord
from evaluation.workspace import TaskWorkspace


class EvaluationTier(str, Enum):
    """Formal tier classification for evaluation backends."""

    TIER_1_INTERNAL = "tier_1_internal"
    TIER_2_OFFICIAL = "tier_2_official"


class EvaluationOutcome(str, Enum):
    """Normalized evaluation outcome across backends."""

    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    OFFICIAL_HARNESS_UNAVAILABLE = "OFFICIAL_HARNESS_UNAVAILABLE"
    ERROR = "ERROR"


class EvaluationResult(BaseModel):
    """Unified, strongly-typed result from an evaluation backend."""

    backend_name: str
    tier: EvaluationTier
    task_id: str
    is_available: bool = True
    outcome: EvaluationOutcome
    verdict: str  # e.g. "RESOLVED_INTERNALLY", "RESOLVED_OFFICIAL", "OFFICIAL_HARNESS_UNAVAILABLE"
    duration_seconds: float = 0.0
    details: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    raw_output: str = ""


class EvaluationBackend(ABC):
    """Abstract interface for all DDIV evaluation backends."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Unique identifier name for this backend."""
        pass

    @property
    @abstractmethod
    def tier(self) -> EvaluationTier:
        """Evaluation tier classification."""
        pass

    @abstractmethod
    def check_availability(self) -> Dict[str, Any]:
        """Probe environment prerequisites required for this backend."""
        pass

    @abstractmethod
    def evaluate(
        self,
        record: SWEBenchRecord,
        candidate_patch: str,
        workspace: Optional[TaskWorkspace] = None,
        timeout: int = 180,
    ) -> EvaluationResult:
        """Execute evaluation of candidate patch against ground truth."""
        pass


class InternalSWEBenchBackend(EvaluationBackend):
    """Tier 1: Internal targeted evaluator executing tests in a clean evaluation workspace.

    Provides rapid, attempt-level feedback for multi-agent recovery without requiring Docker.
    Verdicts: RESOLVED_INTERNALLY / UNRESOLVED_INTERNALLY.
    """

    def __init__(
        self,
        patch_manager: Optional[PatchManager] = None,
        command_runner: Optional[CommandRunner] = None,
    ):
        self.patch_mgr = patch_manager or PatchManager()
        self.runner = command_runner or CommandRunner()
        self.evaluator = InternalSWEBenchEvaluator(
            patch_manager=self.patch_mgr,
            command_runner=self.runner,
        )

    @property
    def backend_name(self) -> str:
        return "internal_targeted_evaluator"

    @property
    def tier(self) -> EvaluationTier:
        return EvaluationTier.TIER_1_INTERNAL

    def check_availability(self) -> Dict[str, Any]:
        has_pytest = bool(shutil.which("pytest"))
        return {
            "available": True,
            "pytest_available": has_pytest,
            "details": "Internal targeted evaluator is ready for pristine workspace execution.",
        }

    def evaluate(
        self,
        record: SWEBenchRecord,
        candidate_patch: str,
        workspace: Optional[TaskWorkspace] = None,
        timeout: int = 180,
        clean_base_passed: bool = True,
        clean_base_error: Optional[str] = None,
    ) -> EvaluationResult:
        if workspace is None:
            return EvaluationResult(
                backend_name=self.backend_name,
                tier=self.tier,
                task_id=record.task.instance_id,
                is_available=True,
                outcome=EvaluationOutcome.ERROR,
                verdict="UNRESOLVED_INTERNALLY (No evaluation workspace provided)",
                error_message="Internal targeted evaluation requires a valid pristine TaskWorkspace.",
            )

        start_time = time.time()
        res: InternalEvaluationResult = self.evaluator.evaluate_candidate_patch(
            workspace=workspace,
            record=record,
            candidate_patch=candidate_patch,
            timeout=timeout,
            clean_base_passed=clean_base_passed,
            clean_base_error=clean_base_error,
        )
        duration = time.time() - start_time

        outcome = EvaluationOutcome.RESOLVED if res.internal_resolved else EvaluationOutcome.UNRESOLVED

        return EvaluationResult(
            backend_name=self.backend_name,
            tier=self.tier,
            task_id=record.task.instance_id,
            is_available=True,
            outcome=outcome,
            verdict=res.evaluation_verdict,
            duration_seconds=duration,
            details={
                "candidate_patch_applied": res.candidate_patch_applied,
                "candidate_patch_error": res.candidate_patch_error,
                "test_patch_applied": res.test_patch_applied,
                "test_patch_error": res.test_patch_error,
                "fail_to_pass_results": res.fail_to_pass_results,
                "pass_to_pass_results": res.pass_to_pass_results,
                "all_f2p_passed": res.all_f2p_passed,
                "all_p2p_passed": res.all_p2p_passed,
                "internal_resolved": res.internal_resolved,
                "failed_f2p_tests": res.failed_f2p_tests,
                "failed_p2p_tests": res.failed_p2p_tests,
                "failure_type": res.failure_type,
                "failure_summary": res.failure_summary,
                "traceback": res.traceback,
                "likely_files": res.likely_files,
                "likely_symbols": res.likely_symbols,
                "clean_base_passed": res.clean_base_passed,
                "clean_base_error": res.clean_base_error,
            },
            raw_output=f"{res.raw_stdout}\n{res.raw_stderr}".strip(),
        )

    def check_clean_base_health(
        self,
        workspace: TaskWorkspace,
        record: SWEBenchRecord,
        max_p2p_tests: int = 5,
        timeout: int = 60,
    ) -> CleanBaseHealthResult:
        """Run clean base health check once before attempt loop."""
        return self.evaluator.check_clean_base_health(
            workspace=workspace,
            record=record,
            max_p2p_tests=max_p2p_tests,
            timeout=timeout,
        )


class OfficialSWEbenchBackend(EvaluationBackend):
    """Tier 2: Authoritative SWE-bench evaluation harness running in Docker containers.

    Requires Docker daemon and the 'swebench' python package.
    If prerequisites are missing, strictly returns OFFICIAL_HARNESS_UNAVAILABLE.
    Never substitutes internal evaluation results for official results.
    """

    def __init__(
        self,
        command_runner: Optional[CommandRunner] = None,
        harness_checker: Optional[OfficialHarnessChecker] = None,
    ):
        self.runner = command_runner or CommandRunner()
        self.checker = harness_checker or OfficialHarnessChecker(self.runner)

    @property
    def backend_name(self) -> str:
        return "official_swebench_harness"

    @property
    def tier(self) -> EvaluationTier:
        return EvaluationTier.TIER_2_OFFICIAL

    def check_availability(self) -> Dict[str, Any]:
        status: OfficialHarnessStatus = self.checker.check_harness_availability()
        return {
            "available": status.available,
            "docker_available": status.docker_available,
            "swebench_package_available": status.swebench_package_available,
            "details": status.details,
        }

    def evaluate(
        self,
        record: SWEBenchRecord,
        candidate_patch: str,
        workspace: Optional[TaskWorkspace] = None,
        timeout: int = 600,
    ) -> EvaluationResult:
        task_id = record.task.instance_id
        avail = self.check_availability()

        if not avail["available"]:
            return EvaluationResult(
                backend_name=self.backend_name,
                tier=self.tier,
                task_id=task_id,
                is_available=False,
                outcome=EvaluationOutcome.OFFICIAL_HARNESS_UNAVAILABLE,
                verdict="OFFICIAL_HARNESS_UNAVAILABLE",
                duration_seconds=0.0,
                details={
                    "docker_available": avail["docker_available"],
                    "swebench_package_available": avail["swebench_package_available"],
                    "diagnostic": avail["details"],
                    "resolution_claim": "NOT_EVALUATED",
                },
                error_message=avail["details"],
                raw_output="",
            )

        # When Docker & swebench are available, invoke official harness
        start_time = time.time()
        with tempfile.TemporaryDirectory() as td:
            pred_file = Path(td) / "predictions.json"
            pred_data = [
                {
                    "instance_id": task_id,
                    "model_patch": candidate_patch,
                    "model_name_or_path": "DDIV",
                }
            ]
            pred_file.write_text(json.dumps(pred_data, indent=2), encoding="utf-8")
            run_id = f"eval_{task_id}_{int(time.time())}"

            cmd = [
                sys.executable,
                "-m",
                "swebench.harness.run_evaluation",
                "--dataset_name",
                "princeton-nlp/SWE-bench_Verified",
                "--predictions_path",
                str(pred_file),
                "--run_id",
                run_id,
                "--max_workers",
                "1",
            ]

            cmd_res: CommandResult = self.runner.run(cmd=cmd, cwd=td, timeout=timeout)
            duration = time.time() - start_time

            # Parse official evaluation output
            report_file = Path(td) / f"{run_id}.json"
            resolved = False
            details: Dict[str, Any] = {
                "exit_code": cmd_res.exit_code,
                "stdout_snippet": cmd_res.stdout[:500],
            }

            if report_file.exists():
                try:
                    report = json.loads(report_file.read_text(encoding="utf-8"))
                    resolved_instances = report.get("resolved_instances", [])
                    resolved = task_id in resolved_instances
                    details["official_report"] = report
                except Exception as parse_err:
                    details["report_parse_error"] = str(parse_err)

            outcome = EvaluationOutcome.RESOLVED if resolved else EvaluationOutcome.UNRESOLVED
            verdict = "RESOLVED_OFFICIAL" if resolved else "UNRESOLVED_OFFICIAL"

            return EvaluationResult(
                backend_name=self.backend_name,
                tier=self.tier,
                task_id=task_id,
                is_available=True,
                outcome=outcome,
                verdict=verdict,
                duration_seconds=duration,
                details=details,
                raw_output=f"{cmd_res.stdout}\n{cmd_res.stderr}".strip(),
            )


class TwoTierEvaluator:
    """Coordinator orchestrating Tier 1 Internal Evaluation and Tier 2 Official Verification."""

    def __init__(
        self,
        internal_backend: Optional[EvaluationBackend] = None,
        official_backend: Optional[EvaluationBackend] = None,
    ):
        self.internal_backend = internal_backend or InternalSWEBenchBackend()
        self.official_backend = official_backend or OfficialSWEbenchBackend()

    def evaluate_internal(
        self,
        record: SWEBenchRecord,
        candidate_patch: str,
        workspace: TaskWorkspace,
        timeout: int = 180,
        clean_base_passed: bool = True,
        clean_base_error: Optional[str] = None,
    ) -> EvaluationResult:
        """Execute Tier 1 internal evaluation on pristine evaluation workspace."""
        if hasattr(self.internal_backend, "evaluate"):
            return self.internal_backend.evaluate(
                record=record,
                candidate_patch=candidate_patch,
                workspace=workspace,
                timeout=timeout,
                clean_base_passed=clean_base_passed,
                clean_base_error=clean_base_error,
            )
        return self.internal_backend.evaluate(
            record=record,
            candidate_patch=candidate_patch,
            workspace=workspace,
            timeout=timeout,
        )

    def check_clean_base_health(
        self,
        workspace: TaskWorkspace,
        record: SWEBenchRecord,
        max_p2p_tests: int = 5,
        timeout: int = 60,
    ) -> CleanBaseHealthResult:
        """Execute clean base health check on pristine evaluation workspace once before attempts."""
        if hasattr(self.internal_backend, "check_clean_base_health"):
            return self.internal_backend.check_clean_base_health(
                workspace=workspace,
                record=record,
                max_p2p_tests=max_p2p_tests,
                timeout=timeout,
            )
        return CleanBaseHealthResult(task_id=record.task.instance_id, clean_base_passed=True)

    def evaluate_official(
        self,
        record: SWEBenchRecord,
        candidate_patch: str,
        timeout: int = 600,
    ) -> EvaluationResult:
        """Execute Tier 2 official SWE-bench evaluation."""
        return self.official_backend.evaluate(
            record=record,
            candidate_patch=candidate_patch,
            timeout=timeout,
        )
