"""Structured JSONL trace logger and human-readable terminal summary generator."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from core.events import EventType, WorkflowEvent


class TraceEvent(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    iso_time: str = ""
    task_id: str
    run_id: str
    attempt: int
    agent_id: Optional[str] = None
    event_type: str
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    tool_action: Optional[str] = None
    tool_result: Optional[str] = None
    latency_seconds: float = 0.0
    token_usage: Dict[str, int] = Field(default_factory=dict)
    failure: Optional[str] = None
    diagnosis: Optional[str] = None
    recovery: Optional[str] = None
    trust_snapshot: Dict[str, float] = Field(default_factory=dict)
    memory_retrieval_count: int = 0
    final_result: Optional[str] = None


class TraceLogger:
    """Logs machine-readable JSONL traces and pretty terminal summaries."""

    def __init__(self, run_id: str, task_id: str, log_dir: str | Path = "logs/runs"):
        self.run_id = run_id
        self.task_id = task_id
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{run_id}.jsonl"

    def log_event(self, event: TraceEvent) -> None:
        """Append structured event to JSONL trace file."""
        if not event.iso_time:
            event.iso_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event.timestamp))

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def print_terminal_summary(
        self,
        task_id: str,
        mode: str,
        attempts: int,
        resolved: bool,
        initial_failure: Optional[str],
        final_diagnosis: Optional[str],
        trust_scores: Dict[str, float],
        duration: float,
    ) -> None:
        """Print clean human-readable execution summary."""
        status_str = "RESOLVED (SUCCESS)" if resolved else "UNRESOLVED (FAILED)"
        div = "=" * 60
        print(f"\n{div}")
        print(f" DDIV RUN SUMMARY — {task_id}")
        print(f"{div}")
        print(f" Mode:                {mode}")
        print(f" Status:              {status_str}")
        print(f" Total Attempts:      {attempts}")
        print(f" Initial Failure:     {initial_failure or 'None'}")
        print(f" Final Diagnosis:     {final_diagnosis or 'Clean pass'}")
        print(f" Duration:            {duration:.2f}s")
        print(f" Trust Scores:")
        for agent, score in trust_scores.items():
            print(f"   - {agent:<12}: {score:.4f}")
        print(f" Trace Log:           {self.log_file}")
        print(f"{div}\n")
