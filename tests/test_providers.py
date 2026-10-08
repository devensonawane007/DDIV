"""Unit tests for model providers, registry, and error categorization."""

import unittest
from unittest.mock import MagicMock, patch

from core.config import AgentModelConfig, DDIVConfig, ExecutionMode, ProviderType
from models.base import ModelConfig, ProviderResponse
from models.providers import (
    ErrorCategory,
    GeminiProvider,
    HuggingFaceProvider,
    MockModelProvider,
    OpenAICompatibleProvider,
    OpenRouterProvider,
    XAIProvider,
    categorize_error,
    extract_json_from_text,
    is_retryable_error,
)
from models.registry import ModelRegistry


class TestProviders(unittest.TestCase):
    def test_error_categorization(self):
        """Verify standard HTTP exceptions map to expected ErrorCategory."""
        # 401
        err_401 = Exception("401 Unauthorized: Invalid API key")
        self.assertEqual(categorize_error(err_401, 401), ErrorCategory.AUTHENTICATION_ERROR)
        self.assertFalse(is_retryable_error(ErrorCategory.AUTHENTICATION_ERROR))

        # 403
        err_403 = Exception("403 Forbidden")
        self.assertEqual(categorize_error(err_403, 403), ErrorCategory.PERMISSION_DENIED)
        self.assertFalse(is_retryable_error(ErrorCategory.PERMISSION_DENIED))

        # 404
        err_404 = Exception("404 Model not found")
        self.assertEqual(categorize_error(err_404, 404), ErrorCategory.MODEL_NOT_FOUND)
        self.assertFalse(is_retryable_error(ErrorCategory.MODEL_NOT_FOUND))

        # 429
        err_429 = Exception("429 Rate limit exceeded")
        self.assertEqual(categorize_error(err_429, 429), ErrorCategory.RATE_LIMITED)
        self.assertTrue(is_retryable_error(ErrorCategory.RATE_LIMITED))

        # 500
        err_500 = Exception("500 Internal server error")
        self.assertEqual(categorize_error(err_500, 500), ErrorCategory.PROVIDER_UNAVAILABLE)
        self.assertTrue(is_retryable_error(ErrorCategory.PROVIDER_UNAVAILABLE))

        # Timeout
        err_timeout = Exception("Request timed out after 60 seconds")
        self.assertEqual(categorize_error(err_timeout), ErrorCategory.TIMEOUT)
        self.assertTrue(is_retryable_error(ErrorCategory.TIMEOUT))

    def test_extract_json_variants(self):
        """Verify robust JSON extraction from multiple LLM output formats."""
        # Clean JSON
        raw = '{"key": "value", "count": 1}'
        self.assertEqual(extract_json_from_text(raw), {"key": "value", "count": 1})

        # Markdown fence
        fenced = 'Here is the response:\n```json\n{"key": "value"}\n```\nDone.'
        self.assertEqual(extract_json_from_text(fenced), {"key": "value"})

        # Heuristic outer braces
        loose = 'Sure, here: {"key": "value"} hope this helps!'
        self.assertEqual(extract_json_from_text(loose), {"key": "value"})

        # Invalid
        invalid = 'Just text with no json'
        self.assertIsNone(extract_json_from_text(invalid))

    def test_provider_subclasses_endpoints(self):
        """Verify each specialized provider has correct default base URL and name."""
        gemini = GeminiProvider(ModelConfig(name="Locator", model_id="gemini-test", api_key="dummy"))
        self.assertEqual(gemini.provider_name, "gemini")
        self.assertEqual(gemini.base_url, GeminiProvider.DEFAULT_BASE_URL)

        xai = XAIProvider(ModelConfig(name="Coder", model_id="grok-test", api_key="dummy"))
        self.assertEqual(xai.provider_name, "xai")
        self.assertEqual(xai.base_url, XAIProvider.DEFAULT_BASE_URL)

        op = OpenRouterProvider(ModelConfig(name="Tester", model_id="or-test", api_key="dummy"))
        self.assertEqual(op.provider_name, "openrouter")
        self.assertEqual(op.base_url, OpenRouterProvider.DEFAULT_BASE_URL)

        hf = HuggingFaceProvider(ModelConfig(name="Supervisor", model_id="hf-test", api_key="dummy"))
        self.assertEqual(hf.provider_name, "huggingface")
        self.assertEqual(hf.base_url, HuggingFaceProvider.DEFAULT_BASE_URL)

    def test_unconfigured_model_fails_fast(self):
        """Verify calling generate with a placeholder or missing model ID returns configuration error."""
        cfg = ModelConfig(name="Locator", model_id="REPLACE_LOCATOR_MODEL", provider="gemini")
        prov = GeminiProvider(cfg)
        resp = prov.generate("Hello")
        self.assertIsNotNone(resp.error)
        self.assertEqual(resp.error_category, ErrorCategory.CONFIGURATION_ERROR.value)

    @patch("models.providers.OpenAICompatibleProvider._get_client")
    def test_mocked_auth_error_no_retry(self, mock_get_client):
        """Verify 401 AuthenticationError is not retried."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        auth_err = Exception("401 Unauthorized")
        setattr(auth_err, "status_code", 401)
        mock_client.chat.completions.create.side_effect = auth_err

        cfg = ModelConfig(name="Locator", model_id="real-model-1", api_key="bad-key", max_retries=3)
        prov = OpenAICompatibleProvider(cfg)

        resp = prov.generate("Test prompt")
        self.assertEqual(mock_client.chat.completions.create.call_count, 1)
        self.assertEqual(resp.error_category, ErrorCategory.AUTHENTICATION_ERROR.value)
        self.assertIn("AUTHENTICATION_ERROR", resp.error)

    def test_model_registry_dispatch(self):
        """Verify ModelRegistry correctly instantiates providers based on config."""
        ddiv_cfg = DDIVConfig(mode=ExecutionMode.REAL, provider_type=ProviderType.OPENAI_COMPATIBLE)
        registry = ModelRegistry(ddiv_cfg)

        loc_cfg = AgentModelConfig(name="Locator", provider="gemini", model="gemini-1")
        code_cfg = AgentModelConfig(name="Coder", provider="xai", model="grok-1")
        test_cfg = AgentModelConfig(name="Tester", provider="openrouter", model="meta-1")
        sup_cfg = AgentModelConfig(name="Supervisor", provider="huggingface", model="qwen-1")

        self.assertIsInstance(registry.get_provider_for_agent(loc_cfg), GeminiProvider)
        self.assertIsInstance(registry.get_provider_for_agent(code_cfg), XAIProvider)
        self.assertIsInstance(registry.get_provider_for_agent(test_cfg), OpenRouterProvider)
        self.assertIsInstance(registry.get_provider_for_agent(sup_cfg), HuggingFaceProvider)

        # In mock mode, all should resolve to MockModelProvider
        mock_cfg = DDIVConfig(mode=ExecutionMode.MOCK)
        mock_registry = ModelRegistry(mock_cfg)
        self.assertIsInstance(mock_registry.get_provider_for_agent(loc_cfg), MockModelProvider)


if __name__ == "__main__":
    unittest.main()
