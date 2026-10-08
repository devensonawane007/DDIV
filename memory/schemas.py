"""Schemas for memory records and trust transactions."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MemoryRecord(BaseModel):
    """Execution experience record stored in DDIV MemoryStore."""

    id: Optional[int] = None
    task_id: str
    repository: str
    issue_summary: str
    failure_type: Optional[str] = None
    failure_evidence: List[str] = Field(default_factory=list)
    previous_patch: str = ""
    failed_tests: List[str] = Field(default_factory=list)
    subsystem: Optional[str] = None
    diagnosis: Optional[str] = None
    recovery_action: Optional[str] = None
    attempt: int = 1
    result: str  # "SUCCESS" or "FAILED"
    relevant_files: List[str] = Field(default_factory=list)
    agent: Optional[str] = None
    trust_before: Optional[float] = None
    trust_after: Optional[float] = None
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TrustEvent(BaseModel):
    """Audit record for individual agent trust update transactions."""

    event_id: Optional[int] = None
    agent_id: str
    task_id: str
    attempt: int
    prior_trust: float
    posterior_trust: float
    delta: float
    outcome: str  # "SUCCESS" or "FAILURE" or "REGRESSION"
    evidence_reason: str
    timestamp: float = Field(default_factory=time.time)


class TrustSnapshot(BaseModel):
    scores: Dict[str, float]
    timestamp: float = Field(default_factory=time.time)
