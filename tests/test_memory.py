"""Tests for MemoryStore (SQLite) and MemoryRetriever."""

import tempfile
import unittest
from pathlib import Path

from memory.memory_store import MemoryStore
from memory.retrieval import MemoryRetriever
from memory.schemas import MemoryRecord


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_memory.db"
        self.store = MemoryStore(self.db_path)
        self.retriever = MemoryRetriever(self.store)

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_insert_and_retrieve_record(self):
        rec = MemoryRecord(
            task_id="task-100",
            repository="django/django",
            issue_summary="QuerySet filter bug",
            failure_type="F2",
            diagnosis="AssertionError in filter",
            recovery_action="A2",
            attempt=1,
            result="FAILED",
            relevant_files=["django/db/models/query.py"],
            agent="Coder",
        )
        row_id = self.store.insert_record(rec)
        self.assertGreater(row_id, 0)

        records = self.store.get_records_by_task("task-100")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].failure_type, "F2")
        self.assertEqual(records[0].repository, "django/django")

    def test_retrieve_by_failure_and_successful_recoveries(self):
        # Insert failure then success
        self.store.insert_record(
            MemoryRecord(
                task_id="task-101",
                repository="sympy/sympy",
                issue_summary="Integral division",
                failure_type="F2",
                diagnosis="Wrong branch",
                recovery_action="A2",
                attempt=1,
                result="FAILED",
            )
        )
        self.store.insert_record(
            MemoryRecord(
                task_id="task-101",
                repository="sympy/sympy",
                issue_summary="Integral division",
                failure_type="F2",
                diagnosis="Added check",
                recovery_action="A2",
                attempt=2,
                result="SUCCESS",
            )
        )

        successes = self.store.get_successful_recoveries("F2")
        self.assertEqual(len(successes), 1)
        self.assertEqual(successes[0].result, "SUCCESS")

        matches = self.retriever.retrieve_context_for_supervisor("task-102", "sympy/sympy", "F2")
        self.assertTrue(len(matches) > 0)
        formatted = self.retriever.format_matches_for_prompt(matches)
        self.assertIn("F2", formatted)


if __name__ == "__main__":
    unittest.main()
