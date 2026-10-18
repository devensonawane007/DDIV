"""Focused tests for Coder model routing.

Verifies:
1. V22SupervisedWorker routes Coder to Ollama (qwen2.5-coder:7b) when experiment_config is passed.
2. Support agents (Supervisor, Tester, Locator) retain their configured Groq/Gemini providers.
3. Explicit experiment_config overrides default environment settings where Coder might be Groq.
4. ModelRegistry accurately instantiates OllamaProvider for Coder and GroqProvider for Supervisor/Tester.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.conditions import ExperimentCondition
from core.config import DDIVConfig
from models.providers import GroqProvider
from models.registry import ModelRegistry
from scripts.ollama_coder_adapter import OllamaProvider
from scripts.v2_2_recovery_manager import V22SupervisedWorker


class TestCoderRouting:
    """Test suite ensuring Coder is strictly routed to Ollama and never defaults to Groq."""

    def test_01_worker_routes_coder_to_ollama_from_dict_config(self, tmp_path):
        """Worker accepts experiment_config dict and configures Coder for Ollama while keeping support agents."""
        exp_config = {
            "experiment_id": "test_exp_01",
            "models": {
                "Coder": {"provider": "ollama", "model_id": "qwen2.5-coder:7b", "temperature": 0.0},
                "Supervisor": {"provider": "groq", "model_id": "qwen/qwen3.8-27b", "temperature": 0.0},
                "Tester": {"provider": "groq", "model_id": "qwen/qwen3.8-27b", "temperature": 0.0},
                "Locator": {"provider": "gemini", "model_id": "gemini-3.1-flash-lite", "temperature": 0.0},
            },
        }

        worker = V22SupervisedWorker(
            experiment_id="test_exp_01",
            task_id="pallets__flask-5014",
            condition=ExperimentCondition.FULL_DDIV_MEMORY_OFF,
            workspace_root=tmp_path / "ws",
            provider="mock",
            experiment_config=exp_config,
        )

        assert worker.config.coder.provider == "ollama"
        assert worker.config.coder.model == "qwen2.5-coder:7b"
        assert worker.config.coder.api_key == "ollama"
        assert "11434" in worker.config.coder.base_url

        # Support agents remain on their configured providers
        assert worker.config.supervisor.provider == "groq"
        assert worker.config.tester.provider == "groq"
        assert worker.config.locator.provider == "gemini"

    def test_02_worker_accepts_file_path_experiment_config(self, tmp_path):
        """Worker accepts a file path to experiment_config.json and applies model configuration."""
        cfg_file = tmp_path / "experiment_config.json"
        cfg_content = {
            "experiment_id": "test_exp_file",
            "models": {
                "Coder": {"provider": "ollama", "model_id": "qwen2.5-coder:7b", "temperature": 0.0},
                "Supervisor": {"provider": "groq", "model_id": "qwen/qwen3.8-27b", "temperature": 0.0},
            },
        }
        cfg_file.write_text(json.dumps(cfg_content), encoding="utf-8")

        worker = V22SupervisedWorker(
            experiment_id="test_exp_file",
            task_id="pallets__flask-5014",
            condition=ExperimentCondition.FULL_DDIV_MEMORY_ON,
            workspace_root=tmp_path / "ws",
            provider="mock",
            experiment_config=cfg_file,
        )

        assert worker.config.coder.provider == "ollama"
        assert worker.config.coder.model == "qwen2.5-coder:7b"
        assert worker.config.supervisor.provider == "groq"

    def test_03_coder_routing_overrides_groq_env(self, monkeypatch, tmp_path):
        """Even when environment variables default Coder to Groq, experiment_config overrides it to Ollama."""
        monkeypatch.setenv("CODER_PROVIDER", "groq")
        monkeypatch.setenv("CODER_MODEL", "openai/gpt-oss-120b")
        monkeypatch.delenv("DDIV_CODER_PROVIDER", raising=False)

        # Confirm default env config produces Groq coder
        default_cfg = DDIVConfig.load_from_env()
        assert default_cfg.coder.provider == "groq"

        exp_config = {
            "models": {
                "Coder": {"provider": "ollama", "model_id": "qwen2.5-coder:7b"},
                "Supervisor": {"provider": "groq", "model_id": "qwen/qwen3.8-27b"},
            }
        }

        worker = V22SupervisedWorker(
            experiment_id="test_override",
            task_id="pallets__flask-5014",
            condition=ExperimentCondition.FULL_DDIV_MEMORY_OFF,
            workspace_root=tmp_path / "ws",
            provider="mock",
            experiment_config=exp_config,
        )

        assert worker.config.coder.provider == "ollama"
        assert worker.config.coder.model == "qwen2.5-coder:7b"
        assert worker.config.supervisor.provider == "groq"

    def test_04_model_registry_instantiates_correct_providers(self, monkeypatch, tmp_path):
        """ModelRegistry returns OllamaProvider for Coder and GroqProvider for Supervisor/Tester."""
        monkeypatch.setenv("GROQ_API_KEY", "gsk_dummy_test_key_12345")
        exp_config = {
            "models": {
                "Coder": {"provider": "ollama", "model_id": "qwen2.5-coder:7b"},
                "Supervisor": {"provider": "groq", "model_id": "qwen/qwen3.8-27b"},
                "Tester": {"provider": "groq", "model_id": "qwen/qwen3.8-27b"},
            }
        }

        worker = V22SupervisedWorker(
            experiment_id="test_reg",
            task_id="pallets__flask-5014",
            condition=ExperimentCondition.FULL_DDIV_MEMORY_OFF,
            workspace_root=tmp_path / "ws",
            provider="real",
            experiment_config=exp_config,
        )

        registry = ModelRegistry(worker.config)
        coder_prov = registry.get_provider_for_agent(worker.config.coder)
        sup_prov = registry.get_provider_for_agent(worker.config.supervisor)
        test_prov = registry.get_provider_for_agent(worker.config.tester)

        assert isinstance(coder_prov, OllamaProvider)
        assert coder_prov.model_id == "qwen2.5-coder:7b"
        assert "11434" in coder_prov.base_url

        assert isinstance(sup_prov, GroqProvider)
        assert isinstance(test_prov, GroqProvider)
