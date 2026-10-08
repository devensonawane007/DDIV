"""SQLite-backed persistent memory store for DDIV execution experience."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from memory.schemas import MemoryRecord, TrustEvent


class MemoryStore:
    """Stores execution experience, failure patterns, and recovery attempts in SQLite."""

    def __init__(self, db_path: str | Path = "data/ddiv_memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    repository TEXT NOT NULL,
                    issue_summary TEXT,
                    failure_type TEXT,
                    diagnosis TEXT,
                    recovery_action TEXT,
                    attempt INTEGER NOT NULL,
                    result TEXT NOT NULL,
                    relevant_files TEXT,
                    agent TEXT,
                    trust_before REAL,
                    trust_after REAL,
                    metadata TEXT,
                    timestamp REAL NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trust_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    prior_trust REAL NOT NULL,
                    posterior_trust REAL NOT NULL,
                    delta REAL NOT NULL,
                    outcome TEXT NOT NULL,
                    evidence_reason TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_mem_task ON memory_records(task_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_mem_repo ON memory_records(repository)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_mem_fail ON memory_records(failure_type)"
            )
            conn.commit()

    def insert_record(self, record: MemoryRecord) -> int:
        """Insert an execution experience record."""
        meta = dict(record.metadata or {})
        if record.failure_evidence:
            meta["failure_evidence"] = record.failure_evidence
        if record.previous_patch:
            meta["previous_patch"] = record.previous_patch
        if record.failed_tests:
            meta["failed_tests"] = record.failed_tests
        if record.subsystem:
            meta["subsystem"] = record.subsystem

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO memory_records (
                    task_id, repository, issue_summary, failure_type, diagnosis,
                    recovery_action, attempt, result, relevant_files, agent,
                    trust_before, trust_after, metadata, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.task_id,
                    record.repository,
                    record.issue_summary,
                    record.failure_type,
                    record.diagnosis,
                    record.recovery_action,
                    record.attempt,
                    record.result,
                    json.dumps(record.relevant_files),
                    record.agent,
                    record.trust_before,
                    record.trust_after,
                    json.dumps(meta),
                    record.timestamp or time.time(),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def record_trust_event(self, event: TrustEvent) -> int:
        """Record a trust update event in the ledger audit table."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trust_events (
                    agent_id, task_id, attempt, prior_trust, posterior_trust,
                    delta, outcome, evidence_reason, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.agent_id,
                    event.task_id,
                    event.attempt,
                    event.prior_trust,
                    event.posterior_trust,
                    event.delta,
                    event.outcome,
                    event.evidence_reason,
                    event.timestamp or time.time(),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        return MemoryRecord(
            id=row["id"],
            task_id=row["task_id"],
            repository=row["repository"],
            issue_summary=row["issue_summary"] or "",
            failure_type=row["failure_type"],
            failure_evidence=meta.get("failure_evidence", []),
            previous_patch=meta.get("previous_patch", ""),
            failed_tests=meta.get("failed_tests", []),
            subsystem=meta.get("subsystem"),
            diagnosis=row["diagnosis"],
            recovery_action=row["recovery_action"],
            attempt=row["attempt"],
            result=row["result"],
            relevant_files=json.loads(row["relevant_files"]) if row["relevant_files"] else [],
            agent=row["agent"],
            trust_before=row["trust_before"],
            trust_after=row["trust_after"],
            metadata=meta,
            timestamp=row["timestamp"],
        )

    def get_records_by_task(self, task_id: str) -> List[MemoryRecord]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memory_records WHERE task_id = ? ORDER BY attempt ASC", (task_id,))
            return [self._row_to_record(r) for r in cursor.fetchall()]

    def get_records_by_repo(self, repository: str, limit: int = 10) -> List[MemoryRecord]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM memory_records WHERE repository = ? ORDER BY timestamp DESC LIMIT ?",
                (repository, limit),
            )
            return [self._row_to_record(r) for r in cursor.fetchall()]

    def get_records_by_failure_type(self, failure_type: str, limit: int = 10) -> List[MemoryRecord]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM memory_records WHERE failure_type = ? ORDER BY timestamp DESC LIMIT ?",
                (failure_type, limit),
            )
            return [self._row_to_record(r) for r in cursor.fetchall()]

    def get_successful_recoveries(self, failure_type: str, limit: int = 5) -> List[MemoryRecord]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM memory_records 
                WHERE failure_type = ? AND result = 'SUCCESS'
                ORDER BY timestamp DESC LIMIT ?
                """,
                (failure_type, limit),
            )
            return [self._row_to_record(r) for r in cursor.fetchall()]

    def get_all_trust_events(self, agent_id: Optional[str] = None) -> List[TrustEvent]:
        with self._connection() as conn:
            cursor = conn.cursor()
            if agent_id:
                cursor.execute(
                    "SELECT * FROM trust_events WHERE agent_id = ? ORDER BY timestamp ASC",
                    (agent_id,),
                )
            else:
                cursor.execute("SELECT * FROM trust_events ORDER BY timestamp ASC")
            return [
                TrustEvent(
                    event_id=r["event_id"],
                    agent_id=r["agent_id"],
                    task_id=r["task_id"],
                    attempt=r["attempt"],
                    prior_trust=r["prior_trust"],
                    posterior_trust=r["posterior_trust"],
                    delta=r["delta"],
                    outcome=r["outcome"],
                    evidence_reason=r["evidence_reason"],
                    timestamp=r["timestamp"],
                )
                for r in cursor.fetchall()
            ]
