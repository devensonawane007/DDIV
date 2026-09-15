"""Evaluation, safe workspace, patch management, and SWE-bench adaptation."""
from evaluation.workspace import WorkspaceManager, TaskWorkspace
from evaluation.patch_manager import PatchManager, PatchValidationResult
from evaluation.command_runner import CommandRunner, CommandResult
from evaluation.swebench_loader import SWEBenchLoader, SWEBenchTask
from evaluation.metrics import MetricCollector, EvaluationSummary

__all__ = [
    "WorkspaceManager",
    "TaskWorkspace",
    "PatchManager",
    "PatchValidationResult",
    "CommandRunner",
    "CommandResult",
    "SWEBenchLoader",
    "SWEBenchTask",
    "MetricCollector",
    "EvaluationSummary",
]
