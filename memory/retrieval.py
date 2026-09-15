"""Evidence-based retrieval interface for memory system."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from memory.memory_store import MemoryStore
from memory.schemas import MemoryRecord


class MemoryRetriever:
    """Retrieves relevant historical failure experiences and recovery successes."""

    def __init__(self, store: MemoryStore):
        self.store = store

    def retrieve_context_for_supervisor(
        self,
        task_id: str,
        repository: str,
        current_failure_candidate: Optional[str] = None,
        max_matches: int = 3,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant past experiences for the Recovery Supervisor."""
        matches: List[Dict[str, Any]] = []

        # 1. Past attempts for the current task
        task_records = self.store.get_records_by_task(task_id)
        if task_records:
            for r in task_records:
                matches.append({
                    "source": "current_task_history",
                    "attempt": r.attempt,
                    "failure_type": r.failure_type,
                    "diagnosis": r.diagnosis,
                    "recovery_action": r.recovery_action,
                    "result": r.result,
                })

        # 2. If a specific failure candidate is suspected, retrieve successful past recoveries
        if current_failure_candidate:
            successful_recoveries = self.store.get_successful_recoveries(
                current_failure_candidate, limit=max_matches
            )
            for r in successful_recoveries:
                matches.append({
                    "source": "successful_past_recovery",
                    "repository": r.repository,
                    "failure_type": r.failure_type,
                    "recovery_action": r.recovery_action,
                    "diagnosis": r.diagnosis,
                    "result": "SUCCESS",
                })

        # 3. Repository-specific failure patterns
        repo_records = self.store.get_records_by_repo(repository, limit=max_matches)
        for r in repo_records:
            if r.task_id != task_id and r.failure_type:
                matches.append({
                    "source": "repository_pattern",
                    "failure_type": r.failure_type,
                    "relevant_files": r.relevant_files,
                    "recovery_action": r.recovery_action,
                })

        # Return capped results to avoid prompt bloating
        return matches[:max_matches * 2]

    def format_matches_for_prompt(self, matches: List[Dict[str, Any]]) -> str:
        """Render concise summary string for injection into prompts."""
        if not matches:
            return ""

        lines = []
        for i, m in enumerate(matches, 1):
            source = m.get("source", "history")
            ftype = m.get("failure_type", "Unknown")
            action = m.get("recovery_action", "None")
            diag = m.get("diagnosis", "")
            lines.append(f"[{i}] ({source}) Failure: {ftype} | Strategy: {action} | Context: {diag[:120]}")

        return "\n".join(lines)
