"""Event definitions for DDIV state transitions."""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    TASK_LOADED = "task_loaded"
    LOCATE_STARTED = "locate_started"
    LOCATE_COMPLETED = "locate_completed"
    CODE_STARTED = "code_started"
    PATCH_GENERATED = "patch_generated"
    TEST_REVIEW_STARTED = "test_review_started"
    TEST_REVIEW_COMPLETED = "test_review_completed"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    FAILURE_DETECTED = "failure_detected"
    DIAGNOSIS_COMPLETED = "diagnosis_completed"
    RECOVERY_SELECTED = "recovery_selected"
    RETRY_TRIGGERED = "retry_triggered"
    TRUST_UPDATED = "trust_updated"
    MEMORY_STORED = "memory_stored"
    RUN_COMPLETED = "run_completed"
    RUN_TERMINATED = "run_terminated"


class WorkflowEvent(BaseModel):
    event_id: str
    run_id: str
    task_id: str
    event_type: EventType
    timestamp: float = Field(default_factory=time.time)
    agent_id: Optional[str] = None
    attempt: int = 1
    details: Dict[str, Any] = Field(default_factory=dict)
