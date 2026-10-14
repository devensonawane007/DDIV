"""Unit tests for DDIV Coder Model Ablation infrastructure."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.config import DDIVConfig
from models.providers import GeminiProvider, GroqProvider
from models.registry import ModelRegistry
from scripts.generate_coder_ablation_report import generate_ablation_report
from scripts.run_coder_ablation import CoderAblationOrchestrator
from scripts.run_coder_ablation_worker import create_ablation_config


class TestCoderAblation:
    """Verifies that the coder ablation configures and executes both models cleanly in isolation."""

    def test_01_create_ablation_config_coder_a(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_mock_test_key_12345")
        config = create_ablation_config("coder_a", "real")

        assert config.coder.name == "Coder"
        assert config.coder.provider == "groq"
        assert config.coder.model == "openai/gpt-oss-120b"
        assert config.coder.base_url == "https://api.groq.com/openai/v1"
        assert config.coder.api_key == "gsk_mock_test_key_12345"

        registry = ModelRegistry(config)
        provider = registry.get_provider_for_agent(config.coder)
        assert isinstance(provider, GroqProvider)
        assert provider.base_url == "https://api.groq.com/openai/v1"

    def test_02_create_ablation_config_coder_b(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AQ.A_mock_test_key_12345")
        config = create_ablation_config("coder_b", "real")

        assert config.coder.name == "Coder"
        assert config.coder.provider == "gemini"
        assert config.coder.model == "gemini-3.8-flash"
        assert config.coder.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"
        assert config.coder.api_key == "AQ.A_mock_test_key_12345"

        registry = ModelRegistry(config)
        provider = registry.get_provider_for_agent(config.coder)
        assert isinstance(provider, GeminiProvider)
        assert provider.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"

    def test_03_ablation_worker_mock_execution(self, tmp_path):
        """Verify run_coder_ablation_worker executes in mock mode and records coder metadata."""
        out_file_a = tmp_path / "result_mock-task__coder_a.json"
        log_file_a = tmp_path / "mock-task__coder_a.log"
        ws_root_a = tmp_path / "ws_coder_a"

        cmd_a = [
            sys.executable,
            "-m",
            "scripts.run_coder_ablation_worker",
            "--task-id",
            "mock-task-1",
            "--coder-variant",
            "coder_a",
            "--condition",
            "full_ddiv",
            "--experiment-id",
            "test_ablation_exp",
            "--workspace-root",
            str(ws_root_a),
            "--output-file",
            str(out_file_a),
            "--log-file",
            str(log_file_a),
            "--provider",
            "mock",
        ]

        proc_a = subprocess.run(cmd_a, capture_output=True, text=True)
        assert proc_a.returncode == 0
        assert out_file_a.exists()

        data_a = json.loads(out_file_a.read_text(encoding="utf-8"))
        assert data_a["status"] == "COMPLETED"
        assert data_a["coder_variant"] == "coder_a"
        assert "mock-coder-coder_a" in data_a["coder_model"]

        out_file_b = tmp_path / "result_mock-task__coder_b.json"
        log_file_b = tmp_path / "mock-task__coder_b.log"
        ws_root_b = tmp_path / "ws_coder_b"

        cmd_b = [
            sys.executable,
            "-m",
            "scripts.run_coder_ablation_worker",
            "--task-id",
            "mock-task-1",
            "--coder-variant",
            "coder_b",
            "--condition",
            "full_ddiv",
            "--experiment-id",
            "test_ablation_exp",
            "--workspace-root",
            str(ws_root_b),
            "--output-file",
            str(out_file_b),
            "--log-file",
            str(log_file_b),
            "--provider",
            "mock",
        ]

        proc_b = subprocess.run(cmd_b, capture_output=True, text=True)
        assert proc_b.returncode == 0
        assert out_file_b.exists()

        data_b = json.loads(out_file_b.read_text(encoding="utf-8"))
        assert data_b["status"] == "COMPLETED"
        assert data_b["coder_variant"] == "coder_b"
        assert "mock-coder-coder_b" in data_b["coder_model"]

    def test_04_ablation_orchestrator_mock_execution_and_reporting(self, tmp_path):
        """Verify CoderAblationOrchestrator coordinates jobs and generates all deliverables."""
        exp_id = "test_orch_ablation"
        orch = CoderAblationOrchestrator(
            experiment_id=exp_id,
            tasks=["mock-task-1"],
            coders=["coder_a", "coder_b"],
            condition="full_ddiv",
            provider="mock",
            base_dir=tmp_path / "experiments",
            workspace_base=tmp_path / "workspaces",
            logs_base=tmp_path / "logs",
        )

        manifest = orch.run_all()
        assert manifest["jobs"]["mock-task-1__coder_a"]["status"] == "COMPLETED"
        assert manifest["jobs"]["mock-task-1__coder_b"]["status"] == "COMPLETED"

        # Generate reports
        outputs = generate_ablation_report(
            experiment_id=exp_id,
            base_dir=str(tmp_path / "experiments"),
        )

        assert outputs["config"].exists()
        assert outputs["results"].exists()
        assert outputs["csv"].exists()
        assert outputs["summary"].exists()
        assert outputs["failure_analysis"].exists()

        csv_content = outputs["csv"].read_text(encoding="utf-8")
        assert "mock-task-1,coder_a" in csv_content
        assert "mock-task-1,coder_b" in csv_content

        summary_content = outputs["summary"].read_text(encoding="utf-8")
        assert "DDIV v2.1: Controlled Coder Model Ablation Summary" in summary_content
        assert "mock-task-1" in summary_content
