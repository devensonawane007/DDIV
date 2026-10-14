"""Offline unit tests for isolated Gemini Coder Provider Adapter.

Tests:
1. Valid JSON matching CoderOutput
2. JSON enclosed in Markdown fences
3. Whitespace and surrounding explanatory text
4. Missing required fields rejection
5. Invalid field types rejection
6. Empty and truncated responses (finish_reason='length')
7. Provider error responses and API key sanitization
8. HTTP 429 rate limit classification
9. Confirmation that default GPT-OSS configuration (Coder A) remains unchanged
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError

from agents.coder import CoderOutput
from evaluation.patch_builder import CodeModification
from models.base import ModelConfig, ProviderResponse
from models.providers import ErrorCategory
from scripts.gemini_coder_adapter import GeminiCoderProvider, robust_extract_json
from scripts.run_coder_ablation_worker import create_ablation_config


class TestGeminiCoderAdapterExtraction:
    """Test JSON extraction and schema validation routines offline."""

    def test_01_valid_json_matching_coder_output(self):
        """Test extraction and validation of pristine JSON matching CoderOutput."""
        data = {
            "behavioral_analysis": "Division by zero must be guarded.",
            "existing_behavior": "Throws raw ZeroDivisionError without clean message.",
            "smallest_change_plan": "Add zero denominator check in divide().",
            "regression_risks": ["Callers expecting ZeroDivisionError instead of ValueError"],
            "modifications": [
                {
                    "path": "src/calc.py",
                    "target_symbol": "Calculator.divide",
                    "operation": "insert_before",
                    "anchor": "return a / b",
                    "code": "if b == 0:\n    raise ValueError('division by zero')\n",
                    "reason": "Prevent zero division",
                }
            ],
            "patch": "",
            "modified_files": ["src/calc.py"],
            "reasoning_summary": "Added guard condition for b == 0.",
            "confidence": 0.95,
        }
        text = json.dumps(data)
        extracted = robust_extract_json(text)
        assert extracted is not None
        assert extracted["behavioral_analysis"] == "Division by zero must be guarded."
        
        # Validate against original CoderOutput schema
        validated = CoderOutput.model_validate(extracted)
        assert validated.confidence == 0.95
        assert len(validated.modifications) == 1
        assert validated.modifications[0].anchor == "return a / b"

    def test_02_json_enclosed_in_markdown_fences(self):
        """Test extraction when JSON is enclosed in markdown code fences."""
        raw = """Here is the suggested patch in JSON format:

```json
{
  "behavioral_analysis": "Fixing cgroup CPU detection.",
  "existing_behavior": "Integer truncation causes 0 processes.",
  "smallest_change_plan": "Ensure jobs >= 1.",
  "regression_risks": [],
  "modifications": [
    {
      "path": "pylint/lint/run.py",
      "target_symbol": "_query_cpu",
      "operation": "replace",
      "anchor": "return int(cpu_shares)",
      "code": "return max(1, int(cpu_shares))",
      "reason": "Avoid returning 0"
    }
  ],
  "patch": "",
  "modified_files": ["pylint/lint/run.py"],
  "reasoning_summary": "Clamped returned CPU count to at least 1.",
  "confidence": 0.90
}
```

Please apply this patch.
"""
        extracted = robust_extract_json(raw)
        assert extracted is not None
        validated = CoderOutput.model_validate(extracted)
        assert validated.confidence == 0.90
        assert validated.modifications[0].operation == "replace"

    def test_03_surrounding_prose_and_trailing_commas(self):
        """Test extraction when conversational prose and trailing commas exist."""
        raw = """Certainly! I analyzed the code.
{
  "behavioral_analysis": "Handle multi-index dtype preservation.",
  "existing_behavior": "Dtype upcast to object.",
  "smallest_change_plan": "Preserve original dtype array.",
  "regression_risks": ["Index conversion edge cases",],
  "modifications": [],
  "patch": "diff --git a/x.py b/x.py",
  "modified_files": ["x.py",],
  "reasoning_summary": "Preserved dtype.",
  "confidence": 0.85,
}
Hope this helps solve the issue!"""
        extracted = robust_extract_json(raw)
        assert extracted is not None
        validated = CoderOutput.model_validate(extracted)
        assert validated.confidence == 0.85
        assert validated.modified_files == ["x.py"]

    def test_04_missing_required_fields_rejected(self):
        """Test that missing required fields in modifications fail Pydantic validation."""
        # 'anchor', 'path', and 'operation' are required in CodeModification
        malformed = {
            "behavioral_analysis": "Missing required fields.",
            "modifications": [
                {
                    "path": "src/calc.py",
                    # Missing operation and anchor
                    "code": "print('hello')",
                }
            ],
            "modified_files": ["src/calc.py"],
            "reasoning_summary": "Test",
            "confidence": 0.5,
        }
        extracted = robust_extract_json(json.dumps(malformed))
        assert extracted is not None
        with pytest.raises(ValidationError) as exc_info:
            CoderOutput.model_validate(extracted)
        err_str = str(exc_info.value)
        assert "operation" in err_str or "anchor" in err_str

    def test_05_invalid_field_types_rejected(self):
        """Test that invalid types (e.g. non-numeric confidence or non-list regression_risks) fail."""
        invalid_type = {
            "behavioral_analysis": "Invalid types",
            "regression_risks": "not a list",  # Should be List[str]
            "confidence": "extremely_high",  # Should be float
        }
        extracted = robust_extract_json(json.dumps(invalid_type))
        assert extracted is not None
        with pytest.raises(ValidationError):
            CoderOutput.model_validate(extracted)

    def test_06_empty_or_truncated_responses(self):
        """Test handling of empty, whitespace-only, or truncated JSON strings."""
        assert robust_extract_json("") is None
        assert robust_extract_json("   \n\t  ") is None
        
        # Truncated in middle of string
        truncated_str = '{\n  "behavioral_analysis": "When pylint is run with --jobs=0, it invokes'
        assert robust_extract_json(truncated_str) is None

        # Truncated in middle of object
        truncated_obj = '{\n  "behavioral_analysis": "test", "modifications": [{'
        assert robust_extract_json(truncated_obj) is None


class TestGeminiCoderProviderMockedExecution:
    """Test GeminiCoderProvider network behavior with mocked OpenAI client."""

    @patch("scripts.gemini_coder_adapter.GeminiCoderProvider._get_client")
    def test_07_provider_handles_truncated_length_finish_reason(self, mock_get_client):
        """Test that finish_reason='length' is explicitly detected as truncation."""
        mock_choice = MagicMock()
        mock_choice.finish_reason = "length"
        mock_choice.message.content = '{"behavioral_analysis": "Truncated...'
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 4000
        mock_response.usage.completion_tokens = 160
        mock_response.usage.total_tokens = 8000
        mock_response.id = "req_123"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        cfg = ModelConfig(
            name="Coder",
            model_id="gemini-3.8-flash",
            provider="gemini",
            api_key="fake_key",
            max_tokens=8192,
        )
        provider = GeminiCoderProvider(cfg)
        resp = provider.generate("Test prompt", response_schema=CoderOutput)

        assert resp.error is not None
        assert "TRUNCATED_RESPONSE" in resp.error
        assert resp.parsed_json is None
        assert resp.error_category == ErrorCategory.INVALID_RESPONSE.value

    @patch("scripts.gemini_coder_adapter.GeminiCoderProvider._get_client")
    def test_08_provider_handles_http_429_rate_limit(self, mock_get_client):
        """Test that HTTP 429 exceptions are categorized as RATE_LIMITED with key sanitization."""
        from openai import RateLimitError
        import httpx

        mock_response = httpx.Response(
            status_code=429,
            request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            json={"error": {"code": 429, "message": "Resource exhausted. Key AIzaSyFakeSecretKey exceeded quota."}},
        )
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RateLimitError(
            message="Resource exhausted. Key AIzaSyFakeSecretKey exceeded quota.",
            response=mock_response,
            body=None,
        )
        mock_get_client.return_value = mock_client

        cfg = ModelConfig(
            name="Coder",
            model_id="gemini-3.8-flash",
            provider="gemini",
            api_key="AIzaSyFakeSecretKey",
            max_tokens=8192,
            max_retries=0,
        )
        provider = GeminiCoderProvider(cfg)
        resp = provider.generate("Test prompt", response_schema=CoderOutput)

        assert resp.error is not None
        assert resp.error_category == ErrorCategory.RATE_LIMITED.value
        # Key must be sanitized
        assert "AIzaSyFakeSecretKey" not in resp.error
        assert "[REDACTED" in resp.error

    def test_09_default_gpt_oss_config_remains_unchanged(self):
        """Confirm that Coder A (Groq GPT-OSS 120B) configuration remains completely intact."""
        cfg_a = create_ablation_config("coder_a", "real")
        assert cfg_a.coder.provider == "groq"
        assert cfg_a.coder.model == "openai/gpt-oss-120b"
        assert cfg_a.coder.max_tokens == 4096
        assert cfg_a.coder.base_url == "https://api.groq.com/openai/v1"

        cfg_b = create_ablation_config("coder_b", "real")
        assert cfg_b.coder.provider == "gemini"
        assert cfg_b.coder.model == "gemini-3.8-flash"
        assert cfg_b.coder.max_tokens >= 8192
        assert "googleapis.com" in cfg_b.coder.base_url
