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
        failed_tests: Optional[List[str]] = None,
        subsystem: Optional[str] = None,
        max_matches: int = 4,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant past experiences for the Recovery Supervisor prioritized by repo, failure category, test pattern, and subsystem."""
        matches: List[Dict[str, Any]] = []
        seen_record_ids = set()

        # 1. Past attempts for the current task (highest priority)
        task_records = self.store.get_records_by_task(task_id)
        if task_records:
            for r in task_records:
                if r.id is not None:
                    seen_record_ids.add(r.id)
                matches.append({
                    "source": "current_task_history",
                    "attempt": r.attempt,
                    "failure_type": r.failure_type,
                    "failed_tests": r.failed_tests,
                    "diagnosis": r.diagnosis,
                    "recovery_action": r.recovery_action,
                    "result": r.result,
                })

        # 2. Same repository records prioritized by failure category or subsystem
        repo_records = self.store.get_records_by_repo(repository, limit=15)
        for r in repo_records:
            if r.task_id == task_id or (r.id is not None and r.id in seen_record_ids):
                continue
            
            # Check for matches
            is_same_fail = bool(current_failure_candidate and r.failure_type == current_failure_candidate)
            is_same_subsystem = bool(subsystem and r.subsystem and r.subsystem.lower() == subsystem.lower())
            has_test_overlap = bool(failed_tests and set(r.failed_tests or []).intersection(failed_tests))

            if is_same_fail or is_same_subsystem or has_test_overlap:
                if r.id is not None:
                    seen_record_ids.add(r.id)
                matches.append({
                    "source": "repo_similar_experience",
                    "task_id": r.task_id,
                    "failure_type": r.failure_type,
                    "failed_tests": r.failed_tests,
                    "subsystem": r.subsystem,
                    "recovery_action": r.recovery_action,
                    "diagnosis": r.diagnosis,
                    "result": r.result,
                })

        # 3. Successful recoveries for the failure candidate across repos
        if current_failure_candidate:
            successful_recoveries = self.store.get_successful_recoveries(
                current_failure_candidate, limit=max_matches
            )
            for r in successful_recoveries:
                if r.id is not None and r.id in seen_record_ids:
                    continue
                if r.id is not None:
                    seen_record_ids.add(r.id)
                matches.append({
                    "source": "cross_repo_successful_recovery",
                    "repository": r.repository,
                    "failure_type": r.failure_type,
                    "recovery_action": r.recovery_action,
                    "diagnosis": r.diagnosis,
                    "result": "SUCCESS",
                })

        # 4. Fallback: repository general patterns
        for r in repo_records:
            if r.task_id == task_id or (r.id is not None and r.id in seen_record_ids):
                continue
            if r.id is not None:
                seen_record_ids.add(r.id)
            matches.append({
                "source": "repository_pattern",
                "failure_type": r.failure_type,
                "relevant_files": r.relevant_files,
                "recovery_action": r.recovery_action,
                "diagnosis": r.diagnosis,
                "result": r.result,
            })
            if len(matches) >= max_matches * 3:
                break

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
            diag = m.get("diagnosis", "") or ""
            ftests = m.get("failed_tests", [])
            test_str = f" | Tests: {', '.join(ftests[:3])}" if ftests else ""
            lines.append(f"[{i}] ({source}) Failure: {ftype}{test_str} | Action: {action} | Context: {diag[:120]}")

        return "\n".join(lines)
