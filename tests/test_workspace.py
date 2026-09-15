"""Tests for WorkspaceManager and safe sandboxing."""

import tempfile
import unittest
from pathlib import Path

from evaluation.workspace import WorkspaceManager


class TestWorkspace(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.ws_mgr = WorkspaceManager(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_create_and_provision_workspace(self):
        ws = self.ws_mgr.create_workspace(task_id="test-task-1")
        self.assertTrue(ws.exists())
        self.assertTrue((ws.path / ".git").exists())

        # Provision mock calculator task
        self.ws_mgr.provision_mock_task(ws)
        self.assertTrue((ws.path / "src" / "calculator.py").exists())
        self.assertTrue((ws.path / "tests" / "test_calculator.py").exists())

        # Cleanup
        ws.cleanup()
        self.assertFalse(ws.path.exists())


if __name__ == "__main__":
    unittest.main()
