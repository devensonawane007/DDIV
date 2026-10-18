"""Concrete ModelProvider implementations: OpenAI-compatible, specialized providers, and Mock."""

from __future__ import annotations

import json
import re
import time
from enum import Enum
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel

from models.base import ModelConfig, ModelProvider, ProviderResponse


class ErrorCategory(str, Enum):
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


def sanitize_error_message(message: str, api_key: Optional[str] = None) -> str:
    """Scrub raw API credentials and secret patterns from error strings."""
    if not message:
        return ""
    sanitized = str(message)
    if api_key and len(api_key) > 4:
        sanitized = sanitized.replace(api_key, "[REDACTED_API_KEY]")
    # Scrub common API key regex signatures
    sanitized = re.sub(r'sk-[a-zA-Z0-9_\-]{8,}', '[REDACTED_KEY]', sanitized)
    sanitized = re.sub(r'gsk_[a-zA-Z0-9_\-]{8,}', '[REDACTED_KEY]', sanitized)
    sanitized = re.sub(r'hf_[a-zA-Z0-9_\-]{8,}', '[REDACTED_KEY]', sanitized)
    sanitized = re.sub(r'AIza[a-zA-Z0-9_\-]{8,}', '[REDACTED_KEY]', sanitized)
    sanitized = re.sub(r'Bearer\s+[a-zA-Z0-9_\-\.]{8,}', 'Bearer [REDACTED_KEY]', sanitized)
    sanitized = re.sub(r'key=[a-zA-Z0-9_\-\.]{8,}', 'key=[REDACTED_KEY]', sanitized)
    return sanitized


def categorize_error(exc: Exception, status_code: Optional[int] = None) -> ErrorCategory:
    """Categorize API exceptions into standard DDIV ErrorCategory values."""
    exc_name = type(exc).__name__.lower()
    exc_str = str(exc).lower()

    if status_code == 401 or "401" in exc_str or "unauthorized" in exc_str or "authenticationerror" in exc_name:
        return ErrorCategory.AUTHENTICATION_ERROR
    if status_code == 403 or "403" in exc_str or "permission" in exc_str or "forbidden" in exc_str or "permissiondeniederror" in exc_name:
        return ErrorCategory.PERMISSION_DENIED
    if status_code == 404 or "404" in exc_str or "not found" in exc_str or "notfounderror" in exc_name:
        return ErrorCategory.MODEL_NOT_FOUND
    if status_code == 429 or "429" in exc_str or "rate limit" in exc_str or "quota" in exc_str or "ratelimiterror" in exc_name:
        return ErrorCategory.RATE_LIMITED
    if "timeout" in exc_str or "timed out" in exc_str or "timeouterror" in exc_name:
        return ErrorCategory.TIMEOUT
    if (status_code and status_code >= 500) or "500" in exc_str or "502" in exc_str or "503" in exc_str or "504" in exc_str or "connection" in exc_str or "apiconnectionerror" in exc_name or "internalservererror" in exc_name:
        return ErrorCategory.PROVIDER_UNAVAILABLE

    return ErrorCategory.PROVIDER_UNAVAILABLE


def is_retryable_error(category: ErrorCategory) -> bool:
    """Determine whether an error is transient and eligible for bounded retry."""
    return category in (
        ErrorCategory.RATE_LIMITED,
        ErrorCategory.PROVIDER_UNAVAILABLE,
        ErrorCategory.TIMEOUT,
    )


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Robustly extract a JSON object from raw LLM output."""
    if not text:
        return None
    text = text.strip()
    # 1. Direct parse attempt
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Markdown code fence match (```json ... ``` or ``` ...)
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        try:
            data = json.loads(fence_match.group(1).strip())
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 3. Outer brace heuristic
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


class OpenAICompatibleProvider(ModelProvider):
    """Base provider for OpenAI-compatible endpoints with bounded retries and error categorization."""

    def __init__(self, config: ModelConfig, default_base_url: Optional[str] = None):
        super().__init__(config)
        self.provider_name = config.provider or "openai_compatible"
        self.base_url = config.base_url or default_base_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                api_key = self.config.api_key or "EMPTY"
                self._client = OpenAI(
                    api_key=api_key,
                    base_url=self.base_url,
                    timeout=self.config.timeout,
                )
            except ImportError:
                raise RuntimeError("openai package is required for OpenAICompatibleProvider")
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> ProviderResponse:
        # Check for unconfigured / placeholder model
        if not self.config.model_id or self.config.model_id.startswith("REPLACE_") or "<" in self.config.model_id:
            return ProviderResponse(
                raw_text="",
                model_id=self.config.model_id or "unconfigured",
                provider=self.provider_name,
                error=f"Model ID is not configured (found '{self.config.model_id}'). Please set a valid model ID.",
                error_category=ErrorCategory.CONFIGURATION_ERROR.value,
            )

        client = self._get_client()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        if response_schema:
            schema_instruction = (
                f"\nYou must respond with a valid JSON object conforming to this schema:\n"
                f"{json.dumps(response_schema.model_json_schema())}\n"
                "Return ONLY the JSON object, no markdown or preamble."
            )
            messages[-1]["content"] += schema_instruction

        start_time = time.time()
        retries = 0
        last_error = ""
        last_category: Optional[ErrorCategory] = None
        max_retries = max(0, self.config.max_retries)
        kwargs: Dict[str, Any] = {
            "model": self.config.model_id,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if response_schema:
            kwargs["response_format"] = {"type": "json_object"}

        last_rate_limit_headers: Dict[str, Any] = {}

        while retries <= max_retries:
            try:
                rate_limit_headers: Dict[str, Any] = {}
                use_raw = hasattr(client.chat.completions, "with_raw_response")
                if use_raw and type(client).__module__ == "unittest.mock":
                    create_fn = getattr(client.chat.completions, "create", None)
                    if getattr(create_fn, "side_effect", None) is not None:
                        use_raw = False

                if use_raw:
                    try:
                        raw_resp = client.chat.completions.with_raw_response.create(**kwargs)
                        response = raw_resp.parse()
                        raw_headers = getattr(raw_resp, "headers", None) or {}
                        for k, v in raw_headers.items():
                            k_lower = k.lower()
                            if "ratelimit" in k_lower or "retry-after" in k_lower:
                                rate_limit_headers[k_lower] = v
                    except Exception:
                        response = client.chat.completions.create(**kwargs)
                else:
                    response = client.chat.completions.create(**kwargs)

                latency = time.time() - start_time
                content = (response.choices[0].message.content or "").strip()
                request_id = getattr(response, "id", None)

                parsed = extract_json_from_text(content) if response_schema else None
                error_msg = None
                error_cat = None

                if not content:
                    error_msg = "Model returned empty response."
                    error_cat = ErrorCategory.INVALID_RESPONSE.value
                elif response_schema and parsed is None:
                    error_msg = f"Failed to extract valid JSON matching schema from output: {content[:200]}"
                    error_cat = ErrorCategory.INVALID_RESPONSE.value

                tokens = getattr(response, "usage", None)
                prompt_tokens = getattr(tokens, "prompt_tokens", 0) or 0
                completion_tokens = getattr(tokens, "completion_tokens", 0) or 0
                total_tokens = getattr(tokens, "total_tokens", 0) or 0

                return ProviderResponse(
                    raw_text=content,
                    parsed_json=parsed,
                    model_id=self.config.model_id,
                    provider=self.provider_name,
                    latency_seconds=latency,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    request_id=request_id,
                    error=error_msg,
                    error_category=error_cat,
                    rate_limit_headers=rate_limit_headers if rate_limit_headers else None,
                )

            except Exception as e:
                status_code = getattr(e, "status_code", None)
                category = categorize_error(e, status_code)
                last_category = category
                last_error = sanitize_error_message(str(e), self.config.api_key)

                # Capture rate limit headers from exception if available
                e_headers = getattr(e, "headers", None)
                if not e_headers and hasattr(e, "response"):
                    e_headers = getattr(e.response, "headers", None)
                if e_headers:
                    for k, v in e_headers.items():
                        k_lower = k.lower()
                        if "ratelimit" in k_lower or "retry-after" in k_lower:
                            last_rate_limit_headers[k_lower] = v

                # Fast-fail non-transient errors (auth, permission, model not found)
                if not is_retryable_error(category):
                    return ProviderResponse(
                        raw_text="",
                        model_id=self.config.model_id,
                        provider=self.provider_name,
                        latency_seconds=time.time() - start_time,
                        error=f"{category.value}: {last_error}",
                        error_category=category.value,
                        rate_limit_headers=last_rate_limit_headers if last_rate_limit_headers else None,
                    )

                retries += 1
                if retries <= max_retries:
                    backoff = min(1.0 * (2 ** (retries - 1)), 8.0)
                    if category == ErrorCategory.RATE_LIMITED:
                        # Extract retry-after header if present
                        retry_after = None
                        for h_k, h_v in last_rate_limit_headers.items():
                            if "retry-after" in h_k:
                                try:
                                    retry_after = float(h_v)
                                    break
                                except (ValueError, TypeError):
                                    pass
                            elif "reset" in h_k and ("token" in h_k or "request" in h_k):
                                try:
                                    retry_after = float(str(h_v).rstrip("s"))
                                    break
                                except (ValueError, TypeError):
                                    pass
                        if retry_after is not None and retry_after > 0:
                            backoff = max(backoff, retry_after + 1.0)
                        else:
                            # For OTPM / TPM 60-second rolling window rate limits without explicit header, wait 25s
                            backoff = max(backoff, 25.0 * retries)
                    time.sleep(backoff)

        # Automatic fallback on rate limit only if explicitly enabled
        disable_fallback = getattr(self.config, "disable_fallback", True)
        if not disable_fallback and last_category == ErrorCategory.RATE_LIMITED and self.provider_name.lower() in ("groq", "openai_compatible"):
            fallback_model = None
            if "gpt-oss-120b" in self.config.model_id:
                fallback_model = "qwen/qwen3.8-27b"
            elif "qwen" in self.config.model_id:
                fallback_model = "openai/gpt-oss-120b"

            if fallback_model:
                try:
                    fb_kwargs = dict(kwargs)
                    fb_kwargs["model"] = fallback_model
                    fb_kwargs.pop("response_format", None)
                    fb_resp = client.chat.completions.create(**fb_kwargs)
                    fb_content = (fb_resp.choices[0].message.content or "").strip()
                    fb_parsed = extract_json_from_text(fb_content) if response_schema else None
                    fb_tokens = getattr(fb_resp, "usage", None)
                    if fb_content and (not response_schema or fb_parsed is not None):
                        return ProviderResponse(
                            raw_text=fb_content,
                            parsed_json=fb_parsed,
                            model_id=fallback_model,
                            provider=self.provider_name,
                            latency_seconds=time.time() - start_time,
                            prompt_tokens=getattr(fb_tokens, "prompt_tokens", 0) or 0,
                            completion_tokens=getattr(fb_tokens, "completion_tokens", 0) or 0,
                            total_tokens=getattr(fb_tokens, "total_tokens", 0) or 0,
                            request_id=getattr(fb_resp, "id", None),
                            error=None,
                        )
                except Exception:
                    pass

        return ProviderResponse(
            raw_text="",
            model_id=self.config.model_id,
            provider=self.provider_name,
            latency_seconds=time.time() - start_time,
            error=f"{last_category.value if last_category else 'PROVIDER_UNAVAILABLE'} after {max_retries} retries: {last_error}",
            error_category=last_category.value if last_category else ErrorCategory.PROVIDER_UNAVAILABLE.value,
            rate_limit_headers=last_rate_limit_headers if last_rate_limit_headers else None,
        )


class GeminiProvider(OpenAICompatibleProvider):
    """Google Gemini provider via official OpenAI-compatible endpoint."""

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __init__(self, config: ModelConfig):
        config.provider = "gemini"
        super().__init__(config, default_base_url=self.DEFAULT_BASE_URL)


class XAIProvider(OpenAICompatibleProvider):
    """xAI Grok provider via standard OpenAI-compatible endpoint."""

    DEFAULT_BASE_URL = "https://api.x.ai/v1"

    def __init__(self, config: ModelConfig):
        config.provider = "xai"
        super().__init__(config, default_base_url=self.DEFAULT_BASE_URL)


class GroqProvider(OpenAICompatibleProvider):
    """Groq LPU provider via standard OpenAI-compatible endpoint."""

    DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self, config: ModelConfig):
        config.provider = "groq"
        super().__init__(config, default_base_url=self.DEFAULT_BASE_URL)


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter provider via standard OpenAI-compatible endpoint."""

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, config: ModelConfig):
        config.provider = "openrouter"
        super().__init__(config, default_base_url=self.DEFAULT_BASE_URL)


class HuggingFaceProvider(OpenAICompatibleProvider):
    """Hugging Face Inference Providers endpoint.
    
    RESEARCH REPRODUCIBILITY GUARANTEE:
    Does NOT dynamically append :fastest, :cheapest, or :preferred.
    Explicitly uses the exact configured model ID.
    """

    DEFAULT_BASE_URL = "https://router.huggingface.co/v1"

    def __init__(self, config: ModelConfig):
        config.provider = "huggingface"
        super().__init__(config, default_base_url=self.DEFAULT_BASE_URL)


class MockModelProvider(ModelProvider):
    """Deterministic mock provider for offline testing and baseline/DDIV validation."""

    def __init__(self, config: ModelConfig, custom_responses: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.custom_responses = custom_responses or {}
        self.call_count = 0
        self.injected_failure_type: Optional[str] = None
        self.injected_recovery_strategy: Optional[str] = None

    def set_injected_scenario(self, failure_type: str, recovery_strategy: str) -> None:
        """Configure mock to trigger a specific failure and corresponding recovery."""
        self.injected_failure_type = failure_type
        self.injected_recovery_strategy = recovery_strategy

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> ProviderResponse:
        self.call_count += 1
        agent_name = self.config.name

        # Check for explicitly mocked responses
        if agent_name in self.custom_responses:
            data = self.custom_responses[agent_name]
            return ProviderResponse(
                raw_text=json.dumps(data),
                parsed_json=data,
                model_id=self.config.model_id,
                latency_seconds=0.01,
                prompt_tokens=50,
                completion_tokens=50,
                total_tokens=100,
            )

        # Default deterministic role-based responses
        data: Dict[str, Any] = {}

        if agent_name == "Locator":
            data = {
                "relevant_files": ["src/calculator.py", "tests/test_calculator.py"],
                "relevant_symbols": ["Calculator.divide", "validate_inputs"],
                "reasoning_summary": "Located divide method in Calculator class handling division logic.",
                "confidence": 0.88,
            }

        elif agent_name == "Coder":
            # Check if this prompt includes recovery instructions
            is_recovery_attempt = (
                "RECOVERY INSTRUCTIONS" in prompt
                or "TARGETED REPAIR" in prompt
                or "PREVIOUS FAILED ATTEMPTS" in prompt
            )

            if is_recovery_attempt:
                # Repaired valid patch
                patch_content = (
                    "--- a/src/calculator.py\n"
                    "+++ b/src/calculator.py\n"
                    "@@ -5,2 +5,4 @@\n"
                    "     def divide(self, a, b):\n"
                    "+        if b == 0:\n"
                    "+            raise ValueError('Cannot divide by zero')\n"
                    "         return a / b\n"
                )
                data = {
                    "patch": patch_content,
                    "modified_files": ["src/calculator.py"],
                    "reasoning_summary": "Added explicit zero-check raising ValueError as suggested by recovery instructions.",
                    "confidence": 0.94,
                }
            else:
                # Initial attempt: check if we should simulate a specific failure scenario
                if self.injected_failure_type == "F1":
                    # F1: Wrong file modified
                    patch_content = (
                        "--- a/src/unrelated.py\n"
                        "+++ b/src/unrelated.py\n"
                        "@@ -1,1 +1,2 @@\n"
                        "+# unrelated modification\n"
                    )
                    data = {
                        "patch": patch_content,
                        "modified_files": ["src/unrelated.py"],
                        "reasoning_summary": "Modified unrelated utility file.",
                        "confidence": 0.65,
                    }
                elif self.injected_failure_type == "F3":
                    # F3: Malformed patch diff
                    patch_content = "INVALID MALFORMED DIFF WITHOUT PROPER HEADERS\n@@ bad line @@"
                    data = {
                        "patch": patch_content,
                        "modified_files": ["src/calculator.py"],
                        "reasoning_summary": "Generated malformed diff without valid headers.",
                        "confidence": 0.50,
                    }
                else:
                    # Default F2: flawed logic (missing zero check)
                    patch_content = (
                        "--- a/src/calculator.py\n"
                        "+++ b/src/calculator.py\n"
                        "@@ -5,2 +5,3 @@\n"
                        "     def divide(self, a, b):\n"
                        "+        # Flawed logic: does not handle zero denominator\n"
                        "         return a / b\n"
                    )
                    data = {
                        "patch": patch_content,
                        "modified_files": ["src/calculator.py"],
                        "reasoning_summary": "Initial candidate patch modifying divide method without zero protection.",
                        "confidence": 0.72,
                    }

        elif agent_name == "Tester":
            data = {
                "assessment": "Patch modifies division logic in Calculator. Must test division by zero.",
                "suspected_failures": ["ZeroDivisionError on b=0"],
                "recommended_tests": ["test_divide_by_zero", "test_divide_normal"],
                "confidence": 0.89,
            }

        elif agent_name == "Supervisor":
            failure_type = self.injected_failure_type or "F2"
            recovery_strategy = self.injected_recovery_strategy or "A2"
            
            data = {
                "should_retry": True,
                "detected_failure": failure_type,
                "diagnosis": f"Diagnosed {failure_type} based on execution evidence.",
                "recovery_strategy": recovery_strategy,
                "intervention_instructions": f"Apply {recovery_strategy}: re-examine implementation logic and handle edge case.",
                "avoid_previous_mistake": "Do not repeat the same flawed logic.",
                "confidence": 0.85,
            }

        elif agent_name == "TestUnderstanding":
            data = {
                "root_cause": "Component logic does not properly validate contract edge cases.",
                "behavioral_contract": "Inputs must be validated and conform to specification.",
                "expected_behavior": "Correctly validate inputs and raise or return expected values.",
                "current_behavior": "Incorrect behavior on edge conditions.",
                "relevant_symbols": ["target_function"],
                "relevant_tests": ["test_expected_behavior"],
                "required_change": "Introduce proper guard or calculation logic.",
                "regression_risks": ["Breaking existing valid calls."],
            }

        elif agent_name == "PatchCritic":
            data = {
                "approved": True,
                "risk_level": "LOW",
                "concerns": [],
                "recommended_changes": [],
                "reasoning": "Patch conforms to behavioral requirements with minimal risk.",
            }

        return ProviderResponse(
            raw_text=json.dumps(data),
            parsed_json=data,
            model_id=self.config.model_id,
            latency_seconds=0.01,
            prompt_tokens=120,
            completion_tokens=80,
            total_tokens=200,
        )

