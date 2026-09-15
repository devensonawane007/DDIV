"""Dynamic trust ledger for agent reliability tracking."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from memory.schemas import TrustEvent, TrustSnapshot
from memory.memory_store import MemoryStore


class TrustLedger:
    """Manages dynamic trust scores for each agent with auditable transaction history."""

    def __init__(
        self,
        memory_store: Optional[MemoryStore] = None,
        initial_trust: Optional[Dict[str, float]] = None,
        success_reward: float = 0.05,
        failure_penalty: float = 0.08,
    ):
        self.store = memory_store
        self.success_reward = success_reward
        self.failure_penalty = failure_penalty

        # Configurable initial baseline values
        defaults = {
            "Locator": 0.87,
            "Coder": 0.74,
            "Tester": 0.91,
            "Supervisor": 0.84,
        }
        if initial_trust:
            defaults.update(initial_trust)

        self._scores: Dict[str, float] = {k: float(v) for k, v in defaults.items()}
        self._history: List[TrustEvent] = []

    def get_score(self, agent_id: str) -> float:
        return self._scores.get(agent_id, 0.5)

    def get_all_scores(self) -> Dict[str, float]:
        return dict(self._scores)

    def get_snapshot(self) -> TrustSnapshot:
        return TrustSnapshot(scores=dict(self._scores), timestamp=time.time())

    def update_trust(
        self,
        agent_id: str,
        task_id: str,
        attempt: int,
        success: bool,
        evidence_reason: str,
        weight: float = 1.0,
    ) -> float:
        """Update trust score based on verified outcome and evidence."""
        prior = self.get_score(agent_id)

        if success:
            delta = self.success_reward * weight
            outcome = "SUCCESS"
        else:
            delta = -self.failure_penalty * weight
            outcome = "FAILURE"

        posterior = max(0.0, min(1.0, prior + delta))
        self._scores[agent_id] = round(posterior, 4)

        event = TrustEvent(
            agent_id=agent_id,
            task_id=task_id,
            attempt=attempt,
            prior_trust=round(prior, 4),
            posterior_trust=round(posterior, 4),
            delta=round(delta, 4),
            outcome=outcome,
            evidence_reason=evidence_reason,
            timestamp=time.time(),
        )

        self._history.append(event)

        if self.store:
            try:
                self.store.record_trust_event(event)
            except Exception:
                pass

        return posterior

    def get_transaction_history(self, agent_id: Optional[str] = None) -> List[TrustEvent]:
        if agent_id:
            return [e for e in self._history if e.agent_id == agent_id]
        return list(self._history)
