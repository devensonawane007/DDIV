"""Execution state model for DDIV."""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    TASK_LOADED = "TASK_LOADED"
    LOCATING = "LOCATING"
    LOCATED = "LOCATED"
    CODING = "CODING"
    PATCH_GENERATED = "PATCH_GENERATED"
    TEST_REVIEW = "TEST_REVIEW"
    VERIFYING = "VERIFYING"
    FAILURE_DETECTED = "FAILURE_DETECTED"
    DIAGNOSING = "DIAGNOSING"
    RECOVERING = "RECOVERING"
    RETRYING = "RETRYING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"


class AgentRole(str, Enum):
    LOCATOR = "Locator"
    CODER = "Coder"
    TESTER = "Tester"
    SUPERVISOR = "Supervisor"


class AttemptRecord(BaseModel):
    attempt: int
    patch: Optional[str] = None
    modified_files: List[str] = Field(default_factory=list)
    test_passed: bool = False
    test_output: str = ""
    failure_type: Optional[str] = None
    diagnosis: Optional[str] = None
    recovery_action: Optional[str] = None
    coder_reasoning: Optional[str] = None
    tester_assessment: Optional[str] = None
    supervisor_reasoning: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class RunState(BaseModel):
    task_id: str
    run_id: str
    repository: str
    base_commit: str = ""
    issue_description: str = ""
    attempt: int = 1
    max_attempts: int = 4
    current_status: TaskStatus = TaskStatus.TASK_LOADED
    current_agent: Optional[AgentRole] = None

    # Intermediate artifacts
    located_files: List[str] = Field(default_factory=list)
    located_symbols: List[str] = Field(default_factory=list)
    current_patch: Optional[str] = None
    modified_files: List[str] = Field(default_factory=list)
    test_results: Dict[str, Any] = Field(default_factory=dict)
    failures: List[Dict[str, Any]] = Field(default_factory=list)
    diagnosis: Optional[Dict[str, Any]] = None
    recovery_action: Optional[Dict[str, Any]] = None
    memory_matches: List[Dict[str, Any]] = Field(default_factory=list)
    trust_snapshot: Dict[str, float] = Field(default_factory=dict)
    
    # History of attempts
    attempt_history: List[AttemptRecord] = Field(default_factory=list)

    # Metrics
    start_time: float = Field(default_factory=time.time)
    end_time: Optional[float] = None
    total_tokens_used: int = 0
    final_status: TaskStatus = TaskStatus.TASK_LOADED
    is_resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)
