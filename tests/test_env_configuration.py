"""Tests for DDIV environment loading, configuration precedence, secret protection, and agent preservation."""

import os
import tempfile
import unittest
from pathlib import Path

from core.config import (
    DDIVConfig,
    ExecutionMode,
    ProviderType,
    get_groq_api_key,
    get_project_root,
    load_project_env,
)
from models.registry import ModelRegistry
from models.providers import GroqProvider


class TestEnvConfiguration(unittest.TestCase):
    def setUp(self):
        self.original_env = os.environ.copy()
        self.original_cwd = os.getcwd()
        self.project_root = get_project_root()

    def tearDown(self):
        os.chdir(self.original_cwd)
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_get_project_root_accuracy(self):
        """Verify get_project_root accurately locates project root containing core markers."""
        root = get_project_root()
        self.assertTrue((root / "pyproject.toml").exists(), "Project root must contain pyproject.toml")
        self.assertTrue((root / ".gitignore").exists(), "Project root must contain .gitignore")
        self.assertTrue((root / "core" / "config.py").exists(), "Project root must contain core/config.py")

    def test_env_loading_from_different_working_directory(self):
        """Verify .env loads correctly even when Python working directory is elsewhere."""
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self.assertNotEqual(Path(os.getcwd()).resolve(), self.project_root.resolve())

                # Clear GROQ_API_KEY from environment to test fresh loading
                if "GROQ_API_KEY" in os.environ:
                    del os.environ["GROQ_API_KEY"]

                # Load env via load_project_env without arguments
                loaded = load_project_env(override=False)
                self.assertTrue(loaded, "load_project_env must successfully locate and load root .env")
                self.assertTrue(bool(os.getenv("GROQ_API_KEY")), "GROQ_API_KEY must be loaded despite foreign cwd")
            finally:
                os.chdir(self.original_cwd)

    def test_explicit_environment_variable_precedence(self):
        """Verify that explicitly supplied environment variables are preserved by default."""
        explicit_dummy_key = "mock_override_test_key_123"
        os.environ["GROQ_API_KEY"] = explicit_dummy_key

        # Calling load_project_env with default override=False must not overwrite
        load_project_env(override=False)
        self.assertEqual(
            os.getenv("GROQ_API_KEY"),
            explicit_dummy_key,
            "Explicit environment variable must not be overwritten when override=False",
        )

        # Calling with override=True would overwrite from .env
        load_project_env(override=True)
        self.assertNotEqual(
            os.getenv("GROQ_API_KEY"),
            explicit_dummy_key,
            "override=True must reload value from .env",
        )

    def test_missing_key_behavior(self):
        """Verify clear error is raised when GROQ_API_KEY is required but missing or placeholder."""
        if "GROQ_API_KEY" in os.environ:
            del os.environ["GROQ_API_KEY"]

        with tempfile.TemporaryDirectory() as temp_dir:
            empty_env = Path(temp_dir) / ".env"
            empty_env.write_text("EMPTY_VAR=1\n", encoding="utf-8")

            # Missing key with empty env path
            with self.assertRaises(ValueError) as ctx:
                get_groq_api_key(required=True, env_path=empty_env)
            self.assertIn("GROQ_API_KEY", str(ctx.exception))
            self.assertIn("Missing or invalid", str(ctx.exception))

            # Placeholder key behavior
            os.environ["GROQ_API_KEY"] = "your_groq_api_key_placeholder"
            with self.assertRaises(ValueError) as ctx:
                get_groq_api_key(required=True)
            self.assertIn("GROQ_API_KEY", str(ctx.exception))
            self.assertIn("Missing or invalid", str(ctx.exception))

    def test_no_secret_leakage_in_metadata_or_exceptions(self):
        """Verify API keys are never exposed in experiment metadata or exception messages."""
        dummy_secret = "mock_canary_secret_token_val_999"
        os.environ["GROQ_API_KEY"] = dummy_secret

        cfg = DDIVConfig()
        meta = cfg.get_experiment_metadata()
        meta_str = str(meta)

        self.assertNotIn(dummy_secret, meta_str, "Secret key must not appear in experiment metadata")

        # Test error sanitization
        try:
            cfg.tester.api_key = None
            cfg.mode = ExecutionMode.REAL
            cfg.validate_for_execution()
        except ValueError as e:
            err_msg = str(e)
            self.assertNotIn(dummy_secret, err_msg)
            self.assertIn("Missing API key/token", err_msg)

    def test_preservation_of_ollama_coder_and_groq_supporting_agents(self):
        """Verify Ollama Coder and Groq supporting agents remain configured and isolated."""
        os.environ["DDIV_CODER_PROVIDER"] = "ollama"
        os.environ["OLLAMA_MODEL"] = "qwen2.5-coder:7b"
        os.environ["TESTER_PROVIDER"] = "groq"
        os.environ["TESTER_MODEL"] = "qwen/qwen3.8-27b"
        os.environ["SUPERVISOR_PROVIDER"] = "groq"
        os.environ["SUPERVISOR_MODEL"] = "qwen/qwen3.8-27b"

        cfg = DDIVConfig(mode=ExecutionMode.REAL, provider_type=ProviderType.GROQ)

        # Coder must be strictly Ollama
        self.assertEqual(cfg.coder.provider, "ollama")
        self.assertEqual(cfg.coder.model, "qwen2.5-coder:7b")
        self.assertEqual(cfg.coder.base_url, "http://localhost:11434")

        # Supporting agents must be Groq
        self.assertEqual(cfg.tester.provider, "groq")
        self.assertEqual(cfg.tester.model, "qwen/qwen3.8-27b")
        self.assertEqual(cfg.supervisor.provider, "groq")
        self.assertEqual(cfg.supervisor.model, "qwen/qwen3.8-27b")

        # ModelRegistry provider instantiation
        registry = ModelRegistry(cfg)
        tester_prov = registry.get_provider_for_agent(cfg.tester)
        supervisor_prov = registry.get_provider_for_agent(cfg.supervisor)

        self.assertIsInstance(tester_prov, GroqProvider)
        self.assertIsInstance(supervisor_prov, GroqProvider)
        self.assertEqual(tester_prov.config.model_id, "qwen/qwen3.8-27b")
        self.assertEqual(supervisor_prov.config.model_id, "qwen/qwen3.8-27b")


if __name__ == "__main__":
    unittest.main()
