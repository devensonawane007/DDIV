"""Focused tests for workspace isolation and git ceiling defense.

Verifies:
1. verify_workspace_isolation succeeds on verified preflight repositories.
2. verify_workspace_isolation fails closed if directory is root DDIV repository.
3. verify_workspace_isolation fails closed if local .git is missing.
4. verify_workspace_isolation fails closed if checked-out HEAD does not match expected base commit.
5. GIT_CEILING_DIRECTORIES strictly prevents Git commands in subdirectories from traversing up to root DDIV.
6. ExperimentWorker strictly validates isolation and fails closed before agent steps.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from core.conditions import ExperimentCondition
from core.experiment_worker import ExperimentWorker, verify_workspace_isolation

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestWorkspaceIsolation:
    """Test suite ensuring workspaces cannot escape to or modify the parent repository."""

    def test_01_verify_isolation_passes_on_preflight_repo(self):
        """Preflight repository passes all isolation checks with its expected base commit."""
        preflight_pylint = PROJECT_ROOT / "data" / "workspaces" / "preflight_verification" / "pylint-dev__pylint-6903"
        if not preflight_pylint.exists():
            pytest.skip("Preflight cache not present on disk.")

        expected_commit = "ca80f03a43bc39e4cc2c67dc99817b3c9f13b8a6"
        # Should complete without error
        verify_workspace_isolation(preflight_pylint, expected_commit=expected_commit, root_repo=PROJECT_ROOT)

    def test_02_verify_isolation_fails_if_root_ddiv(self):
        """Passing the root DDIV repository path raises a critical isolation breach error."""
        with pytest.raises(RuntimeError, match="CRITICAL ISOLATION BREACH.*root DDIV repository"):
            verify_workspace_isolation(PROJECT_ROOT, root_repo=PROJECT_ROOT)

    def test_03_verify_isolation_fails_if_git_missing(self, tmp_path):
        """A directory lacking a local .git folder immediately fails closed."""
        empty_dir = tmp_path / "empty_workspace"
        empty_dir.mkdir()

        with pytest.raises(RuntimeError, match="lacks local .git directory"):
            verify_workspace_isolation(empty_dir, root_repo=PROJECT_ROOT)

    def test_04_verify_isolation_fails_if_commit_mismatch(self):
        """A repository whose HEAD does not match the expected base commit fails closed."""
        preflight_pylint = PROJECT_ROOT / "data" / "workspaces" / "preflight_verification" / "pylint-dev__pylint-6903"
        if not preflight_pylint.exists():
            pytest.skip("Preflight cache not present on disk.")

        with pytest.raises(RuntimeError, match="does not match expected base commit"):
            verify_workspace_isolation(
                preflight_pylint,
                expected_commit="0000000000000000000000000000000000000000",
                root_repo=PROJECT_ROOT,
            )

    def test_05_git_ceiling_directories_blocks_discovery(self, tmp_path):
        """With GIT_CEILING_DIRECTORIES set to root DDIV, Git commands in child dirs never discover root .git."""
        sub_dir = PROJECT_ROOT / "data" / "workspaces" / f"tmp_ceiling_test_{os.getpid()}"
        sub_dir.mkdir(parents=True, exist_ok=True)
        try:
            env = os.environ.copy()
            env["GIT_CEILING_DIRECTORIES"] = str(PROJECT_ROOT.resolve())

            res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(sub_dir),
                capture_output=True,
                text=True,
                env=env,
            )
            # Must exit non-zero because ceiling directory prevents seeing root .git
            assert res.returncode != 0
            assert "not a git repository" in res.stderr.lower()
        finally:
            if sub_dir.exists():
                sub_dir.rmdir()

    def test_06_worker_fails_closed_when_workspace_is_root(self, monkeypatch):
        """ExperimentWorker refuses to execute and fails closed if workspace_root resolves to PROJECT_ROOT."""
        worker = ExperimentWorker(
            task_id="pallets__flask-5014",
            condition=ExperimentCondition.BASELINE,
            experiment_id="test_iso",
            workspace_root=PROJECT_ROOT,
            provider="mock",
        )

        with pytest.raises(RuntimeError, match="CRITICAL ISOLATION BREACH"):
            worker.run()
