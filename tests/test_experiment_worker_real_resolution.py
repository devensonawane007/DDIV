"""Unit tests verifying ExperimentWorker dataset discovery and provider resolution."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.conditions import ExperimentCondition
from core.config import AgentModelConfig, DDIVConfig, ExecutionMode, ProviderType
from core.experiment_worker import ExperimentWorker
from models.providers import (
    GeminiProvider,
    GroqProvider,
    MockModelProvider,
    OpenRouterProvider,
)
from models.registry import ModelRegistry


class TestExperimentWorkerRealResolution(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

    def tearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_worker_real_provider_config(self):
        """Verify that provider='real' configures ProviderType.OPENAI_COMPATIBLE."""
        worker = ExperimentWorker(
            task_id="pallets__flask-5014",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="test_exp",
            workspace_root=self.tmp_path,
            provider="real",
        )
        self.assertEqual(worker.config.mode, ExecutionMode.FULL_DDIV)
        self.assertEqual(worker.config.provider_type, ProviderType.OPENAI_COMPATIBLE)

    def test_worker_mock_provider_config(self):
        """Verify that provider='mock' configures ProviderType.MOCK."""
        worker = ExperimentWorker(
            task_id="mock-task-1",
            condition=ExperimentCondition.BASELINE,
            experiment_id="test_exp",
            workspace_root=self.tmp_path,
            provider="mock",
        )
        self.assertEqual(worker.config.mode, ExecutionMode.BASELINE)
        self.assertEqual(worker.config.provider_type, ProviderType.MOCK)

    def test_model_registry_real_dispatch(self):
        """Verify ModelRegistry correctly returns real providers when mode is not MOCK."""
        cfg = DDIVConfig(
            mode=ExecutionMode.FULL_DDIV,
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            locator=AgentModelConfig(name="Locator", provider="gemini", model="gemini-2.5-flash", api_key="k1"),
            coder=AgentModelConfig(name="Coder", provider="groq", model="openai/gpt-oss-120b", api_key="k2"),
            tester=AgentModelConfig(name="Tester", provider="openrouter", model="cohere/north-mini-code:free", api_key="k3"),
            supervisor=AgentModelConfig(name="Supervisor", provider="openrouter", model="nvidia/nemotron-3-super-120b-a12b:free", api_key="k4"),
        )
        registry = ModelRegistry(cfg)

        loc_prov = registry.get_provider_for_agent(cfg.locator)
        code_prov = registry.get_provider_for_agent(cfg.coder)
        test_prov = registry.get_provider_for_agent(cfg.tester)
        sup_prov = registry.get_provider_for_agent(cfg.supervisor)

        self.assertIsInstance(loc_prov, GeminiProvider)
        self.assertIsInstance(code_prov, GroqProvider)
        self.assertIsInstance(test_prov, OpenRouterProvider)
        self.assertIsInstance(sup_prov, OpenRouterProvider)

    def test_real_worker_raises_on_missing_task(self):
        """Verify worker raises ValueError if task cannot be found in dataset when provider='real'."""
        worker = ExperimentWorker(
            task_id="nonexistent__task-9999",
            condition=ExperimentCondition.FULL_DDIV,
            experiment_id="test_exp",
            workspace_root=self.tmp_path,
            provider="real",
        )
        with self.assertRaises(ValueError) as ctx:
            worker.run()
        self.assertIn("nonexistent__task-9999", str(ctx.exception))
        self.assertIn("not found in any SWE-bench dataset files", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
