"""Unit tests for OllamaProvider, CoderAgent contract, and isolation guarantees."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import requests

from agents.base import AgentInputMetadata
from agents.coder import CoderAgent, CoderOutput
from core.config import DDIVConfig
from evaluation.patch_builder import CodeModification
from models.base import ModelConfig, ProviderResponse
from models.providers import ErrorCategory, GroqProvider, GeminiProvider
from models.registry import ModelRegistry
from scripts.demo_patch_builder import DemoPatchBuilder
from scripts.ollama_coder_adapter import OllamaProvider, robust_extract_json, register_ollama_provider


class TestOllamaProvider:
    """Verifies Ollama provider contract, schema validation, error categorization, and strict no-fallback."""

    def test_01_default_provider_preserved_as_groq(self, monkeypatch):
        """When DDIV_CODER_PROVIDER is unset or empty, Groq remains the active Coder provider."""
        monkeypatch.delenv("DDIV_CODER_PROVIDER", raising=False)
        monkeypatch.setenv("CODER_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_12345")
        monkeypatch.setenv("CODER_MODEL", "openai/gpt-oss-120b")
        monkeypatch.setenv("DDIV_MODE", "real")
        monkeypatch.setenv("PROVIDER_TYPE", "openai_compatible")

        config = DDIVConfig.load_from_env()
        assert config.coder.provider == "groq"
        assert config.coder.model == "openai/gpt-oss-120b"
        assert "groq.com" in config.coder.base_url

        registry = ModelRegistry(config)
        provider = registry.get_provider_for_agent(config.coder)
        assert isinstance(provider, GroqProvider)

    def test_02_ollama_configured_explicitly(self, monkeypatch):
        """When DDIV_CODER_PROVIDER=ollama, Coder routes cleanly to OllamaProvider with sensible defaults."""
        monkeypatch.setenv("DDIV_CODER_PROVIDER", "ollama")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
        monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "240")
        monkeypatch.setenv("DDIV_MODE", "real")
        monkeypatch.setenv("PROVIDER_TYPE", "openai_compatible")

        config = DDIVConfig.load_from_env()
        assert config.coder.provider == "ollama"
        assert config.coder.model == "qwen2.5-coder:7b"
        assert config.coder.base_url == "http://localhost:11434"
        assert config.coder.timeout == 240

        registry = ModelRegistry(config)
        provider = registry.get_provider_for_agent(config.coder)
        assert isinstance(provider, OllamaProvider)
        assert provider.model_id == "qwen2.5-coder:7b"
        assert provider.base_url == "http://localhost:11434"
        assert provider.timeout == 240

    def test_03_successful_generation_and_token_accounting(self):
        """Verify successful structured response with prompt_eval_count, eval_count, and latency."""
        cfg = ModelConfig(
            name="Coder",
            model_id="qwen2.5-coder:7b",
            provider="ollama",
            base_url="http://localhost:11434",
            timeout=240,
        )
        provider = OllamaProvider(cfg)

        sample_coder_dict = {
            "behavioral_analysis": "Target function must reject empty strings.",
            "existing_behavior": "Currently accepts empty string silently.",
            "smallest_change_plan": "Add validation guard at start of function.",
            "regression_risks": ["Callers relying on empty string might fail."],
            "modifications": [
                {
                    "path": "test_mod.py",
                    "target_symbol": "func",
                    "operation": "insert_after",
                    "anchor": "def func(name):\n",
                    "code": "    if not name:\n        raise ValueError('empty')\n",
                    "reason": "Validate input name",
                }
            ],
            "modified_files": ["test_mod.py"],
            "reasoning_summary": "Added input validation guard.",
            "confidence": 0.95,
        }

        mock_ollama_res = {
            "model": "qwen2.5-coder:7b",
            "created_at": "2026-10-13T16:00:00Z",
            "response": json.dumps(sample_coder_dict),
            "done": True,
            "total_duration": 4500000000,  # 4.5 seconds in nanoseconds
            "prompt_eval_count": 512,
            "eval_count": 128,
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_ollama_res

        with patch("requests.post", return_value=mock_resp) as mock_post:
            resp: ProviderResponse = provider.generate(
                prompt="Fix the bug",
                system_prompt="You are coder",
                response_schema=CoderOutput,
            )

            assert mock_post.called
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"]["model"] == "qwen2.5-coder:7b"
            assert call_kwargs["json"]["format"] == "json"
            assert call_kwargs["json"]["stream"] is False

            assert resp.error is None
            assert resp.parsed_json == sample_coder_dict
            assert resp.prompt_tokens == 512
            assert resp.completion_tokens == 128
            assert resp.total_tokens == 640
            assert resp.latency_seconds == pytest.approx(4.5, rel=1e-3)
            assert resp.provider == "ollama"

    def test_04_coder_agent_execution_validates_schema_contract(self):
        """Verify CoderAgent executes cleanly with OllamaProvider and produces validated CoderOutput."""
        cfg = ModelConfig(
            name="Coder",
            model_id="qwen2.5-coder:7b",
            provider="ollama",
            base_url="http://localhost:11434",
            timeout=240,
        )
        provider = OllamaProvider(cfg)
        agent = CoderAgent(provider)

        sample_coder_dict = {
            "behavioral_analysis": "Analysis here",
            "existing_behavior": "Behavior here",
            "smallest_change_plan": "Plan here",
            "regression_risks": [],
            "modifications": [
                {
                    "path": "src/app.py",
                    "target_symbol": "init",
                    "operation": "replace",
                    "anchor": "x = 1\n",
                    "code": "x = 2\n",
                    "reason": "Fix value",
                }
            ],
            "modified_files": ["src/app.py"],
            "reasoning_summary": "Fixed value to 2",
            "confidence": 0.9,
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "model": "qwen2.5-coder:7b",
            "response": json.dumps(sample_coder_dict),
            "done": True,
            "total_duration": 2000000000,
            "prompt_eval_count": 200,
            "eval_count": 100,
        }

        with patch("requests.post", return_value=mock_resp):
            metadata = AgentInputMetadata(task_id="test-task", run_id="run-1", attempt=1)
            result = agent.execute({"issue": "Fix x", "source_files": "x = 1\n"}, metadata)

            assert result.success is True
            assert isinstance(result.output, CoderOutput)
            assert len(result.output.modifications) == 1
            assert result.output.modifications[0].path == "src/app.py"
            assert result.output.confidence == 0.9
            assert result.total_tokens == 300

    def test_05_json_parse_failure_distinguished_and_handled(self):
        """When model output cannot be parsed as JSON, INVALID_RESPONSE is returned without crash."""
        cfg = ModelConfig(
            name="Coder",
            model_id="qwen2.5-coder:7b",
            provider="ollama",
            base_url="http://localhost:11434",
        )
        provider = OllamaProvider(cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "model": "qwen2.5-coder:7b",
            "response": "I cannot fulfill this request because of XYZ reasons.",
            "done": True,
            "total_duration": 1000000000,
            "prompt_eval_count": 50,
            "eval_count": 20,
        }

        with patch("requests.post", return_value=mock_resp):
            resp: ProviderResponse = provider.generate(
                prompt="Fix bug",
                response_schema=CoderOutput,
            )
            assert resp.parsed_json is None
            assert resp.error is not None
            assert "JSON_PARSE_ERROR" in resp.error
            assert resp.error_category == ErrorCategory.INVALID_RESPONSE.value

            # And CoderAgent flags failure properly
            agent = CoderAgent(provider)
            metadata = AgentInputMetadata(task_id="test-task", run_id="run-1", attempt=1)
            result = agent.execute({"issue": "Fix"}, metadata)
            assert result.success is False
            assert result.output is None

    def test_06_schema_validation_failure_distinguished(self):
        """When model returns valid JSON but invalid schema, BaseAgent flags CODER_SCHEMA_FAILURE."""
        cfg = ModelConfig(
            name="Coder",
            model_id="qwen2.5-coder:7b",
            provider="ollama",
            base_url="http://localhost:11434",
        )
        provider = OllamaProvider(cfg)
        agent = CoderAgent(provider)

        # Missing required CodeModification fields (e.g. anchor and operation missing)
        invalid_schema_dict = {
            "behavioral_analysis": "Ok",
            "modifications": [
                {
                    "path": "test.py",
                    # 'operation' and 'anchor' missing!
                }
            ],
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "model": "qwen2.5-coder:7b",
            "response": json.dumps(invalid_schema_dict),
            "done": True,
            "total_duration": 1000000000,
            "prompt_eval_count": 100,
            "eval_count": 50,
        }

        with patch("requests.post", return_value=mock_resp):
            metadata = AgentInputMetadata(task_id="test-task", run_id="run-1", attempt=1)
            result = agent.execute({"issue": "Fix"}, metadata)
            assert result.success is False
            assert result.output is None
            assert "CODER_SCHEMA_FAILURE" in (result.error_code or "")

    def test_07_connection_refused_no_fallback(self):
        """ConnectionError must immediately produce PROVIDER_UNAVAILABLE with ZERO cloud fallback."""
        cfg = ModelConfig(
            name="Coder",
            model_id="qwen2.5-coder:7b",
            provider="ollama",
            base_url="http://localhost:11434",
            max_retries=0,
        )
        provider = OllamaProvider(cfg)

        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("WinError 10061: Connection refused")):
            with patch("models.providers.GroqProvider.generate") as mock_groq_gen:
                with patch("models.providers.GeminiProvider.generate") as mock_gemini_gen:
                    resp = provider.generate("Fix bug")

                    # Fallback must NEVER be called
                    assert not mock_groq_gen.called
                    assert not mock_gemini_gen.called

                    assert resp.error is not None
                    assert "PROVIDER_UNAVAILABLE" in resp.error
                    assert resp.error_category == ErrorCategory.PROVIDER_UNAVAILABLE.value
                    assert resp.provider == "ollama"

    def test_08_timeout_no_fallback(self):
        """Timeout must produce TIMEOUT with ZERO cloud fallback."""
        cfg = ModelConfig(
            name="Coder",
            model_id="qwen2.5-coder:7b",
            provider="ollama",
            base_url="http://localhost:11434",
            timeout=10,
            max_retries=0,
        )
        provider = OllamaProvider(cfg)

        with patch("requests.post", side_effect=requests.exceptions.Timeout("Read timed out")):
            with patch("models.providers.GroqProvider.generate") as mock_groq_gen:
                resp = provider.generate("Fix bug")

                assert not mock_groq_gen.called
                assert resp.error is not None
                assert "TIMEOUT" in resp.error
                assert resp.error_category == ErrorCategory.TIMEOUT.value
                assert resp.provider == "ollama"

    def test_09_model_not_found_404_no_fallback(self):
        """404 response from Ollama produces MODEL_NOT_FOUND with ZERO cloud fallback."""
        cfg = ModelConfig(
            name="Coder",
            model_id="nonexistent-model:latest",
            provider="ollama",
            base_url="http://localhost:11434",
            max_retries=0,
        )
        provider = OllamaProvider(cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = '{"error": "model \'nonexistent-model:latest\' not found"}'

        with patch("requests.post", return_value=mock_resp):
            with patch("models.providers.GroqProvider.generate") as mock_groq_gen:
                resp = provider.generate("Fix bug")

                assert not mock_groq_gen.called
                assert resp.error is not None
                assert "MODEL_NOT_FOUND" in resp.error
                assert resp.error_category == ErrorCategory.MODEL_NOT_FOUND.value

    def test_10_patch_construction_with_coder_output(self, tmp_path):
        """Verifies DemoPatchBuilder integration with CoderOutput modifications."""
        target_file = tmp_path / "sample.py"
        target_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

        mod = CodeModification(
            path="sample.py",
            target_symbol="hello",
            operation="replace",
            anchor="    return 'world'\n",
            code="    return 'ddiv'\n",
            reason="Fix return string",
        )

        builder = DemoPatchBuilder()
        result = builder.build_patch([mod], base_dir=tmp_path)

        assert result.success is True
        assert "-    return 'world'" in result.unified_diff
        assert "+    return 'ddiv'" in result.unified_diff

        # Anchor mismatch failure test
        bad_mod = CodeModification(
            path="sample.py",
            target_symbol="hello",
            operation="replace",
            anchor="    return 'nonexistent_anchor'\n",
            code="    return 'fail'\n",
            reason="Will fail anchor match",
        )
        bad_result = builder.build_patch([bad_mod], base_dir=tmp_path)
        assert bad_result.success is False
        assert "ANCHOR_NOT_FOUND" in (bad_result.error_category or "")
